<?php
/**
 * mubashirr.com cron-pull publisher
 *
 * Fetches the latest committed draft from the public GitHub repo via the
 * REST API + raw URLs, sideloads images into WordPress media, creates a
 * draft post, sends a Telegram notification. User publishes manually
 * from WP admin.
 *
 * Architecture: GitHub Actions agents (Scout/Writer/Visual) commit content
 * to the public mubashirr-com-automation repo. This script runs every 10
 * min via cPanel Cron Jobs, polls GitHub for new content, downloads what's
 * needed into /tmp, then uses WordPress internal APIs to create the draft.
 *
 * Why GitHub API rather than `git pull`: this shared host disables
 * exec/shell_exec/proc_open/system, so running git from PHP isn't possible.
 *
 * Why cron-pull at all: direct REST from GH Actions is blocked by the
 * host's origin firewall (silent SYN drop on Azure egress) AND Cloudflare
 * Bot Fight Mode AND the host doesn't offer SSH on this plan. Pulling
 * from the host outward (over plain HTTPS to github.com) is the only
 * direction the host's network allows reliably.
 *
 * Idempotency: tracks processed slugs in state.json. A slug is processed
 * exactly once.
 *
 * Config:  /home/mubashir/cron/config.php   (see config.php.example)
 * State:   /home/mubashir/cron/state.json
 * Log:     /home/mubashir/cron/cron.log
 */

declare(strict_types=1);

$CONFIG_FILE = '/home/mubashir/cron/config.php';
$STATE_FILE  = '/home/mubashir/cron/state.json';
$LOG_FILE    = '/home/mubashir/cron/cron.log';

// --- Logging --------------------------------------------------------------
function log_msg(string $level, string $msg): void {
    global $LOG_FILE;
    $line = date('c') . " [$level] $msg" . PHP_EOL;
    @file_put_contents($LOG_FILE, $line, FILE_APPEND | LOCK_EX);
    // STDOUT is a resource only under CLI SAPI; under FPM/Apache (e.g. when
    // invoked via the kickoff shim) it's undefined.
    if (PHP_SAPI === 'cli' && defined('STDOUT') && is_resource(STDOUT)) {
        fwrite(STDOUT, $line);
    } else {
        echo $line;
    }
}

function fatal(string $msg, int $code = 1): void {
    log_msg('FATAL', $msg);
    exit($code);
}

if (!is_readable($CONFIG_FILE)) {
    fatal("missing config file: $CONFIG_FILE (see host/cron/config.php.example)");
}

$cfg = require $CONFIG_FILE;
foreach (['wp_root'] as $k) {
    if (empty($cfg[$k])) fatal("config missing required key: $k");
}

// Repo identity for GitHub API. Defaults to the public mubashirr repo.
$repo_owner = $cfg['repo_owner'] ?? 'malikmubashir';
$repo_name  = $cfg['repo_name']  ?? 'mubashirr-com-automation';
$repo_branch = $cfg['repo_branch'] ?? 'main';
$github_token = $cfg['github_token'] ?? ''; // optional, raises rate limit

// --- GitHub fetch helpers -------------------------------------------------
// This host's outbound firewall lets raw.githubusercontent.com through but
// blocks api.github.com (cURL returns HTTP 0). So we avoid the Contents API
// entirely: probe for a draft directory by trying recent Saturdays in order
// and using HEAD checks on raw URLs to detect file presence.

function gh_fetch(string $owner, string $repo, string $branch, string $path, string $token = '', bool $head_only = false) {
    $url = "https://raw.githubusercontent.com/$owner/$repo/$branch/$path";
    $headers = "User-Agent: mubashirr-cron/1.0\r\n";
    if ($token) $headers .= "Authorization: Bearer $token\r\n";
    $ctx = stream_context_create(['http' => [
        'method'  => $head_only ? 'HEAD' : 'GET',
        'timeout' => 20,
        'header'  => $headers,
        'ignore_errors' => true,
    ]]);
    $body = @file_get_contents($url, false, $ctx);
    $code = 0;
    if (isset($http_response_header[0]) && preg_match('#HTTP/\S+\s+(\d+)#', $http_response_header[0], $m)) {
        $code = (int) $m[1];
    }
    return ['code' => $code, 'body' => $body === false ? '' : (string) $body];
}

function gh_exists(string $owner, string $repo, string $branch, string $path, string $token = ''): bool {
    $r = gh_fetch($owner, $repo, $branch, $path, $token, true);
    return $r['code'] === 200;
}

function gh_get(string $owner, string $repo, string $branch, string $path, string $token = ''): string {
    $r = gh_fetch($owner, $repo, $branch, $path, $token, false);
    if ($r['code'] !== 200) fatal("github fetch $path failed: HTTP " . $r['code']);
    return $r['body'];
}

// --- Discover latest draft directory by probing recent Saturdays ----------
log_msg('INFO', "probing $repo_owner/$repo_name@$repo_branch for latest draft meta.json...");
$latest = null;
$probe_date = new DateTimeImmutable('today');
// Search back 8 weeks worth of Saturdays.
for ($i = 0; $i < 60; $i++) {
    if ((int) $probe_date->format('w') === 6) {
        if (gh_exists($repo_owner, $repo_name, $repo_branch, "drafts/" . $probe_date->format('Y-m-d') . "/meta.json", $github_token)) {
            $latest = $probe_date->format('Y-m-d');
            break;
        }
    }
    $probe_date = $probe_date->sub(new DateInterval('P1D'));
}
if (!$latest) fatal("no draft meta.json found in last 60 days of Saturdays");
log_msg('INFO', "latest draft: $latest");

// --- Read meta.json from remote ------------------------------------------
$meta_raw = gh_get($repo_owner, $repo_name, $repo_branch, "drafts/$latest/meta.json", $github_token);
$meta = json_decode($meta_raw, true);
if (!is_array($meta) || empty($meta['slug'])) {
    fatal("invalid meta.json on remote for $latest (Writer may not have committed JSON form yet)");
}

$state = is_readable($STATE_FILE) ? json_decode(file_get_contents($STATE_FILE), true) : null;
if (!is_array($state)) $state = ['processed' => []];

if (in_array($meta['slug'], $state['processed'] ?? [], true)) {
    log_msg('INFO', "slug already processed: " . $meta['slug']);
    exit(0);
}

// --- Wait for all expected images on the remote --------------------------
// Visual commits images to the repo on its own schedule; if we process
// before they arrive, the post is created without images AND the slug is
// marked done — images would then never be picked up. So we exit cleanly
// here and try next tick.
$missing = [];
foreach (($meta['image_briefs'] ?? []) as $brief) {
    $shot = $brief['shot'] ?? '';
    if (!$shot) continue;
    if (!gh_exists($repo_owner, $repo_name, $repo_branch, "drafts/$latest/images/$shot.png", $github_token)) {
        $missing[] = $shot;
    }
}
if ($missing) {
    log_msg('INFO', "waiting for images on remote: " . implode(',', $missing) . ". Will retry next tick.");
    exit(0);
}

// --- Download required files into a temp work dir ------------------------
$work_dir = sys_get_temp_dir() . '/mubashirr_' . $latest . '_' . uniqid();
if (!@mkdir($work_dir, 0700, true)) fatal("cannot create work dir $work_dir");
@mkdir("$work_dir/images", 0700, true);

file_put_contents("$work_dir/meta.json", $meta_raw);
file_put_contents("$work_dir/post.md", gh_get($repo_owner, $repo_name, $repo_branch, "drafts/$latest/post.md", $github_token));
if (gh_exists($repo_owner, $repo_name, $repo_branch, "drafts/$latest/schema.json", $github_token)) {
    file_put_contents("$work_dir/schema.json", gh_get($repo_owner, $repo_name, $repo_branch, "drafts/$latest/schema.json", $github_token));
}
foreach (($meta['image_briefs'] ?? []) as $brief) {
    $shot = $brief['shot'] ?? '';
    if (!$shot) continue;
    file_put_contents("$work_dir/images/$shot.png", gh_get($repo_owner, $repo_name, $repo_branch, "drafts/$latest/images/$shot.png", $github_token));
}
$dir = $work_dir; // downstream code reads $dir/...

log_msg('INFO', "new draft to process: slug=" . $meta['slug']);

// --- Load WordPress -------------------------------------------------------
$wp_load = rtrim($cfg['wp_root'], '/') . '/wp-load.php';
if (!is_readable($wp_load)) fatal("wp-load.php not found at $wp_load");

error_reporting(E_ALL & ~E_DEPRECATED & ~E_USER_DEPRECATED & ~E_NOTICE);
define('WP_USE_THEMES', false);
// WordPress reads $_SERVER['HTTP_HOST'] when generating URLs (home_url etc).
// In CLI/cron context that key is unset by default; populate it explicitly
// so wp_insert_post and home_url return correct URLs.
$_SERVER['HTTP_HOST']   = $cfg['wp_host'] ?? 'mubashirr.com';
$_SERVER['REQUEST_URI'] = '/';

require_once $wp_load;

$admins = get_users(['role' => 'administrator', 'number' => 1]);
if (!$admins) fatal("no administrator user in WP");
wp_set_current_user($admins[0]->ID);
log_msg('INFO', "wp loaded; acting as user_id=" . $admins[0]->ID . " (" . $admins[0]->user_login . ")");

require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

// --- Helpers --------------------------------------------------------------
function ensure_term(string $name, string $taxonomy): int {
    $existing = get_term_by('name', $name, $taxonomy);
    if ($existing && !is_wp_error($existing)) return (int) $existing->term_id;
    $created = wp_insert_term($name, $taxonomy);
    if (is_wp_error($created)) {
        log_msg('WARN', "wp_insert_term($taxonomy, $name): " . $created->get_error_message());
        return 0;
    }
    return (int) $created['term_id'];
}

function inline_md(string $s): string {
    // Order matters: bold before italic to avoid clobbering ** with *.
    $s = preg_replace('/\*\*([^\*]+?)\*\*/', '<strong>$1</strong>', $s);
    $s = preg_replace('/(?<!\*)\*([^\*]+?)\*(?!\*)/', '<em>$1</em>', $s);
    $s = preg_replace('/`([^`]+?)`/', '<code>$1</code>', $s);
    $s = preg_replace('/\[([^\]]+)\]\(([^)]+)\)/', '<a href="$2">$1</a>', $s);
    return $s;
}

function markdown_to_html(string $md): string {
    // Strip YAML front-matter
    $md = preg_replace('/^---\s*\n.*?\n---\s*\n/s', '', $md, 1) ?? $md;

    // Convert to HTML — handles the subset Writer actually produces:
    // headings, paragraphs, bullet/numbered lists, bold/italic, inline links,
    // inline code. For richer features (tables, fenced code blocks, images,
    // blockquotes), install league/commonmark via Composer in a future pass.
    $lines = preg_split("/\r\n|\n/", $md);
    $html = [];
    $in_ul = false;
    $in_ol = false;
    $close_lists = function () use (&$html, &$in_ul, &$in_ol) {
        if ($in_ul) { $html[] = '</ul>'; $in_ul = false; }
        if ($in_ol) { $html[] = '</ol>'; $in_ol = false; }
    };

    foreach ($lines as $raw) {
        $line = rtrim($raw);
        if ($line === '') { $close_lists(); continue; }

        if (preg_match('/^(#{1,6})\s+(.+)$/', $line, $m)) {
            $close_lists();
            $lvl = strlen($m[1]);
            $html[] = "<h$lvl>" . inline_md(htmlspecialchars($m[2], ENT_QUOTES, 'UTF-8')) . "</h$lvl>";
            continue;
        }
        if (preg_match('/^[-*]\s+(.+)$/', $line, $m)) {
            if ($in_ol) { $html[] = '</ol>'; $in_ol = false; }
            if (!$in_ul) { $html[] = '<ul>'; $in_ul = true; }
            $html[] = '<li>' . inline_md(htmlspecialchars($m[1], ENT_QUOTES, 'UTF-8')) . '</li>';
            continue;
        }
        if (preg_match('/^\d+\.\s+(.+)$/', $line, $m)) {
            if ($in_ul) { $html[] = '</ul>'; $in_ul = false; }
            if (!$in_ol) { $html[] = '<ol>'; $in_ol = true; }
            $html[] = '<li>' . inline_md(htmlspecialchars($m[1], ENT_QUOTES, 'UTF-8')) . '</li>';
            continue;
        }
        $close_lists();
        $html[] = '<p>' . inline_md(htmlspecialchars($line, ENT_QUOTES, 'UTF-8')) . '</p>';
    }
    $close_lists();
    return implode("\n", $html);
}

// --- Sideload images ------------------------------------------------------
$media_ids = [];
foreach (($meta['image_briefs'] ?? []) as $brief) {
    $shot = $brief['shot'] ?? '';
    if (!$shot) continue;
    $img_path = "$dir/images/$shot.png";
    if (!is_readable($img_path)) {
        log_msg('WARN', "image missing, skipping: $img_path");
        continue;
    }
    $tmp = tempnam(sys_get_temp_dir(), 'mubashirr_');
    copy($img_path, $tmp);
    $file_array = ['name' => "$shot.png", 'tmp_name' => $tmp];
    $alt = (string) ($brief['alt'] ?? '');
    $id = media_handle_sideload($file_array, 0, $alt);
    @unlink($tmp);
    if (is_wp_error($id)) {
        log_msg('WARN', "media_handle_sideload($shot): " . $id->get_error_message());
        continue;
    }
    $id = (int) $id;
    update_post_meta($id, '_wp_attachment_image_alt', $alt);
    wp_update_post(['ID' => $id, 'post_excerpt' => $alt]);
    $media_ids[$shot] = $id;
    log_msg('INFO', "sideloaded $shot -> media_id=$id");
}

// --- Build post body ------------------------------------------------------
$post_md = is_readable("$dir/post.md") ? file_get_contents("$dir/post.md") : '';
if ($post_md === '') fatal("post.md missing or empty in $dir");

$body_html = markdown_to_html($post_md);

$schema_block = '';
if (is_readable("$dir/schema.json")) {
    $schema = json_decode(file_get_contents("$dir/schema.json"), true);
    if (is_array($schema)) {
        $schema_block = "<!-- wp:html -->\n<script type=\"application/ld+json\">"
            . wp_json_encode($schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)
            . "</script>\n<!-- /wp:html -->\n\n";
    }
}

$cat_ids = array_values(array_filter(array_map(fn ($c) => ensure_term($c, 'category'), $meta['categories'] ?? [])));

// --- Create draft post ----------------------------------------------------
$post_id = wp_insert_post([
    'post_title'    => wp_strip_all_tags((string) $meta['title']),
    'post_name'     => $meta['slug'],
    'post_content'  => $schema_block . $body_html,
    'post_excerpt'  => (string) ($meta['meta_description'] ?? ''),
    'post_status'   => 'draft',
    'post_type'     => 'post',
    'post_category' => $cat_ids,
    'tags_input'    => $meta['tags'] ?? [],
    'meta_input'    => [
        'rank_math_focus_keyword' => $meta['focus_keyword'] ?? '',
        'rank_math_title'         => $meta['og_title']      ?? $meta['title'],
        'rank_math_description'   => $meta['meta_description'] ?? '',
        '_yoast_wpseo_focuskw'    => $meta['focus_keyword'] ?? '',
        '_yoast_wpseo_title'      => $meta['og_title']      ?? $meta['title'],
        '_yoast_wpseo_metadesc'   => $meta['meta_description'] ?? '',
    ],
], true);

if (is_wp_error($post_id)) fatal("wp_insert_post failed: " . $post_id->get_error_message());
$post_id = (int) $post_id;
log_msg('INFO', "created draft post_id=$post_id slug=" . $meta['slug']);

if (!empty($media_ids['hero'])) {
    set_post_thumbnail($post_id, $media_ids['hero']);
    log_msg('INFO', "set featured image media_id=" . $media_ids['hero']);
}

// --- Telegram notify ------------------------------------------------------
if (!empty($cfg['telegram_token']) && !empty($cfg['telegram_chat_id'])) {
    $preview = home_url("/?p=$post_id&preview=true");
    $admin   = home_url("/wp-admin/post.php?post=$post_id&action=edit");
    $title_clean = str_replace(['*', '_', '`', '['], '', (string) $meta['title']);
    $text = "🍽 *New post ready for review*\n*$title_clean*\n\nPreview: $preview\nEdit / publish: $admin\n\nReview in WP admin, then click *Publish*.";

    $ch = curl_init("https://api.telegram.org/bot" . $cfg['telegram_token'] . "/sendMessage");
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query([
            'chat_id'                  => $cfg['telegram_chat_id'],
            'text'                     => $text,
            'parse_mode'               => 'Markdown',
            'disable_web_page_preview' => true,
        ]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
    ]);
    $resp = curl_exec($ch);
    $tcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    log_msg($tcode === 200 ? 'INFO' : 'WARN', "telegram HTTP=$tcode " . substr((string) $resp, 0, 200));
}

// --- Update state ---------------------------------------------------------
$state['processed'][] = $meta['slug'];
$state['last_post_id'] = $post_id;
$state['last_run']     = date('c');
file_put_contents($STATE_FILE, json_encode($state, JSON_PRETTY_PRINT));
log_msg('INFO', "done. processed_count=" . count($state['processed']));

// --- Clean up temp work dir ----------------------------------------------
foreach (glob("$work_dir/images/*") ?: [] as $f) @unlink($f);
@rmdir("$work_dir/images");
foreach (glob("$work_dir/*") ?: [] as $f) @unlink($f);
@rmdir($work_dir);

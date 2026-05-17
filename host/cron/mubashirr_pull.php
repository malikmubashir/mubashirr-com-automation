<?php
/**
 * mubashirr.com cron-pull publisher
 *
 * Reads the latest committed draft from the local Git checkout, sideloads
 * images into WordPress media, creates a draft post, and sends a Telegram
 * notification. User publishes manually from WP admin.
 *
 * Architecture: GitHub Actions agents (Scout/Writer/Visual) commit content
 * to the repo. cPanel Git Version Control clones the repo locally. This
 * script runs every 10 min via cPanel Cron Jobs, reads new content from the
 * local checkout, and creates WP drafts via WordPress internal APIs.
 *
 * Why cron-pull: direct REST from GH Actions is blocked by the host's
 * origin firewall (silent SYN drop on Azure egress). SSH access is not
 * available on this hosting plan. Cron-pull avoids inbound traffic from
 * external networks entirely.
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
    fwrite(STDOUT, $line);
}

function fatal(string $msg, int $code = 1): void {
    log_msg('FATAL', $msg);
    exit($code);
}

if (!is_readable($CONFIG_FILE)) {
    fatal("missing config file: $CONFIG_FILE (see host/cron/config.php.example)");
}

$cfg = require $CONFIG_FILE;
foreach (['wp_root', 'repo_path'] as $k) {
    if (empty($cfg[$k])) fatal("config missing required key: $k");
}

// --- git pull -------------------------------------------------------------
function git_pull(string $repo_path): void {
    if (!is_dir($repo_path)) fatal("repo_path missing: $repo_path");
    chdir($repo_path);
    exec('git fetch --quiet origin main 2>&1 && git reset --hard origin/main 2>&1', $out, $code);
    $tail = implode(' | ', array_slice($out, -3));
    log_msg($code === 0 ? 'INFO' : 'WARN', "git sync (code=$code): $tail");
    if ($code !== 0) fatal("git sync failed");
}

git_pull($cfg['repo_path']);

// --- Discover latest draft ------------------------------------------------
$drafts_dir = rtrim($cfg['repo_path'], '/') . '/drafts';
if (!is_dir($drafts_dir)) fatal("drafts directory not found: $drafts_dir");

$entries = array_filter(scandir($drafts_dir), function ($d) use ($drafts_dir) {
    return $d !== '.' && $d !== '..'
        && is_dir("$drafts_dir/$d")
        && preg_match('/^\d{4}-\d{2}-\d{2}$/', $d);
});
if (!$entries) fatal("no dated draft directories found in $drafts_dir");

rsort($entries);
$latest = $entries[0];
$dir = "$drafts_dir/$latest";
log_msg('INFO', "latest draft: $latest");

$meta_path = "$dir/meta.json";
if (!is_readable($meta_path)) {
    log_msg('INFO', "no meta.json in $latest (Writer hasn't run yet or pre-dates JSON output). Exiting.");
    exit(0);
}

$meta = json_decode(file_get_contents($meta_path), true);
if (!is_array($meta) || empty($meta['slug'])) fatal("invalid meta.json: $meta_path");

$state = is_readable($STATE_FILE) ? json_decode(file_get_contents($STATE_FILE), true) : null;
if (!is_array($state)) $state = ['processed' => []];

if (in_array($meta['slug'], $state['processed'] ?? [], true)) {
    log_msg('INFO', "slug already processed: " . $meta['slug']);
    exit(0);
}

// Wait for all expected images to land before processing. Visual commits
// images to the repo on its own schedule; if we process before they arrive,
// the post is created without images AND the slug is marked done — images
// would then never be picked up. So we exit cleanly here and try next tick.
$missing = [];
foreach (($meta['image_briefs'] ?? []) as $brief) {
    $shot = $brief['shot'] ?? '';
    if (!$shot) continue;
    if (!is_readable("$dir/images/$shot.png")) $missing[] = $shot;
}
if ($missing) {
    log_msg('INFO', "waiting for images: " . implode(',', $missing) . ". Will retry next tick.");
    exit(0);
}

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

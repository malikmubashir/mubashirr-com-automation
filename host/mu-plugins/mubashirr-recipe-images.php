<?php
/**
 * Plugin Name: Mubashirr Recipe Images
 * Description: When a recipe post receives its featured (hero) image, this automatically inserts
 *   the matching ingredients, process and plated photos into the post body: ingredients under the
 *   "Ingredients" heading, process under "Method", and plated before "Variations". Idempotent, and
 *   also attaches the four photos to the post. Result: every future recipe post uses all four
 *   generated images, not just the hero.
 * Version: 1.0
 * Author: mubashirr.com
 */

if (!defined('ABSPATH')) { exit; }

add_action('added_post_meta',   'mbz_ri_meta', 20, 4);
add_action('updated_post_meta', 'mbz_ri_meta', 20, 4);
function mbz_ri_meta($mid, $post_id, $key, $val) {
    if ($key === '_thumbnail_id') { mbz_ri_apply((int) $post_id); }
}

function mbz_ri_block($att) {
    if (!$att) { return ''; }
    $url = wp_get_attachment_image_url($att, 'large');
    if (!$url) { $url = wp_get_attachment_url($att); }
    $alt = esc_attr((string) get_post_meta($att, '_wp_attachment_image_alt', true));
    $nl  = chr(10);
    $out  = '<!-- wp:image {"id":' . $att . ',"sizeSlug":"large","linkDestination":"none"} -->' . $nl;
    $out .= '<figure class="wp-block-image size-large"><img src="' . esc_url($url) . '" alt="' . $alt . '" class="wp-image-' . $att . '"/></figure>' . $nl;
    $out .= '<!-- /wp:image -->';
    return $nl . $nl . $out . $nl . $nl;
}

function mbz_ri_needle($title) { return '<h2>' . $title . '</h2>'; }

function mbz_ri_after($c, $title, $att) {
    if (!$att || strpos($c, 'wp-image-' . $att) !== false) { return $c; }
    $n = mbz_ri_needle($title);
    $i = strpos($c, $n);
    if ($i === false) { return $c . mbz_ri_block($att); }
    $pos = $i + strlen($n);
    return substr($c, 0, $pos) . mbz_ri_block($att) . substr($c, $pos);
}

function mbz_ri_before($c, $title, $att) {
    if (!$att || strpos($c, 'wp-image-' . $att) !== false) { return $c; }
    $n = mbz_ri_needle($title);
    $i = strpos($c, $n);
    if ($i === false) { return $c . mbz_ri_block($att); }
    return substr($c, 0, $i) . mbz_ri_block($att) . substr($c, $i);
}

function mbz_ri_apply($post_id) {
    $post = get_post($post_id);
    if (!$post || $post->post_type !== 'post' || $post->post_status === 'trash') { return; }

    $hero = (int) get_post_thumbnail_id($post_id);
    if (!$hero) { return; }
    $hf = get_attached_file($hero);
    if (!$hf || strpos(strtolower(basename($hf)), 'hero') !== 0) { return; }

    $shots = array('ingredients' => 0, 'process' => 0, 'plated' => 0);
    for ($off = 1; $off <= 4; $off++) {
        $cand = $hero + $off;
        $cf = get_attached_file($cand);
        if (!$cf) { continue; }
        $b = strtolower(basename($cf));
        if (!$shots['ingredients'] && strpos($b, 'ingredient') !== false) { $shots['ingredients'] = $cand; }
        if (!$shots['process']     && strpos($b, 'process')    !== false) { $shots['process']     = $cand; }
        if (!$shots['plated']      && (strpos($b, 'plated') !== false || strpos($b, 'plate') !== false)) { $shots['plated'] = $cand; }
    }
    if (!$shots['ingredients'] && !$shots['process'] && !$shots['plated']) { return; }

    $c = $post->post_content;
    $orig = $c;
    $c = mbz_ri_after($c, 'Ingredients', $shots['ingredients']);
    $c = mbz_ri_after($c, 'Method', $shots['process']);
    $c = mbz_ri_before($c, 'Variations', $shots['plated']);

    if ($c !== $orig) {
        remove_action('updated_post_meta', 'mbz_ri_meta', 20);
        remove_action('added_post_meta', 'mbz_ri_meta', 20);
        wp_update_post(array('ID' => $post_id, 'post_content' => $c));
        foreach ($shots as $a) { if ($a) { wp_update_post(array('ID' => $a, 'post_parent' => $post_id)); } }
        add_action('updated_post_meta', 'mbz_ri_meta', 20, 4);
        add_action('added_post_meta', 'mbz_ri_meta', 20, 4);
    }
}

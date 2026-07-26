<?php
/**
 * Plugin Name: Mubashirr Accent Overrides
 * Description: Recolors the theme's terracotta accent to black/white on the category keyword
 *   pills (.cat-links) and the scroll-to-top button (.back-to-top), matching the site's
 *   black-and-white styling. Global, survives theme updates. No other links are affected.
 * Version: 1.0
 * Author: mubashirr.com
 */

if (!defined('ABSPATH')) { exit; }

add_action('wp_head', function () {
    echo '<style id="mubashirr-accent-overrides">'
       . '.cat-links a,.cat-links a:visited{background:#111111!important;color:#ffffff!important;border-color:#111111!important;}'
       . '.cat-links a:hover,.cat-links a:focus{background:#000000!important;color:#ffffff!important;}'
       . '.back-to-top{background:#111111!important;}'
       . '.back-to-top:hover{background:#000000!important;}'
       . '.back-to-top svg,.back-to-top a{fill:#ffffff!important;color:#ffffff!important;}'
       . '</style>';
}, 99);

<?php
/**
 * Plugin Name: Mubashirr Home Recipe Carousel
 * Description: Prepends a warm hero + a horizontally scrolling carousel of the latest recipes to the
 *   front page, so published recipes are visible and enticing to visitors. Auto-updates. Self-contained
 *   (inline CSS + tiny vanilla JS), no theme edits, no external dependencies.
 * Version: 1.0
 * Author: mubashirr.com
 */

if (!defined('ABSPATH')) { exit; }

// Demo/placeholder posts to keep out of the showcase.
const MUBASHIRR_CAROUSEL_EXCLUDE = [1, 33, 34, 35, 36];

function mubashirr_carousel_html(): string {
    $q = new WP_Query([
        'post_type'           => 'post',
        'post_status'         => 'publish',
        'posts_per_page'      => 12,
        'post__not_in'        => MUBASHIRR_CAROUSEL_EXCLUDE,
        'ignore_sticky_posts' => true,
        'no_found_rows'       => true,
    ]);

    // Collect cards for posts that have a featured image.
    $cards = [];
    while ($q->have_posts()) {
        $q->the_post();
        if (!has_post_thumbnail()) { continue; }
        $img = esc_url(get_the_post_thumbnail_url(get_the_ID(), 'large'));
        $link = esc_url(get_permalink());
        $title = esc_html(get_the_title());
        $cats = get_the_category();
        $cat = $cats ? esc_html($cats[0]->name) : '';
        $excerpt = esc_html(wp_trim_words(get_the_excerpt(), 18, '…'));
        $cards[] = <<<CARD
<a class="mbz-card" href="{$link}">
  <div class="mbz-card-img" style="background-image:url('{$img}')"></div>
  <div class="mbz-card-body">
    <span class="mbz-tag">{$cat}</span>
    <h3 class="mbz-card-title">{$title}</h3>
    <p class="mbz-card-ex">{$excerpt}</p>
    <span class="mbz-readmore">Read the recipe &rarr;</span>
  </div>
</a>
CARD;
    }
    wp_reset_postdata();

    if (!$cards) { return ''; }
    $cards_html = implode("\n", $cards);

    $css = <<<CSS
<style id="mbz-carousel-css">
.mbz-wrap{--mbz-ink:#2b2420;--mbz-accent:#b5551d;--mbz-cream:#fbf6ef;
  font-family:'Georgia','Times New Roman',serif;margin:0 0 2.4rem;}
.mbz-hero{background:linear-gradient(135deg,#7a2e12 0%,#b5551d 55%,#d98c3f 100%);
  color:#fff;padding:3rem 1.5rem 2.6rem;text-align:center;}
.mbz-hero h1{margin:0 0 .5rem;font-size:2.3rem;letter-spacing:.5px;font-weight:700;line-height:1.15;}
.mbz-hero p{margin:0 auto;max-width:640px;font-size:1.05rem;line-height:1.6;opacity:.94;
  font-family:'Helvetica Neue',Arial,sans-serif;}
.mbz-section{max-width:1180px;margin:0 auto;padding:2.2rem 1.2rem 0;}
.mbz-head{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:1.1rem;}
.mbz-head h2{margin:0;font-size:1.6rem;color:var(--mbz-ink);}
.mbz-nav{display:flex;gap:.5rem;}
.mbz-nav button{width:40px;height:40px;border-radius:50%;border:1px solid #e2d6c8;background:var(--mbz-cream);
  color:var(--mbz-accent);font-size:1.2rem;cursor:pointer;transition:.15s;line-height:1;}
.mbz-nav button:hover{background:var(--mbz-accent);color:#fff;border-color:var(--mbz-accent);}
.mbz-track{display:flex;gap:1.1rem;overflow-x:auto;scroll-snap-type:x mandatory;
  scroll-behavior:smooth;padding:.4rem .2rem 1.4rem;-webkit-overflow-scrolling:touch;}
.mbz-track::-webkit-scrollbar{height:8px;}
.mbz-track::-webkit-scrollbar-thumb{background:#e2d6c8;border-radius:8px;}
.mbz-card{scroll-snap-align:start;flex:0 0 300px;max-width:300px;background:#fff;border-radius:14px;
  overflow:hidden;box-shadow:0 6px 20px rgba(60,40,20,.10);text-decoration:none;color:inherit;
  display:flex;flex-direction:column;transition:transform .18s,box-shadow .18s;}
.mbz-card:hover{transform:translateY(-5px);box-shadow:0 14px 30px rgba(60,40,20,.18);}
.mbz-card-img{height:190px;background-size:cover;background-position:center;}
.mbz-card-body{padding:1rem 1.1rem 1.2rem;display:flex;flex-direction:column;gap:.45rem;}
.mbz-tag{align-self:flex-start;background:var(--mbz-cream);color:var(--mbz-accent);
  font-family:'Helvetica Neue',Arial,sans-serif;font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;
  font-weight:700;padding:.25rem .6rem;border-radius:999px;}
.mbz-card-title{margin:.1rem 0 0;font-size:1.18rem;line-height:1.3;color:var(--mbz-ink);}
.mbz-card-ex{margin:0;font-size:.9rem;line-height:1.5;color:#6b5d51;
  font-family:'Helvetica Neue',Arial,sans-serif;}
.mbz-readmore{margin-top:auto;padding-top:.5rem;color:var(--mbz-accent);font-weight:700;
  font-family:'Helvetica Neue',Arial,sans-serif;font-size:.9rem;}
@media(max-width:640px){.mbz-hero h1{font-size:1.8rem;}.mbz-card{flex-basis:82vw;max-width:82vw;}}
</style>
CSS;

    $js = <<<JS
<script>
(function(){
  var t=document.getElementById('mbz-track'); if(!t) return;
  var by=function(d){t.scrollBy({left:d*(t.querySelector('.mbz-card')?t.querySelector('.mbz-card').offsetWidth+18:320),behavior:'smooth'});};
  var p=document.getElementById('mbz-prev'),n=document.getElementById('mbz-next');
  if(p)p.addEventListener('click',function(){by(-1);});
  if(n)n.addEventListener('click',function(){by(1);});
})();
</script>
JS;

    return <<<HTML
{$css}
<div class="mbz-wrap">
  <div class="mbz-hero">
    <h1>Halal French-Fusion, From My Kitchen</h1>
    <p>Pakistani spice meets French produce — original, tested recipes for everyday cooks. Fresh dishes every week.</p>
  </div>
  <div class="mbz-section">
    <div class="mbz-head">
      <h2>Latest Recipes</h2>
      <div class="mbz-nav"><button id="mbz-prev" aria-label="Previous">&larr;</button><button id="mbz-next" aria-label="Next">&rarr;</button></div>
    </div>
    <div class="mbz-track" id="mbz-track">
      {$cards_html}
    </div>
  </div>
</div>
{$js}
HTML;
}

// Inject at the top of the front-page content, once.
add_filter('the_content', function ($content) {
    if (is_front_page() && in_the_loop() && is_main_query() && !is_admin()) {
        static $done = false;
        if (!$done) {
            $done = true;
            $html = mubashirr_carousel_html();
            if ($html) { return $html . $content; }
        }
    }
    return $content;
}, 9);

// Also provide a shortcode [recent_recipes] in case the front page uses a page builder
// that bypasses the_content, so it can be placed manually.
add_shortcode('recent_recipes', 'mubashirr_carousel_html');

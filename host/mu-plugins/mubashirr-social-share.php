<?php
/**
 * Plugin Name: Mubashirr Social Share
 * Description: Adds a share bar (WhatsApp, Facebook, X, Pinterest, Instagram, Copy link) to the bottom
 *   of every recipe post. Self-contained: inline SVG icons + CSS + tiny vanilla JS, no external services,
 *   no tracking. Pinterest pins the featured image with the recipe title.
 * Version: 1.0
 * Author: mubashirr.com
 */

if (!defined('ABSPATH')) { exit; }

function mubashirr_share_bar(string $content): string {
    if (!is_singular('post') || !in_the_loop() || !is_main_query()) { return $content; }

    $url   = rawurlencode(get_permalink());
    $title = rawurlencode(get_the_title());
    $img   = rawurlencode((string) get_the_post_thumbnail_url(get_the_ID(), 'large'));
    $plain = esc_url(get_permalink());

    $wa  = "https://wa.me/?text={$title}%20{$url}";
    $fb  = "https://www.facebook.com/sharer/sharer.php?u={$url}";
    $x   = "https://twitter.com/intent/tweet?url={$url}&text={$title}";
    $pin = "https://pinterest.com/pin/create/button/?url={$url}&media={$img}&description={$title}";

    // Brand-recognisable single-path SVG icons (viewBox 0 0 24 24, currentColor).
    $ic = [
        'wa'   => '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.821 11.821 0 0 0 20.885 3.386"/>',
        'fb'   => '<path d="M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z"/>',
        'x'    => '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>',
        'pin'  => '<path d="M12.017 0C5.396 0 .029 5.367.029 11.987c0 5.079 3.158 9.417 7.618 11.162-.105-.949-.199-2.403.041-3.439.219-.937 1.406-5.957 1.406-5.957s-.359-.72-.359-1.781c0-1.663.967-2.911 2.168-2.911 1.024 0 1.518.769 1.518 1.688 0 1.029-.653 2.567-.992 3.992-.285 1.193.6 2.165 1.775 2.165 2.128 0 3.768-2.245 3.768-5.487 0-2.861-2.063-4.869-5.008-4.869-3.41 0-5.409 2.562-5.409 5.199 0 1.033.394 2.143.889 2.741.099.12.112.225.085.345-.09.375-.293 1.199-.334 1.363-.053.225-.172.271-.402.165-1.495-.69-2.433-2.878-2.433-4.646 0-3.776 2.748-7.252 7.92-7.252 4.158 0 7.392 2.967 7.392 6.923 0 4.135-2.607 7.462-6.233 7.462-1.214 0-2.354-.629-2.758-1.379l-.749 2.848c-.269 1.045-1.004 2.352-1.498 3.146 1.123.345 2.317.535 3.554.535 6.607 0 11.985-5.365 11.985-11.987C24.002 5.367 18.635.001 12.017.001z"/>',
        'ig'   => '<path d="M12 0C8.74 0 8.333.015 7.053.072 5.775.132 4.905.333 4.14.63c-.789.306-1.459.717-2.126 1.384S.935 3.35.63 4.14C.333 4.905.131 5.775.072 7.053.012 8.333 0 8.74 0 12s.015 3.667.072 4.947c.06 1.277.261 2.148.558 2.913.306.788.717 1.459 1.384 2.126.667.666 1.336 1.079 2.126 1.384.766.296 1.636.499 2.913.558C8.333 23.988 8.74 24 12 24s3.667-.015 4.947-.072c1.277-.06 2.148-.262 2.913-.558.788-.306 1.459-.718 2.126-1.384.666-.667 1.079-1.335 1.384-2.126.296-.765.499-1.636.558-2.913.06-1.28.072-1.687.072-4.947s-.015-3.667-.072-4.947c-.06-1.277-.262-2.149-.558-2.913-.306-.789-.718-1.459-1.384-2.126C21.319 1.347 20.651.935 19.86.63c-.765-.297-1.636-.499-2.913-.558C15.667.012 15.26 0 12 0zm0 2.16c3.203 0 3.585.016 4.85.071 1.17.055 1.805.249 2.227.415.562.217.96.477 1.382.896.419.42.679.819.896 1.381.164.422.36 1.057.413 2.227.057 1.266.07 1.646.07 4.85s-.015 3.585-.074 4.85c-.061 1.17-.256 1.805-.421 2.227-.224.562-.479.96-.899 1.382-.419.419-.824.679-1.38.896-.42.164-1.065.36-2.235.413-1.274.057-1.649.07-4.859.07-3.211 0-3.586-.015-4.859-.074-1.171-.061-1.816-.256-2.236-.421-.569-.224-.96-.479-1.379-.899-.421-.419-.69-.824-.9-1.38-.165-.42-.359-1.065-.42-2.235-.045-1.26-.061-1.649-.061-4.844 0-3.196.016-3.586.061-4.861.061-1.17.255-1.814.42-2.234.21-.57.479-.96.9-1.381.419-.419.81-.689 1.379-.898.42-.166 1.051-.361 2.221-.421 1.275-.045 1.65-.06 4.859-.06l.045.03zm0 3.678c-3.405 0-6.162 2.76-6.162 6.162 0 3.405 2.76 6.162 6.162 6.162 3.405 0 6.162-2.76 6.162-6.162 0-3.405-2.76-6.162-6.162-6.162zM12 16c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm7.846-10.405c0 .795-.646 1.44-1.44 1.44-.795 0-1.44-.646-1.44-1.44 0-.794.646-1.439 1.44-1.439.793-.001 1.44.645 1.44 1.439z"/>',
        'copy' => '<path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/>',
    ];

    $svg = fn($k) => '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20" aria-hidden="true">' . $ic[$k] . '</svg>';

    $css = <<<CSS
<style id="mbz-share-css">
.mbz-share{margin:2.4rem 0 1rem;padding:1.4rem 1.3rem;border:1px solid #ededed;border-radius:14px;background:#ffffff;font-family:'Helvetica Neue',Arial,sans-serif;}
.mbz-share .mbz-share-h{margin:0 0 .95rem;padding:0;font-size:1.05rem;font-weight:700;color:#111111;letter-spacing:.2px;}
.mbz-share .mbz-share-row{display:flex;flex-wrap:wrap;gap:.7rem;align-items:center;}
.mbz-share .mbz-share-row .mbz-sh{box-sizing:border-box!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;width:46px!important;height:46px!important;min-width:0!important;max-width:46px!important;padding:0!important;margin:0!important;border:0!important;border-radius:50%!important;line-height:1!important;font-size:0!important;color:#fff!important;text-decoration:none!important;box-shadow:none!important;cursor:pointer!important;-webkit-appearance:none!important;appearance:none!important;flex:0 0 auto!important;transition:transform .15s,filter .15s!important;}
.mbz-share .mbz-share-row .mbz-sh:hover{transform:translateY(-3px)!important;filter:brightness(1.06);}
.mbz-share .mbz-share-row .mbz-sh svg{width:20px!important;height:20px!important;fill:#fff!important;color:#fff!important;display:block!important;}
.mbz-share .mbz-share-row .mbz-sh.wa{background:#25d366!important}
.mbz-share .mbz-share-row .mbz-sh.fb{background:#1877f2!important}
.mbz-share .mbz-share-row .mbz-sh.x{background:#000!important}
.mbz-share .mbz-share-row .mbz-sh.pin{background:#e60023!important}
.mbz-share .mbz-share-row .mbz-sh.ig{background:radial-gradient(circle at 30% 107%,#fdf497 0%,#fdf497 5%,#fd5949 45%,#d6249f 60%,#285aeb 90%)!important}
.mbz-share .mbz-share-row .mbz-sh.copy{background:#111111!important}
.mbz-share .mbz-share-msg{margin-left:.4rem;font-size:.85rem;color:#2d6a4f;font-weight:700;opacity:0;transition:opacity .2s;}
.mbz-share .mbz-share-msg.on{opacity:1;}
</style>
CSS;

    $js = <<<JS
<script>
(function(){
  var box=document.currentScript.previousElementSibling; if(!box||!box.classList.contains('mbz-share'))return;
  var link=box.getAttribute('data-url'), msg=box.querySelector('.mbz-share-msg');
  function flash(t){msg.textContent=t;msg.classList.add('on');setTimeout(function(){msg.classList.remove('on');},2200);}
  function copy(){ if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(link).then(function(){flash('Link copied!');},function(){prompt('Copy this link:',link);});}
    else{prompt('Copy this link:',link);} }
  var c=box.querySelector('.mbz-sh.copy'); if(c)c.addEventListener('click',copy);
  var ig=box.querySelector('.mbz-sh.ig'); if(ig)ig.addEventListener('click',function(){copy();flash('Link copied — paste into your Instagram story or bio'); window.open('https://instagram.com','_blank','noopener');});
})();
</script>
JS;

    $bar = <<<BAR
{$css}
<div class="mbz-share" data-url="{$plain}">
  <p class="mbz-share-h">Loved this recipe? Share it</p>
  <div class="mbz-share-row">
    <a class="mbz-sh wa"  href="{$wa}"  target="_blank" rel="noopener" aria-label="Share on WhatsApp" title="WhatsApp">{$svg('wa')}</a>
    <a class="mbz-sh fb"  href="{$fb}"  target="_blank" rel="noopener" aria-label="Share on Facebook" title="Facebook">{$svg('fb')}</a>
    <a class="mbz-sh x"   href="{$x}"   target="_blank" rel="noopener" aria-label="Share on X" title="X">{$svg('x')}</a>
    <a class="mbz-sh pin" href="{$pin}" target="_blank" rel="noopener" aria-label="Pin on Pinterest" title="Pinterest">{$svg('pin')}</a>
    <button type="button" class="mbz-sh ig"   aria-label="Share on Instagram" title="Instagram">{$svg('ig')}</button>
    <button type="button" class="mbz-sh copy" aria-label="Copy link" title="Copy link">{$svg('copy')}</button>
    <span class="mbz-share-msg" aria-live="polite"></span>
  </div>
</div>
{$js}
BAR;

    return $content . $bar;
}

add_filter('the_content', 'mubashirr_share_bar', 20);

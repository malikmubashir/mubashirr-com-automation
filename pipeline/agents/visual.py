"""Visual: generate 4 brand-consistent food images via fal.ai Flux Pro.

Reads drafts/<date>/meta.yaml for image_briefs. Generates 4 images,
saves locally, uploads to WordPress media library, records media_ids
back into meta.yaml. Falls back to Pexels search if fal.ai fails.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import fal_client
import requests

from .common import draft_dir, env, read_yaml, wp_ca_bundle, write_yaml

log = logging.getLogger("visual")

# Browser-like User-Agent so Cloudflare's Bot Fight Mode doesn't challenge
# our REST API uploads from GitHub Actions Azure IPs.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def wp_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": BROWSER_UA,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    s.auth = (env("WP_USER", required=True), env("WP_APP_PASSWORD", required=True))
    # See pipeline/agents/common.py for the Cloudflare bypass mechanics.
    s.verify = wp_ca_bundle()
    return s

# Style fingerprint that runs in every image prompt.
BRAND_STYLE = (
    "shot on Hasselblad, natural window light from the left, soft shadows, "
    "warm muted tones, slight film grain, food styling in the manner of a "
    "modern Parisian cookbook, rustic linen, hand-thrown ceramic, no people, "
    "no text, photorealistic"
)


def generate_with_fal(prompt: str, out_path: Path) -> bool:
    full_prompt = f"{prompt}. {BRAND_STYLE}"
    try:
        result = fal_client.subscribe(
            "fal-ai/flux-pro/v1.1",
            arguments={
                "prompt": full_prompt,
                "image_size": "landscape_4_3",
                "num_inference_steps": 28,
                "guidance_scale": 3.5,
                "num_images": 1,
                "enable_safety_checker": True,
            },
        )
        url = result["images"][0]["url"]
        img = requests.get(url, timeout=60).content
        out_path.write_bytes(img)
        return True
    except Exception as e:
        log.error("fal.ai failed: %s", e)
        return False


def generate_with_pexels(query: str, out_path: Path) -> bool:
    """Fallback to Pexels stock when AI generation fails."""
    key = env("PEXELS_API_KEY")
    if not key:
        log.error("No Pexels key; cannot fall back")
        return False
    r = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": 5, "orientation": "landscape"},
        headers={"Authorization": key},
        timeout=15,
    )
    photos = r.json().get("photos", [])
    if not photos:
        return False
    img = requests.get(photos[0]["src"]["large2x"], timeout=30).content
    out_path.write_bytes(img)
    return True


def upload_to_wp(path: Path, alt: str) -> int | None:
    base = env("WP_BASE_URL", required=True).rstrip("/")
    s = wp_session()
    with path.open("rb") as f:
        r = s.post(
            f"{base}/wp-json/wp/v2/media",
            headers={
                "Content-Disposition": f'attachment; filename="{path.name}"',
                "Content-Type": "image/png",
            },
            data=f.read(),
            timeout=60,
        )
    if r.status_code >= 300:
        log.error("WP upload failed: %s %s", r.status_code, r.text[:200])
        return None
    media_id = r.json()["id"]
    # Patch alt text.
    s.post(
        f"{base}/wp-json/wp/v2/media/{media_id}",
        json={"alt_text": alt, "caption": alt},
        timeout=15,
    )
    return media_id


def run() -> None:
    dd = draft_dir()
    meta = read_yaml(dd / "meta.yaml")
    images_dir = dd / "images"
    images_dir.mkdir(exist_ok=True)

    # Architecture: Visual only generates images and writes them to disk.
    # Upload to WP happens on the host via the cron-pull PHP script — direct
    # REST API from GH Actions is blocked by the host's origin firewall.
    # Set WP_SKIP_UPLOAD=false to re-enable the legacy upload path.
    skip_upload = env("WP_SKIP_UPLOAD", "true").lower() == "true"

    media_ids: dict[str, int] = {}
    for brief in meta["image_briefs"]:
        shot = brief["shot"]
        out = images_dir / f"{shot}.png"

        log.info("Generating %s image", shot)
        if not generate_with_fal(brief["prompt"], out):
            log.warning("Falling back to Pexels for %s", shot)
            if not generate_with_pexels(meta["focus_keyword"], out):
                log.error("All image sources failed for %s; skipping", shot)
                continue

        if not skip_upload:
            media_id = upload_to_wp(out, brief["alt"])
            if media_id:
                media_ids[shot] = media_id
        time.sleep(1)  # be polite to APIs

    if not skip_upload:
        meta["media_ids"] = media_ids
        write_yaml(dd / "meta.yaml", meta)
    log.info("Visual completed. generated=%d skip_upload=%s media_ids=%s",
             len([b for b in meta["image_briefs"] if (images_dir / f'{b["shot"]}.png').exists()]),
             skip_upload, media_ids)


if __name__ == "__main__":
    run()

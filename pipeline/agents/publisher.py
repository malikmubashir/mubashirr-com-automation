"""Publisher: push the draft to WordPress, wait for Telegram approval, go live.

Converts Markdown to Gutenberg block HTML, creates a WP draft, sends a
Telegram message with Approve / Reject buttons, blocks for user response
(or timeout). On approve, flips status to publish. On reject, deletes
the draft.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import markdown as md_lib
import requests

from .common import (
    draft_dir,
    env,
    load_history,
    read_json,
    read_yaml,
    save_history,
    wp_ca_bundle,
)

log = logging.getLogger("publisher")

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
    # When WP_ORIGIN_IP is set, common.py installs a DNS override so the WP
    # host resolves directly to the origin IP, bypassing Cloudflare Bot Fight
    # Mode. The origin presents a Cloudflare Origin CA cert that isn't in the
    # public trust store, so verify against a bundle that pins the CF Origin
    # CA roots in addition to the standard certifi bundle.
    s.verify = wp_ca_bundle()
    return s


def md_to_html(markdown_text: str) -> str:
    body = markdown_text.split("---", 2)[-1].strip()  # drop front matter
    return md_lib.markdown(body, extensions=["extra", "tables", "sane_lists"])


def get_or_create_category(slug: str, name: str) -> int:
    base = env("WP_BASE_URL", required=True).rstrip("/")
    s = wp_session()
    r = s.get(f"{base}/wp-json/wp/v2/categories", params={"slug": slug})
    if r.json():
        return r.json()[0]["id"]
    r = s.post(
        f"{base}/wp-json/wp/v2/categories",
        json={"name": name, "slug": slug},
        timeout=15,
    )
    return r.json()["id"]


def get_or_create_tags(tags: list[str]) -> list[int]:
    base = env("WP_BASE_URL", required=True).rstrip("/")
    s = wp_session()
    ids = []
    for t in tags:
        slug = t.lower().replace(" ", "-")
        r = s.get(f"{base}/wp-json/wp/v2/tags", params={"slug": slug})
        if r.json():
            ids.append(r.json()[0]["id"])
            continue
        r = s.post(
            f"{base}/wp-json/wp/v2/tags",
            json={"name": t, "slug": slug},
            timeout=15,
        )
        if r.status_code < 300:
            ids.append(r.json()["id"])
    return ids


def create_wp_draft(meta: dict, html_body: str, schema: dict) -> dict:
    base = env("WP_BASE_URL", required=True).rstrip("/")
    s = wp_session()

    # Inject JSON-LD schema at top of content (RankMath will not duplicate
    # if we disable its recipe schema).
    import json as _json
    schema_block = (
        f'<script type="application/ld+json">{_json.dumps(schema)}</script>\n'
    )

    category_ids = [
        get_or_create_category(c.lower().replace(" ", "-"), c)
        for c in meta.get("categories", [])
    ]
    tag_ids = get_or_create_tags(meta.get("tags", []))
    featured = meta.get("media_ids", {}).get("hero")

    payload = {
        "title": meta["title"],
        "slug": meta["slug"],
        "status": "draft",
        "content": schema_block + html_body,
        "excerpt": meta["meta_description"],
        "categories": category_ids,
        "tags": tag_ids,
        "meta": {
            "_yoast_wpseo_title": meta.get("og_title", meta["title"]),
            "_yoast_wpseo_metadesc": meta["meta_description"],
            "rank_math_title": meta.get("og_title", meta["title"]),
            "rank_math_description": meta["meta_description"],
            "rank_math_focus_keyword": meta["focus_keyword"],
        },
    }
    if featured:
        payload["featured_media"] = featured

    r = s.post(f"{base}/wp-json/wp/v2/posts", json=payload, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"WP draft creation failed: {r.status_code} {r.text[:300]}")
    return r.json()


def send_telegram(post_id: int, preview_url: str, title: str) -> int | None:
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    if not (token and chat):
        log.warning("No Telegram creds; skipping approval step")
        return None
    text = (
        f"<b>Saturday post ready</b>\n"
        f"<i>{title}</i>\n\n"
        f"Preview: {preview_url}\n\n"
        f"Reply <code>/approve {post_id}</code> or <code>/reject {post_id}</code>."
    )
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "Approve", "callback_data": f"approve:{post_id}"},
                    {"text": "Reject", "callback_data": f"reject:{post_id}"},
                ]]
            },
        },
        timeout=15,
    )
    return r.json().get("result", {}).get("message_id")


def wait_for_approval(post_id: int, timeout_min: int) -> str:
    """Poll Telegram for callback. Returns 'approve' | 'reject' | 'timeout'."""
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        return "timeout"
    deadline = time.time() + timeout_min * 60
    last_update = 0
    while time.time() < deadline:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": last_update + 1, "timeout": 30},
            timeout=35,
        )
        for upd in r.json().get("result", []):
            last_update = upd["update_id"]
            cb = upd.get("callback_query")
            if cb and cb.get("data", "").endswith(f":{post_id}"):
                action = cb["data"].split(":")[0]
                return action
        time.sleep(5)
    return "timeout"


def flip_status(post_id: int, status: str) -> None:
    base = env("WP_BASE_URL", required=True).rstrip("/")
    s = wp_session()
    r = s.post(
        f"{base}/wp-json/wp/v2/posts/{post_id}",
        json={"status": status},
        timeout=15,
    )
    r.raise_for_status()


def run(dry_run: bool = False) -> None:
    dd = draft_dir()
    meta = read_yaml(dd / "meta.yaml")
    schema = read_json(dd / "schema.json")
    body_md = (dd / "post.md").read_text()
    html = md_to_html(body_md)

    if dry_run:
        log.info("DRY RUN: would publish title=%r slug=%r words=%d",
                 meta["title"], meta["slug"], len(body_md.split()))
        return

    draft = create_wp_draft(meta, html, schema)
    post_id = draft["id"]
    preview = draft.get("link") or f"{env('WP_BASE_URL')}/?p={post_id}&preview=true"
    log.info("WP draft created: id=%s preview=%s", post_id, preview)

    send_telegram(post_id, preview, meta["title"])

    timeout = int(env("TIMEOUT_MINUTES", "120"))
    auto_pub = env("AUTO_PUBLISH_ON_TIMEOUT", "true").lower() == "true"

    decision = wait_for_approval(post_id, timeout)
    log.info("Decision: %s", decision)

    if decision == "reject":
        # Keep as draft, do not delete; user may want to edit.
        log.info("Rejected. Post remains as draft for editing.")
        return

    if decision == "approve" or (decision == "timeout" and auto_pub):
        flip_status(post_id, "publish")
        h = load_history()
        h.setdefault("slugs", []).append(meta["slug"])
        save_history(h)
        log.info("Published: %s", preview)
    else:
        log.info("Timeout with auto-publish disabled. Manual review required.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

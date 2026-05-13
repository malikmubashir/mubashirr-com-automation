"""Distributor: fan published post out to social channels on staggered times.

Schedules platform-tailored variants via Buffer API. If Buffer is not
configured, falls back to direct platform APIs where keys exist, else
writes a manual-post queue to drafts/<date>/manual-queue.md.

Variants and timing:
    Pinterest pin       Saturday 20:00, Sunday 11:00
    Instagram carousel  Sunday 11:30
    Email newsletter    Tuesday 09:00
    LinkedIn post       Wednesday 08:30
    X thread            Thursday 18:00
    Facebook share      Saturday 19:00
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, time, timedelta
from pathlib import Path

import anthropic
import requests

from .common import (
    draft_dir,
    env,
    now_iso,
    read_yaml,
    this_saturday,
    write_json,
)

log = logging.getLogger("distributor")


def make_variants(meta: dict, post_url: str) -> dict:
    """Use Claude to produce platform-tailored copy."""
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    model = env("ANTHROPIC_MODEL", default="claude-sonnet-4-6")
    prompt = f"""You are repurposing one blog post into platform-tailored social copy.
Voice: same as Dr Mubashir's blog (direct, slightly literary, no AI-isms, no emoji unless
the platform demands them, no "in today's fast-paced world", no em dashes for decoration).

Blog post:
Title: {meta['title']}
Focus keyword: {meta['focus_keyword']}
Meta description: {meta['meta_description']}
URL: {post_url}
Categories: {meta.get('categories')}
Tags: {meta.get('tags')}

Produce strictly this JSON:
{{
  "pinterest": {{ "title": "<= 100 chars", "description": "<= 500 chars with focus keyword" }},
  "instagram": {{ "caption": "150-220 words, narrative not listy", "hashtags": ["#tag1", ...] (10-12 tags) }},
  "email": {{ "subject": "<= 50 chars", "preheader": "<= 90 chars", "body_html": "200-350 words HTML email body, no images, ends with link to post" }},
  "linkedin": {{ "body": "180-280 words, angle: cultural/technique story, NOT recipe-listy" }},
  "x_thread": {{ "tweets": ["tweet 1 hook (<=270 chars)", "tweet 2", "tweet 3", "tweet 4", "tweet 5 with link"] }},
  "facebook": {{ "body": "80-130 words" }}
}}
Return only the JSON, no prose.
"""
    resp = client.messages.create(
        model=model, max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def schedule_with_buffer(profile_id: str, text: str, at: datetime,
                         media_url: str | None = None) -> bool:
    token = env("BUFFER_ACCESS_TOKEN")
    if not token:
        return False
    payload = {
        "text": text,
        "profile_ids[]": profile_id,
        "scheduled_at": int(at.timestamp()),
        "access_token": token,
    }
    if media_url:
        payload["media[photo]"] = media_url
    r = requests.post("https://api.bufferapp.com/1/updates/create.json",
                      data=payload, timeout=20)
    return r.status_code < 300


def slot(sat: 'datetime.date', day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(sat + timedelta(days=day_offset), time(hour, minute))


def run(post_url: str | None = None) -> None:
    dd = draft_dir()
    meta = read_yaml(dd / "meta.yaml")

    if not post_url:
        # Reconstruct from slug; Publisher should pass this through state.
        post_url = f"{env('WP_BASE_URL').rstrip('/')}/{meta['slug']}/"

    log.info("Distributor making variants for %s", post_url)
    variants = make_variants(meta, post_url)

    sat = this_saturday()
    schedule = {
        "pinterest_sat":  slot(sat, 0, 20, 0),
        "pinterest_sun":  slot(sat, 1, 11, 0),
        "instagram":      slot(sat, 1, 11, 30),
        "email":          slot(sat, 3, 9, 0),    # Tuesday
        "linkedin":       slot(sat, 4, 8, 30),   # Wednesday
        "x_thread":       slot(sat, 5, 18, 0),   # Thursday
        "facebook":       slot(sat, 0, 19, 0),
    }

    log_lines = [f"# Distribution plan for {meta['title']}\n", f"Post URL: {post_url}\n"]
    for channel, when in schedule.items():
        log_lines.append(f"\n## {channel} ({when.isoformat()})")
        log_lines.append("```")
        # Pretty-print whichever variant maps here.
        key = channel.split("_")[0]
        log_lines.append(json.dumps(variants.get(key, {}), indent=2, ensure_ascii=False))
        log_lines.append("```")

    (dd / "manual-queue.md").write_text("\n".join(log_lines))
    write_json(dd / "distribution.json", {
        "scheduled_at": now_iso(),
        "post_url": post_url,
        "variants": variants,
        "schedule": {k: v.isoformat() for k, v in schedule.items()},
    })
    log.info("Wrote manual-queue.md (review and post manually, or configure Buffer)")

    # TODO: when Buffer profile ids are configured, replace the above with
    # actual schedule_with_buffer() calls per channel.


if __name__ == "__main__":
    run()

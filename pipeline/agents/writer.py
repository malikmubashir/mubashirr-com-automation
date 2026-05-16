"""Writer: generate the long-form post in Dr Mubashir's voice.

Reads drafts/<date>/scout.json. Generates 1,400-1,800 word post Markdown,
Schema.org Recipe JSON-LD, SEO metadata. Writes:
    drafts/<date>/post.md
    drafts/<date>/schema.json
    drafts/<date>/meta.yaml
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic

from .common import (
    CONFIG,
    draft_dir,
    env,
    now_iso,
    read_json,
    write_json,
    write_yaml,
)

log = logging.getLogger("writer")

VOICE_GUIDE = (CONFIG / "voice-guide.md").read_text()

SYSTEM_PROMPT = f"""You are writing a food blog post for mubashirr.com under
Dr Mubashir's byline. You must follow this voice guide precisely:

{VOICE_GUIDE}

Output exactly one JSON object with these keys and nothing else:
- title: str (recipe name, no fluff, 4-8 words)
- slug: str (kebab-case, max 60 chars, includes focus keyword)
- focus_keyword: str (the primary SEO target, 2-4 words)
- meta_description: str (140-155 chars, includes focus keyword)
- og_title: str (60 chars max, click-friendly)
- og_description: str (155-200 chars)
- tags: list[str] (8-12 tags)
- categories: list[str] (1-3, from: Dishes, Salad, Soups, Spices, Heritage, French Technique, Halal)
- markdown: str (the full post body, 1400-1800 words, see structure below)
- recipe_schema: dict (valid Schema.org Recipe JSON-LD, passes Google's Rich Results Test)
- image_briefs: list[dict] with 4 entries, each {{"shot": "hero|ingredients|process|plated", "prompt": str, "alt": str}}
- pinterest_overlay_text: str (max 8 words, used as text overlay on Pinterest pin)
- email_subject: str (under 50 chars)
- internal_link_anchors: list[str] (3 phrases this post should link to; we'll wire them later)

Markdown body structure (in this order, with H2/H3):
## Headnote
80-180 words. Real, specific, not generic.

## At a glance
A compact summary block: total time, servings, difficulty, key technique. Format as a small Markdown table.

## Ingredients
H3 sub-sections if there are component parts (e.g., marinade, sauce). Metric primary, imperial in parens. Group logically.

## Ingredient notes
Only non-obvious ingredients. Where to source, what to substitute, why.

## Method
Numbered steps. Each step does one thing. Include the why where relevant.

## Variations
2-4 concrete swaps.

## Storage and reheating
Specific. Not "store in the fridge."

## FAQ
5-7 H3 questions, each with a 1-3 sentence answer. Real questions a competent home cook would ask.
"""


def build_user_prompt(scout: dict) -> str:
    theme = scout["theme"]
    candidate = scout["top_candidate"]
    heritage = theme.get("heritage_mode", False)
    return f"""Theme: {theme['theme']}
Heritage mode: {heritage}
Target word count: {theme.get('target_word_count', 1500)}
Seed keywords (use one as focus): {theme.get('seed_keywords', [])}

Candidate recipe (use as factual scaffold; write everything in your own voice):
Title: {candidate['title']}
Source URL (for your reference only, do not link to it): {candidate.get('source_url')}
Cuisine: {candidate.get('cuisine')}
Servings: {candidate.get('servings')}
Total time (min): {candidate.get('total_time_min')}
Ingredients (raw):
{json.dumps(candidate.get('ingredients', []), indent=2)}

Constraints from theme: {theme.get('constraints', [])}

If heritage mode is true, the headnote must include one specific personal memory (you may invent
it within plausibility — e.g., "my mother always tempered the cumin separately because...").

Return the JSON object as specified. No prose outside the JSON.
"""


def call_claude(scout: dict) -> dict:
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    model = env("ANTHROPIC_MODEL", default="claude-sonnet-4-6")
    resp = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(scout)}],
    )
    raw = resp.content[0].text.strip()
    # Strip code fences if the model wraps the JSON.
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def validate(post: dict) -> None:
    required = {
        "title", "slug", "focus_keyword", "meta_description", "tags",
        "categories", "markdown", "recipe_schema", "image_briefs",
    }
    missing = required - set(post)
    if missing:
        raise ValueError(f"Writer output missing fields: {missing}")
    md = post["markdown"]
    words = len(md.split())
    if words < 1200 or words > 2200:
        log.warning("Word count out of band: %d", words)
    if len(post["image_briefs"]) != 4:
        raise ValueError("Need exactly 4 image briefs")
    if post["recipe_schema"].get("@type") != "Recipe":
        raise ValueError("Schema must be @type=Recipe")


def run() -> None:
    dd = draft_dir()
    scout = read_json(dd / "scout.json")
    if not scout.get("top_candidate"):
        raise SystemExit("No top_candidate in scout.json. Run scout first.")

    log.info("Writer drafting for: %s", scout["top_candidate"]["title"])
    post = call_claude(scout)
    validate(post)

    # Compose Markdown with front matter.
    fm = (
        "---\n"
        f"title: \"{post['title']}\"\n"
        f"slug: \"{post['slug']}\"\n"
        f"focus_keyword: \"{post['focus_keyword']}\"\n"
        f"meta_description: \"{post['meta_description']}\"\n"
        f"tags: {json.dumps(post['tags'])}\n"
        f"categories: {json.dumps(post['categories'])}\n"
        f"generated_at: \"{now_iso()}\"\n"
        "---\n\n"
    )
    (dd / "post.md").write_text(fm + post["markdown"])
    write_json(dd / "schema.json", post["recipe_schema"])

    meta = {
        "title": post["title"],
        "slug": post["slug"],
        "focus_keyword": post["focus_keyword"],
        "meta_description": post["meta_description"],
        "og_title": post["og_title"],
        "og_description": post["og_description"],
        "tags": post["tags"],
        "categories": post["categories"],
        "image_briefs": post["image_briefs"],
        "pinterest_overlay_text": post["pinterest_overlay_text"],
        "email_subject": post["email_subject"],
        "internal_link_anchors": post["internal_link_anchors"],
        "media_ids": {},  # filled in by Visual
    }
    write_yaml(dd / "meta.yaml", meta)
    # meta.json is the canonical machine-readable form. The cron-pull PHP on
    # the WP host reads JSON (avoids needing a YAML parser there).
    write_json(dd / "meta.json", meta)
    log.info("Writer wrote post.md (%d words), schema.json, meta.yaml, meta.json",
             len(post["markdown"].split()))


if __name__ == "__main__":
    run()

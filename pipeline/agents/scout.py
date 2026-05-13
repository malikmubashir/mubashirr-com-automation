"""Scout: source structured recipe candidates for this week's theme.

Pulls candidate recipes from Edamam and TheMealDB, filters by the week's
halal and theme constraints, scores them by SEO potential (search volume
proxy from Google Trends), and writes the top 5 to drafts/<date>/scout.json.

Usage:
    python -m pipeline.agents.scout
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .common import (
    current_theme,
    draft_dir,
    env,
    load_history,
    now_iso,
    write_json,
)

log = logging.getLogger("scout")

# Hard-block ingredients regardless of theme.
HARAM_BLOCK = {
    "pork", "bacon", "ham", "lard", "prosciutto", "pancetta", "chorizo",
    "wine", "beer", "rum", "whisky", "whiskey", "brandy", "vodka", "sake", "mirin",
    "gelatin",  # block unless caller confirms halal source
}


def fetch_edamam(query: str, count: int = 20) -> list[dict]:
    """Edamam Recipe Search API v2 (Meal Planner Developer plan).

    Free tier: 10 calls/min, 10000/month. Requires Edamam-Account-User
    header on every request — value is any string identifying the
    consuming account; we use a fixed identifier.
    """
    app_id = env("EDAMAM_APP_ID")
    app_key = env("EDAMAM_APP_KEY")
    if not (app_id and app_key):
        log.warning("Edamam credentials missing; skipping")
        return []
    url = "https://api.edamam.com/api/recipes/v2"
    headers = {
        "Edamam-Account-User": env("EDAMAM_USER", default="mubashirr-com"),
        "Accept": "application/json",
    }
    params = {
        "type": "public",
        "q": query,
        "app_id": app_id,
        "app_key": app_key,
        "random": "true",
        "field": ["label", "ingredientLines", "totalTime", "yield",
                  "cuisineType", "mealType", "dietLabels", "healthLabels",
                  "calories", "totalNutrients", "url"],
    }
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    hits = r.json().get("hits", [])[:count]
    return [h["recipe"] for h in hits]


def fetch_themealdb(query: str) -> list[dict]:
    """TheMealDB free search API."""
    r = requests.get(
        "https://www.themealdb.com/api/json/v1/1/search.php",
        params={"s": query}, timeout=15,
    )
    r.raise_for_status()
    return r.json().get("meals") or []


def looks_halal(ingredients_text: str) -> bool:
    low = ingredients_text.lower()
    return not any(tok in low for tok in HARAM_BLOCK)


def score_seo_potential(title: str) -> float:
    """Cheap proxy: prefer 2-3 word titles with concrete dish names.

    Real implementation should query pytrends or a paid API. We keep this
    deterministic so tests are stable.
    """
    words = title.split()
    if 2 <= len(words) <= 4:
        return 0.8
    if len(words) <= 6:
        return 0.6
    return 0.3


def normalize_edamam(r: dict) -> dict:
    return {
        "source": "edamam",
        "title": r.get("label"),
        "ingredients": r.get("ingredientLines", []),
        "total_time_min": r.get("totalTime"),
        "servings": r.get("yield"),
        "cuisine": r.get("cuisineType", []),
        "meal_type": r.get("mealType", []),
        "calories": r.get("calories"),
        "source_url": r.get("url"),
    }


def normalize_themealdb(m: dict) -> dict:
    ings = []
    for i in range(1, 21):
        name = (m.get(f"strIngredient{i}") or "").strip()
        amount = (m.get(f"strMeasure{i}") or "").strip()
        if name:
            ings.append(f"{amount} {name}".strip())
    return {
        "source": "themealdb",
        "title": m.get("strMeal"),
        "ingredients": ings,
        "instructions_raw": m.get("strInstructions"),
        "cuisine": [m.get("strArea")] if m.get("strArea") else [],
        "category": m.get("strCategory"),
        "source_url": m.get("strSource") or m.get("strYoutube"),
    }


def run() -> None:
    theme = current_theme()
    log.info("Scout running for theme=%s", theme["theme"])

    history = load_history()
    seen_titles = {s.lower() for s in history.get("slugs", [])}

    candidates: list[dict[str, Any]] = []
    for kw in theme.get("seed_keywords", []):
        candidates.extend(normalize_edamam(r) for r in fetch_edamam(kw))
        candidates.extend(normalize_themealdb(m) for m in fetch_themealdb(kw))

    # Filter.
    keep: list[dict[str, Any]] = []
    for c in candidates:
        if not c.get("title"):
            continue
        if c["title"].lower() in seen_titles:
            continue
        ing_text = " ".join(c.get("ingredients", []))
        if not looks_halal(ing_text):
            log.debug("Filtered haram-flagged: %s", c["title"])
            continue
        c["seo_score"] = score_seo_potential(c["title"])
        keep.append(c)

    keep.sort(key=lambda x: x["seo_score"], reverse=True)
    top5 = keep[:5]

    out = {
        "generated_at": now_iso(),
        "theme": theme,
        "top_candidate": top5[0] if top5 else None,
        "alternates": top5[1:] if len(top5) > 1 else [],
        "stats": {
            "candidates_fetched": len(candidates),
            "candidates_after_filter": len(keep),
        },
    }
    target = draft_dir() / "scout.json"
    write_json(target, out)
    log.info("Wrote %s (%d candidates kept)", target, len(keep))

    if not top5:
        raise SystemExit("Scout produced zero candidates. Check API keys or relax constraints.")


if __name__ == "__main__":
    run()

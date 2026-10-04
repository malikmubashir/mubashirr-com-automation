"""Produce: keep a stock of complete, verified recipe drafts in drafts/.

One job, run daily. It reconciles state instead of choreographing timers:

    1. Rebuild drafts/index.json from the manifests on disk.
    2. Find the earliest Saturday in the horizon without a complete draft.
       Horizon = last Saturday (if within the past 7 days, so a missed week
       can still be rescued) + the next STOCK_TARGET Saturdays.
    3. If none is missing, exit 0 in a few seconds. Stock is full.
    4. Otherwise produce exactly one draft, sequentially, in this process:
       scout -> writer -> visual -> validate -> manifest. Steps whose outputs
       already exist are skipped (resume), unless FORCE=true.
    5. Any failure raises. The workflow then commits nothing, goes red, and
       tomorrow's run retries. There is no such thing as a partial draft.

Environment:
    STOCK_TARGET   how many future Saturdays to keep complete (default 2)
    DRAFT_DATE     produce this exact Saturday instead of the earliest gap
    FORCE          "true" = redo every step even if outputs exist
    CHECK_LIVE     "true" = also check slug/title against the live site
    GITHUB_OUTPUT  when set (Actions), writes produced=<date> and slug=<slug>

Usage:
    python -m pipeline.produce
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .agents.common import DRAFTS, env
from .validate import (
    IMAGE_SHOTS,
    is_complete,
    validate_draft,
    verify_manifest,
    write_manifest,
)

log = logging.getLogger("produce")

INDEX_PATH = DRAFTS / "index.json"


class ProduceError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def saturdays_in_horizon(today: date, stock_target: int) -> list[date]:
    nxt = today + timedelta(days=(5 - today.weekday()) % 7)  # today if Saturday
    horizon = []
    last = nxt - timedelta(days=7)
    if 0 < (today - last).days <= 7:
        horizon.append(last)
    horizon += [nxt + timedelta(days=7 * i) for i in range(stock_target)]
    return horizon


# Drafts older than this were produced by the v1 cron chain and published
# through the old host cron. They have no manifest and never will; they are
# listed as "legacy" so they do not read as failures.
LEGACY_BEFORE = date(2026, 10, 3)


def rebuild_index() -> dict:
    """Summarise every draft folder; this is what the delivery task reads."""
    complete, partial, legacy = [], [], []
    for d in sorted(DRAFTS.iterdir()) if DRAFTS.exists() else []:
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                meta = {}
        entry = {"date": d.name, "slug": meta.get("slug"), "title": meta.get("title")}
        if is_complete(d):
            m = json.loads((d / "manifest.json").read_text())
            entry["manifest_created_at"] = m.get("created_at")
            complete.append(entry)
            continue
        try:
            folder_date = date.fromisoformat(d.name)
        except ValueError:
            folder_date = None
        if folder_date and folder_date < LEGACY_BEFORE:
            legacy.append(entry)
        else:
            entry["problems"] = verify_manifest(d)[:3]
            partial.append(entry)
    today = date.today()
    future_complete = [e for e in complete if date.fromisoformat(e["date"]) >= today]
    index = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stock": len(future_complete),
        "next_due": future_complete[0]["date"] if future_complete else None,
        "complete": complete,
        "partial": partial,
        "legacy": legacy,
    }
    DRAFTS.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n")
    return index


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _have(dd: Path, *names: str) -> bool:
    return all((dd / n).exists() for n in names)


def step_scout(dd: Path, force: bool) -> None:
    if not force and _have(dd, "scout.json"):
        log.info("scout: scout.json exists, skipping")
        return
    from .agents import scout
    scout.run()
    if not _have(dd, "scout.json"):
        raise ProduceError("scout finished without writing scout.json")


def step_writer(dd: Path, force: bool) -> None:
    if not force and _have(dd, "meta.json", "post.md", "schema.json"):
        log.info("writer: outputs exist, skipping")
        return
    from .agents import writer
    writer.run()
    if not _have(dd, "meta.json", "post.md", "schema.json"):
        raise ProduceError("writer finished without writing meta.json/post.md/schema.json")


def step_visual(dd: Path, force: bool) -> None:
    images = [dd / "images" / f"{s}.png" for s in IMAGE_SHOTS]
    if not force and all(p.exists() for p in images):
        log.info("visual: all 4 images exist, skipping")
        return
    if force:
        for p in images:
            p.unlink(missing_ok=True)
    # Fail on text problems BEFORE spending money on four image generations.
    text_problems = [p for p in validate_draft(dd) if "images/" not in p]
    if text_problems:
        for p in text_problems:
            log.error("pre-visual: %s", p)
        raise ProduceError("text/meta problems; not generating images")
    os.environ.setdefault("WP_SKIP_UPLOAD", "true")  # images travel through git, never direct upload
    from .agents import visual
    visual.run()
    missing = [p.name for p in images if not p.exists()]
    if missing:
        raise ProduceError(f"visual finished without producing: {missing}")


def produce(target: date, *, force: bool, check_live: bool) -> dict:
    os.environ["DRAFT_DATE"] = target.isoformat()
    dd = DRAFTS / target.isoformat()
    dd.mkdir(parents=True, exist_ok=True)
    log.info("=== producing drafts/%s (force=%s) ===", target, force)

    step_scout(dd, force)
    step_writer(dd, force)
    step_visual(dd, force)

    problems = validate_draft(dd, check_live=check_live)
    if problems:
        for p in problems:
            log.error("validation: %s", p)
        raise ProduceError(f"drafts/{target} failed validation with {len(problems)} problem(s)")

    manifest = write_manifest(dd)
    log.info("=== drafts/%s complete: %s ===", target, manifest["slug"])
    return manifest


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _gh_output(**kv: str) -> None:
    out = os.getenv("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")


def main() -> int:
    stock_target = int(env("STOCK_TARGET", "2") or 2)
    force = env("FORCE", "false").lower() == "true"
    check_live = env("CHECK_LIVE", "false").lower() == "true"
    override = env("DRAFT_DATE", "").strip()

    index = rebuild_index()
    log.info("stock=%d next_due=%s partial=%d", index["stock"], index["next_due"], len(index["partial"]))

    if override:
        target = date.fromisoformat(override)
        if target.weekday() != 5:
            raise ProduceError(f"DRAFT_DATE {target} is not a Saturday")
        if is_complete(DRAFTS / override) and not force:
            log.info("drafts/%s already complete; set FORCE=true to redo it", override)
            _gh_output(produced="", slug="")
            return 0
    else:
        horizon = saturdays_in_horizon(date.today(), stock_target)
        gaps = [s for s in horizon if not is_complete(DRAFTS / s.isoformat())]
        log.info("horizon=%s gaps=%s", [s.isoformat() for s in horizon], [s.isoformat() for s in gaps])
        if not gaps:
            log.info("stock full (%d/%d). Nothing to do.", index["stock"], stock_target)
            _gh_output(produced="", slug="")
            return 0
        target = gaps[0]

    manifest = produce(target, force=force, check_live=check_live)
    index = rebuild_index()
    log.info("stock now %d/%d", index["stock"], stock_target)
    _gh_output(produced=manifest["date"], slug=manifest["slug"])
    return 0


def summary_markdown() -> str:
    """Short Markdown status for the Actions step summary (never raises)."""
    if not INDEX_PATH.exists():
        return "## produce\n\nno drafts/index.json\n"
    i = json.loads(INDEX_PATH.read_text())
    lines = ["## produce", "", f"stock: **{i['stock']}**, next due: {i['next_due']}", ""]
    for e in i["complete"][-4:]:
        lines.append(f"- complete {e['date']} `{e['slug']}`")
    for e in i["partial"]:
        lines.append(f"- partial {e['date']} {e.get('slug')}: {', '.join(e.get('problems') or [])}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if "--summary" in sys.argv:
        print(summary_markdown())
        sys.exit(0)
    try:
        sys.exit(main())
    except ProduceError as e:
        log.error("%s", e)
        sys.exit(1)

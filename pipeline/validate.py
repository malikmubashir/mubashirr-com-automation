"""Completeness gate for a draft folder, and the manifest that proves it.

A draft is COMPLETE only when `drafts/<date>/manifest.json` exists and every
file it lists still hashes to the recorded sha256. Nothing downstream (the
daily delivery task, distribution) may act on a draft without a verified
manifest. This file is the single contract between production and publishing.

Usage:
    python -m pipeline.validate --date 2026-10-10            # report only
    python -m pipeline.validate --date 2026-10-10 --write    # validate, then write manifest.json
    python -m pipeline.validate --date 2026-10-10 --verify   # check an existing manifest's hashes
    python -m pipeline.validate --date 2026-10-10 --check-live  # also ask the live site for slug/title collisions

Exit code 0 = complete, 1 = problems (listed on stdout).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .agents.common import DRAFTS, env

log = logging.getLogger("validate")

MANIFEST_SCHEMA_VERSION = 1
IMAGE_SHOTS = ("hero", "ingredients", "process", "plated")
# The mu-plugin on the host injects body images by matching these exact H2s
# after Markdown->HTML conversion, so the Markdown must carry them verbatim.
REQUIRED_H2 = ("## Ingredients", "## Method", "## Variations")
MIN_WORDS = 1000
MIN_IMAGE_BYTES = 30_000
MIN_IMAGE_WIDTH = 800
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
TEXT_FILES = ("meta.json", "post.md", "schema.json")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_saturday(d: date) -> bool:
    return d.weekday() == 5


def _strip_front_matter(md: str) -> str:
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return md


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception as e:  # noqa: BLE001 - any decode failure is a validation failure
        log.warning("Cannot decode %s: %s", path.name, e)
        return None


def other_drafts_index(exclude: Path) -> list[tuple[str, str, str]]:
    """(date, slug, title) for every other draft that has a meta.json."""
    out = []
    for d in sorted(DRAFTS.iterdir()) if DRAFTS.exists() else []:
        if d == exclude or not d.is_dir():
            continue
        m = d / "meta.json"
        if not m.exists():
            continue
        try:
            meta = json.loads(m.read_text())
        except json.JSONDecodeError:
            continue
        out.append((d.name, str(meta.get("slug", "")).lower(), str(meta.get("title", "")).lower()))
    return out


def live_site_collisions(slug: str, title: str) -> list[str] | None:
    """Ask the live site whether slug/title already exist in any status.

    Returns a list of problems, or None when the site could not be queried
    (GitHub Actions egress is frequently challenged by the host's Cloudflare
    setup, so unreachable is a warning, not a failure).
    """
    import requests

    base = env("WP_BASE_URL").rstrip("/")
    user, pw = env("WP_USER"), env("WP_APP_PASSWORD")
    if not (base and user and pw):
        return None
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/150.0 Safari/537.36")
    try:
        r = requests.get(
            f"{base}/wp-json/wp/v2/posts",
            params={"status": "publish,draft,future,pending,private", "context": "edit",
                    "per_page": 100, "_fields": "slug,title"},
            auth=(user, pw), headers={"User-Agent": ua}, timeout=20,
        )
        if r.status_code != 200:
            log.warning("Live-site check skipped: HTTP %s", r.status_code)
            return None
        posts = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("Live-site check skipped: %s", e)
        return None
    problems = []
    for p in posts:
        if p.get("slug", "").lower() == slug.lower():
            problems.append(f"slug '{slug}' already exists on the live site")
        t = p.get("title", {})
        t = t.get("raw") or t.get("rendered") or "" if isinstance(t, dict) else str(t)
        if t.strip().lower() == title.strip().lower():
            problems.append(f"title '{title}' already exists on the live site")
    return problems


def validate_draft(dd: Path, *, check_live: bool = False) -> list[str]:
    """Return a list of problems. Empty list means the draft is complete."""
    problems: list[str] = []

    try:
        d = date.fromisoformat(dd.name)
        if not is_saturday(d):
            problems.append(f"folder date {dd.name} is not a Saturday")
    except ValueError:
        problems.append(f"folder name {dd.name} is not YYYY-MM-DD")

    # --- meta.json -------------------------------------------------------
    meta_path = dd / "meta.json"
    if not meta_path.exists():
        return problems + ["meta.json missing"]
    try:
        meta = json.loads(meta_path.read_text())
    except json.JSONDecodeError as e:
        return problems + [f"meta.json is not valid JSON: {e}"]

    for key in ("title", "slug", "meta_description", "categories", "tags", "image_briefs"):
        if not meta.get(key):
            problems.append(f"meta.json missing or empty: {key}")
    slug = str(meta.get("slug", ""))
    title = str(meta.get("title", ""))
    if slug and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        problems.append(f"slug is not clean kebab-case: {slug!r}")
    if len(slug) > 80:
        problems.append("slug longer than 80 chars")

    briefs = meta.get("image_briefs") or []
    shots = [b.get("shot") for b in briefs if isinstance(b, dict)]
    if sorted(shots) != sorted(IMAGE_SHOTS):
        problems.append(f"image_briefs must cover exactly {IMAGE_SHOTS}, got {shots}")
    for b in briefs:
        if not isinstance(b, dict):
            continue
        if not str(b.get("prompt", "")).strip():
            problems.append(f"image brief '{b.get('shot')}' has no prompt (Visual would crash)")
        if not str(b.get("alt", "")).strip():
            problems.append(f"image brief '{b.get('shot')}' has no alt text")

    # --- post.md ---------------------------------------------------------
    post_path = dd / "post.md"
    if not post_path.exists():
        problems.append("post.md missing")
    else:
        md = post_path.read_text()
        if not md.startswith("---"):
            problems.append("post.md has no YAML front matter")
        body = _strip_front_matter(md)
        words = len(body.split())
        if words < MIN_WORDS:
            problems.append(f"post.md body too short: {words} words (< {MIN_WORDS})")
        for h in REQUIRED_H2:
            if not re.search(rf"^{re.escape(h)}\s*$", body, flags=re.MULTILINE):
                problems.append(f"post.md missing exact heading line '{h}'")
        if "@context" in body:
            problems.append("post.md contains JSON-LD (@context); schema must stay in schema.json")

    # --- schema.json -----------------------------------------------------
    schema_path = dd / "schema.json"
    if not schema_path.exists():
        problems.append("schema.json missing")
    else:
        try:
            schema = json.loads(schema_path.read_text())
            if schema.get("@type") != "Recipe":
                problems.append("schema.json @type is not Recipe")
        except json.JSONDecodeError as e:
            problems.append(f"schema.json is not valid JSON: {e}")

    # --- images ----------------------------------------------------------
    for shot in IMAGE_SHOTS:
        p = dd / "images" / f"{shot}.png"
        if not p.exists():
            problems.append(f"images/{shot}.png missing")
            continue
        size = p.stat().st_size
        if size < MIN_IMAGE_BYTES:
            problems.append(f"images/{shot}.png too small: {size} bytes")
        with p.open("rb") as f:
            magic = f.read(8)
        if magic[:8] != PNG_MAGIC and magic[:3] != JPEG_MAGIC:
            problems.append(f"images/{shot}.png is neither PNG nor JPEG")
            continue
        # fal.ai returns JPEG bytes under the .png name. WordPress detects the
        # real type and corrects the extension on upload (proven weekly since
        # 2026-09), so this is a note, not a failure. Do not re-encode: PNG
        # would quadruple the repo growth for no visible gain.
        dims = _image_dimensions(p)
        if dims is None:
            problems.append(f"images/{shot}.png cannot be decoded")
        elif dims[0] < MIN_IMAGE_WIDTH:
            problems.append(f"images/{shot}.png too narrow: {dims[0]}px")

    # --- uniqueness across the repo -------------------------------------
    for other_date, other_slug, other_title in other_drafts_index(dd):
        if slug and other_slug == slug.lower():
            problems.append(f"slug '{slug}' already used by drafts/{other_date}")
        if title and other_title == title.lower():
            problems.append(f"title '{title}' already used by drafts/{other_date}")

    if check_live and slug and title:
        live = live_site_collisions(slug, title)
        if live:
            problems.extend(live)

    return problems


def manifest_files(dd: Path) -> list[Path]:
    files = [dd / name for name in TEXT_FILES]
    files += [dd / "images" / f"{shot}.png" for shot in IMAGE_SHOTS]
    return files


def write_manifest(dd: Path) -> dict:
    meta = json.loads((dd / "meta.json").read_text())
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "date": dd.name,
        "slug": meta["slug"],
        "title": meta["title"],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {
            str(p.relative_to(dd)): {"sha256": sha256_of(p), "bytes": p.stat().st_size}
            for p in manifest_files(dd)
        },
    }
    (dd / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_manifest(dd: Path) -> list[str]:
    """Problems with an existing manifest (missing, malformed, or hash drift)."""
    mp = dd / "manifest.json"
    if not mp.exists():
        return ["manifest.json missing"]
    try:
        m = json.loads(mp.read_text())
    except json.JSONDecodeError as e:
        return [f"manifest.json invalid JSON: {e}"]
    problems = []
    if m.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        problems.append(f"manifest schema_version {m.get('schema_version')} != {MANIFEST_SCHEMA_VERSION}")
    expected = {str(p.relative_to(dd)) for p in manifest_files(dd)}
    listed = set((m.get("files") or {}).keys())
    for missing in sorted(expected - listed):
        problems.append(f"manifest does not list {missing}")
    for rel, info in (m.get("files") or {}).items():
        p = dd / rel
        if not p.exists():
            problems.append(f"{rel} listed in manifest but missing on disk")
        elif sha256_of(p) != info.get("sha256"):
            problems.append(f"{rel} changed since manifest was written")
    return problems


def is_complete(dd: Path) -> bool:
    return dd.is_dir() and not verify_manifest(dd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="draft folder date, YYYY-MM-DD")
    ap.add_argument("--write", action="store_true", help="write manifest.json when validation passes")
    ap.add_argument("--verify", action="store_true", help="verify an existing manifest instead of validating content")
    ap.add_argument("--check-live", action="store_true", help="also check slug/title against the live site")
    args = ap.parse_args(argv)

    dd = DRAFTS / args.date
    if not dd.is_dir():
        print(f"FAIL drafts/{args.date}: folder does not exist")
        return 1

    problems = verify_manifest(dd) if args.verify else validate_draft(dd, check_live=args.check_live)
    if problems:
        print(f"FAIL drafts/{args.date}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if args.write:
        m = write_manifest(dd)
        print(f"OK drafts/{args.date}: manifest written ({len(m['files'])} files)")
    else:
        print(f"OK drafts/{args.date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

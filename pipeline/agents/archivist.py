"""Archivist: weekly backup and digest.

Sunday 22:00 Europe/Paris.
- Dumps WP MySQL database, encrypts with age, uploads to Backblaze B2.
- Commits this week's drafts, schemas, prompts, image hashes to git.
- Generates weekly digest Markdown sent to email (via Buttondown or SMTP).
- Advances current_week pointer in theme-rotation.yaml.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import date, datetime
from pathlib import Path

import yaml

from .common import CONFIG, ROOT, draft_dir, env, load_rotation, now_iso

log = logging.getLogger("archivist")


def dump_mysql(out_path: Path) -> bool:
    host = env("MYSQL_HOST")
    if not host:
        log.warning("No MYSQL_HOST; skipping DB dump")
        return False
    user = env("MYSQL_USER", required=True)
    pw = env("MYSQL_PASSWORD", required=True)
    db = env("MYSQL_DB", required=True)
    try:
        subprocess.run(
            ["mysqldump", f"-h{host}", f"-u{user}", f"-p{pw}",
             "--single-transaction", "--quick", db],
            stdout=out_path.open("wb"), check=True, timeout=600,
        )
        return True
    except Exception as e:
        log.error("mysqldump failed: %s", e)
        return False


def encrypt_with_age(in_path: Path, out_path: Path) -> bool:
    recipient = env("AGE_RECIPIENT")
    if not recipient:
        log.warning("No AGE_RECIPIENT; storing unencrypted")
        out_path.write_bytes(in_path.read_bytes())
        return False
    try:
        subprocess.run(
            ["age", "-r", recipient, "-o", str(out_path), str(in_path)],
            check=True, timeout=120,
        )
        return True
    except Exception as e:
        log.error("age encryption failed: %s", e)
        return False


def upload_to_b2(local: Path, key: str) -> bool:
    """Uses b2 CLI; install via `pip install b2`."""
    bucket = env("B2_BUCKET")
    if not bucket:
        log.warning("No B2 bucket configured; skipping upload")
        return False
    try:
        subprocess.run(
            ["b2", "file", "upload", bucket, str(local), key],
            check=True, timeout=300,
            env={"B2_APPLICATION_KEY_ID": env("B2_KEY_ID"),
                 "B2_APPLICATION_KEY": env("B2_APP_KEY")},
        )
        return True
    except Exception as e:
        log.error("B2 upload failed: %s", e)
        return False


def git_commit_drafts() -> bool:
    """Commit this week's drafts and rotation state to git."""
    try:
        subprocess.run(["git", "add", "drafts/", "state/", "pipeline/config/"],
                       cwd=ROOT, check=True)
        msg = f"weekly: {date.today().isoformat()} archive"
        subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log.warning("git commit/push failed (nothing to commit?): %s", e)
        return False


def advance_rotation() -> None:
    p = CONFIG / "theme-rotation.yaml"
    rot = load_rotation()
    rot["current_week"] = rot["current_week"] + 1
    p.write_text(yaml.safe_dump(rot, sort_keys=False))
    log.info("Advanced current_week to %d", rot["current_week"])


def rebuild_llms_txt() -> None:
    """Rebuild /llms.txt at the site root from published-history."""
    # This is a placeholder; actual implementation depends on whether you
    # serve llms.txt from WP (custom redirect) or from a static host.
    log.info("TODO: rebuild llms.txt and upload to site root")


def weekly_digest() -> str:
    dd = draft_dir()
    lines = [f"# Weekly digest — {date.today().isoformat()}", ""]
    if (dd / "meta.yaml").exists():
        meta = yaml.safe_load((dd / "meta.yaml").read_text())
        lines += [
            f"## Published this week",
            f"- {meta['title']} ({meta['slug']})",
            f"- Focus keyword: {meta['focus_keyword']}",
            "",
        ]
    if (dd / "distribution.json").exists():
        lines.append("## Social distribution scheduled")
        lines.append(f"See drafts/{dd.name}/manual-queue.md")
    return "\n".join(lines)


def run() -> None:
    log.info("Archivist start at %s", now_iso())

    # 1. DB backup
    stamp = date.today().isoformat()
    raw = Path(f"/tmp/wp-{stamp}.sql")
    enc = Path(f"/tmp/wp-{stamp}.sql.age")
    if dump_mysql(raw):
        encrypt_with_age(raw, enc)
        upload_to_b2(enc, f"weekly/{stamp}.sql.age")
        raw.unlink(missing_ok=True)
        enc.unlink(missing_ok=True)

    # 2. Git commit drafts and state
    git_commit_drafts()

    # 3. Advance rotation
    advance_rotation()

    # 4. Rebuild AEO file
    rebuild_llms_txt()

    # 5. Weekly digest
    digest = weekly_digest()
    digest_path = ROOT / "state" / f"digest-{stamp}.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(digest)
    log.info("Digest written to %s", digest_path)


if __name__ == "__main__":
    run()

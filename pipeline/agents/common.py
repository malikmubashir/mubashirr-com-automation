"""Shared utilities across all agents."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "pipeline"
CONFIG = PIPELINE / "config"
DRAFTS = ROOT / "drafts"
STATE = ROOT / "state"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {key}")
    return value or ""


def this_saturday() -> date:
    """Return the date of the upcoming Saturday (today if today is Saturday)."""
    today = date.today()
    days_until_sat = (5 - today.weekday()) % 7
    return today.fromordinal(today.toordinal() + days_until_sat)


def draft_dir(target: date | None = None) -> Path:
    d = target or this_saturday()
    out = DRAFTS / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_rotation() -> dict:
    with (CONFIG / "theme-rotation.yaml").open() as f:
        return yaml.safe_load(f)


def current_theme() -> dict:
    rot = load_rotation()
    week = rot["current_week"]
    weeks = rot["weeks"]
    return weeks[(week - 1) % len(weeks)]


def load_history() -> dict:
    STATE.mkdir(parents=True, exist_ok=True)
    p = STATE / "published-history.json"
    if not p.exists():
        return {"slugs": [], "ingredients_seen": {}}
    return json.loads(p.read_text())


def save_history(h: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "published-history.json").write_text(json.dumps(h, indent=2))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

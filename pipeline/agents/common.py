"""Shared utilities across all agents."""

from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import tempfile
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import certifi
import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "pipeline"
CONFIG = PIPELINE / "config"
CERTS = PIPELINE / "certs"
DRAFTS = ROOT / "drafts"
STATE = ROOT / "state"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

_bypass_log = logging.getLogger("cf_bypass")


# ---------------------------------------------------------------------------
# Cloudflare bypass for WP REST API calls.
#
# Problem: Cloudflare Bot Fight Mode (enabled on the host's Cloudflare
# account, which we don't control) challenges GitHub Actions requests to
# /wp-json/wp/v2/* because they come from Azure IPs and lack browser TLS
# fingerprints. Setting a browser UA wasn't enough.
#
# Fix: when WP_ORIGIN_IP is set, resolve the WP_BASE_URL host directly to the
# origin IP at the socket layer. SNI still carries the real hostname so the
# Cloudflare Origin CA certificate matches, and we pin that root for TLS
# validation. The public site continues to be served through Cloudflare;
# only our pipeline traffic skips the edge.
# ---------------------------------------------------------------------------

_ORIG_GETADDRINFO = socket.getaddrinfo
_WP_CA_BUNDLE_PATH: str | None = None


def _install_origin_dns_override() -> None:
    origin_ip = os.getenv("WP_ORIGIN_IP", "").strip()
    base_url = os.getenv("WP_BASE_URL", "").strip()
    if not origin_ip or not base_url:
        return

    target_host = urlparse(base_url if "://" in base_url else f"https://{base_url}").hostname
    if not target_host:
        return

    # WP_ORIGIN_PORT lets us redirect 443 to an SSH tunnel on localhost.
    # Needed because the host's firewall (or upstream) silently drops TCP
    # SYNs from GitHub Actions Azure egress. We tunnel through SSH (which
    # the firewall accepts on port 22) and land at localhost:8443 -> origin:443.
    try:
        override_port = int(os.getenv("WP_ORIGIN_PORT", "0"))
    except ValueError:
        override_port = 0

    def _resolve(host, port, *args, **kwargs):
        if host == target_host:
            dest_port = override_port or port
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (origin_ip, dest_port))]
        return _ORIG_GETADDRINFO(host, port, *args, **kwargs)

    socket.getaddrinfo = _resolve
    if override_port:
        _bypass_log.info("Origin bypass active: %s -> %s:%d", target_host, origin_ip, override_port)
    else:
        _bypass_log.info("Origin bypass active: %s -> %s", target_host, origin_ip)


def _build_wp_ca_bundle() -> str | None:
    """Concatenate certifi's bundle with Cloudflare Origin CA roots.

    Returns a path usable as `requests.Session.verify`. None if bypass is off.
    """
    global _WP_CA_BUNDLE_PATH
    if _WP_CA_BUNDLE_PATH:
        return _WP_CA_BUNDLE_PATH
    if not os.getenv("WP_ORIGIN_IP", "").strip():
        return None

    parts = [Path(certifi.where()).read_text()]
    for name in ("origin-ca-rsa-root.pem", "origin-ca-ecc-root.pem"):
        p = CERTS / name
        if p.exists():
            parts.append(p.read_text())
        else:
            _bypass_log.warning("Missing pinned CA bundle: %s", p)

    fd, path = tempfile.mkstemp(prefix="wp-ca-", suffix=".pem")
    os.write(fd, "\n".join(parts).encode())
    os.close(fd)
    _WP_CA_BUNDLE_PATH = path
    return path


def wp_ca_bundle() -> str | bool:
    """Return path to a CA bundle that trusts CF Origin CA + public roots.

    When WP_ORIGIN_IP is unset (production / local dev hitting the apex via
    Cloudflare), return True so `requests` uses the system default.
    """
    path = _build_wp_ca_bundle()
    return path if path else True


_install_origin_dns_override()


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
    """Resolve the draft directory.

    Precedence: explicit `target` arg > `DRAFT_DATE` env var (YYYY-MM-DD) >
    upcoming Saturday. The env var is useful for one-off re-runs and for
    backfilling images against a past Saturday's draft.
    """
    if target is None:
        override = os.getenv("DRAFT_DATE", "").strip()
        if override:
            target = date.fromisoformat(override)
        else:
            target = this_saturday()
    out = DRAFTS / target.isoformat()
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

"""Freshness policy helpers for continuity artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

from .state_snapshot import hermes_home


DEFAULT_MAX_CHECKPOINT_AGE_SEC = 86400
DEFAULT_MAX_REPORT_AGE_SEC = 21600


def parse_iso8601_utc(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except Exception:
        return None


def load_continuity_freshness_policy(home: Path | None = None) -> Dict[str, int]:
    home = home or hermes_home()
    config_path = home / "config.yaml"
    continuity: Dict[str, Any] = {}
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            continuity = raw.get("continuity") or {}
        except Exception:
            continuity = {}

    def _int_value(key: str, default: int) -> int:
        try:
            value = int(continuity.get(key, default))
            return max(1, value)
        except Exception:
            return default

    return {
        "max_checkpoint_age_sec": _int_value("max_checkpoint_age_sec", DEFAULT_MAX_CHECKPOINT_AGE_SEC),
        "max_report_age_sec": _int_value("max_report_age_sec", DEFAULT_MAX_REPORT_AGE_SEC),
    }


def freshness_status(
    generated_at: str | None,
    *,
    max_age_sec: int,
    now: datetime | None = None,
) -> Dict[str, Any]:
    observed_at = parse_iso8601_utc(generated_at)
    if observed_at is None:
        return {
            "present": bool(generated_at),
            "generated_at": generated_at,
            "age_sec": None,
            "max_age_sec": max_age_sec,
            "stale": True,
            "reason": "missing_or_invalid_generated_at",
        }
    now_dt = now or datetime.now(timezone.utc)
    age_sec = max(0, int((now_dt - observed_at).total_seconds()))
    stale = age_sec > max_age_sec
    return {
        "present": True,
        "generated_at": generated_at,
        "age_sec": age_sec,
        "max_age_sec": max_age_sec,
        "stale": stale,
        "reason": "stale" if stale else "fresh",
    }

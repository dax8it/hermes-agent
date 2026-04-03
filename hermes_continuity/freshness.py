"""Freshness policy helpers for continuity artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

from .state_snapshot import hermes_home


DEFAULT_MAX_CHECKPOINT_AGE_SEC = 86400
DEFAULT_MAX_REPORT_AGE_SEC = 21600


_REPORT_FRESHNESS_PROFILES = {
    "single-machine-readiness": {
        "category": "guarded_surface",
        "stale_label": "STALE",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Single-machine readiness should be refreshed before long operator runs.",
    },
    "verify": {
        "category": "guarded_proof",
        "stale_label": "STALE",
        "stale_operator_state": "FAIL",
        "blocks_on_stale": True,
        "summary": "Verify is a guarded proof; stale verify means checkpoint custody needs a fresh pass.",
    },
    "rehydrate": {
        "category": "guarded_proof",
        "stale_label": "NEEDS_RE-EXERCISE",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Rehydrate is safe but should be re-exercised against the newest checkpoint before relying on it.",
    },
    "gateway-reset": {
        "category": "event_receipt",
        "stale_label": "NOT_RECENTLY_EXERCISED",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Gateway reset receipts are event-driven; stale means no recent reset exercise, not broken continuity.",
    },
    "cron-continuity": {
        "category": "event_receipt",
        "stale_label": "NOT_RECENTLY_EXERCISED",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Cron continuity receipts are event-driven; stale means the cron recovery path has not run recently.",
    },
    "external-memory-ingest": {
        "category": "event_receipt",
        "stale_label": "NOT_RECENTLY_EXERCISED",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "External-memory ingest receipts are event-driven and only refresh when that path is exercised.",
    },
    "external-memory-promotion": {
        "category": "event_receipt",
        "stale_label": "NOT_RECENTLY_EXERCISED",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "External-memory promotion receipts are event-driven and only refresh when that path is exercised.",
    },
    "external-memory-review": {
        "category": "event_receipt",
        "stale_label": "NOT_RECENTLY_EXERCISED",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "External-memory review receipts are event-driven and only refresh when that path is exercised.",
    },
    "knowledge-compile": {
        "category": "derived_surface",
        "stale_label": "STALE",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Knowledge compile is derived operator context; stale means the continuity knowledge layer should be refreshed.",
    },
    "knowledge-lint": {
        "category": "derived_surface",
        "stale_label": "STALE",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Knowledge lint is derived operator context; stale means contradiction and coverage checks are out of date.",
    },
    "knowledge-health": {
        "category": "derived_surface",
        "stale_label": "STALE",
        "stale_operator_state": "WARN",
        "blocks_on_stale": False,
        "summary": "Knowledge health is derived operator context and should refresh when continuity reports change.",
    },
}


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


def continuity_report_freshness_semantics(
    target: str,
    freshness: Dict[str, Any] | None,
) -> Dict[str, Any]:
    profile = _REPORT_FRESHNESS_PROFILES.get(
        target,
        {
            "category": "guarded_surface",
            "stale_label": "STALE",
            "stale_operator_state": "WARN",
            "blocks_on_stale": False,
            "summary": "Continuity freshness should be reviewed before operator use.",
        },
    )
    if not freshness:
        return {
            "category": profile["category"],
            "display_state": "MISSING",
            "operator_state": "WARN",
            "blocks_on_stale": profile["blocks_on_stale"],
            "summary": profile["summary"],
        }
    if freshness.get("stale"):
        return {
            "category": profile["category"],
            "display_state": profile["stale_label"],
            "operator_state": profile["stale_operator_state"],
            "blocks_on_stale": profile["blocks_on_stale"],
            "summary": profile["summary"],
        }
    return {
        "category": profile["category"],
        "display_state": "FRESH",
        "operator_state": "OK",
        "blocks_on_stale": profile["blocks_on_stale"],
        "summary": profile["summary"],
    }

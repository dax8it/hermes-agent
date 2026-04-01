"""Report writing helpers for Hermes continuity artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

from utils import atomic_json_write

from .schema import now_utc, slug_ts


def write_json_report(base_dir: Path, prefix: str, payload: Dict[str, Any]) -> Tuple[str, str]:
    base_dir.mkdir(parents=True, exist_ok=True)
    ts = slug_ts(now_utc())
    report_path = base_dir / f"{prefix}-{ts}.json"
    latest_path = base_dir / f"{prefix}-latest.json"
    atomic_json_write(report_path, payload)
    atomic_json_write(latest_path, payload)
    return str(report_path.resolve()), str(latest_path.resolve())

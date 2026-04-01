"""Continuity guard helpers for protected transitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home

from .checkpoint import generate_checkpoint
from .reporting import write_json_report
from .schema import iso_z, now_utc
from .verify import verify_latest_checkpoint


class ContinuityGateError(RuntimeError):
    """Raised when a protected transition is blocked by continuity policy."""


def checkpoint_and_verify_before_compaction(*, session_id: str, cwd: Path) -> Dict[str, Any]:
    checkpoint = generate_checkpoint(session_id=session_id, cwd=cwd)
    verify = verify_latest_checkpoint()
    ok = verify.get("status") in {"PASS", "WARN"}
    payload = {
        "generated_at": iso_z(now_utc()),
        "transition": "compaction",
        "session_id": session_id,
        "cwd": str(Path(cwd).resolve()),
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "checkpoint": checkpoint,
        "verify": verify,
        "status": verify.get("status"),
        "blocked": not ok,
        "warnings": verify.get("warnings") or [],
        "errors": verify.get("errors") or [],
    }
    report_path, latest_path = write_json_report(
        get_hermes_home().resolve() / "continuity" / "reports",
        "compact-gate",
        payload,
    )
    payload["report_path"] = report_path
    payload["latest_report_path"] = latest_path
    payload["ok"] = ok
    return payload

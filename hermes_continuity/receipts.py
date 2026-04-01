"""Continuity receipt writers for gateway and cron transitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home

from .reporting import write_json_report
from .schema import iso_z, now_utc


def write_gateway_reset_receipt(
    *,
    session_key: str,
    old_session_id: str,
    new_session_id: str,
    reason: str,
    platform: str,
    chat_type: str,
    had_activity: bool,
    automatic: bool,
) -> Dict[str, Any]:
    payload = {
        "generated_at": iso_z(now_utc()),
        "kind": "gateway_session_reset",
        "session_key": session_key,
        "old_session_id": old_session_id,
        "new_session_id": new_session_id,
        "reason": reason,
        "platform": platform,
        "chat_type": chat_type,
        "had_activity": had_activity,
        "automatic": automatic,
        "status": "PASS",
    }
    report_path, latest_path = write_json_report(
        get_hermes_home().resolve() / "continuity" / "reports",
        "gateway-reset",
        payload,
    )
    payload["report_path"] = report_path
    payload["latest_report_path"] = latest_path
    return payload


def write_cron_continuity_receipt(
    *,
    event: str,
    job_id: str,
    job_name: Optional[str],
    schedule_kind: Optional[str],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "generated_at": iso_z(now_utc()),
        "kind": "cron_continuity",
        "event": event,
        "job_id": job_id,
        "job_name": job_name,
        "schedule_kind": schedule_kind,
        "details": details,
        "status": "PASS",
    }
    report_path, latest_path = write_json_report(
        get_hermes_home().resolve() / "continuity" / "reports",
        "cron-continuity",
        payload,
    )
    payload["report_path"] = report_path
    payload["latest_report_path"] = latest_path
    return payload

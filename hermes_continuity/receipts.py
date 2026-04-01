"""Continuity receipt writers for gateway and cron transitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home

from .freshness import freshness_status, load_continuity_freshness_policy
from .incidents import create_or_update_continuity_incident
from .reporting import write_json_report
from .schema import iso_z, now_utc


def _read_latest_report(prefix: str) -> Dict[str, Any] | None:
    path = get_hermes_home().resolve() / "continuity" / "reports" / f"{prefix}-latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def write_gateway_reset_anomaly_incident(
    *,
    session_key: str,
    old_session_id: str,
    new_session_id: str,
    reason: str,
    automatic: bool,
    error: str,
) -> Dict[str, Any]:
    return create_or_update_continuity_incident(
        verdict="DEGRADED_CONTINUE",
        transition_type="gateway_reset",
        protected_transitions_blocked=False,
        summary="Gateway reset continuity receipt/reporting failed.",
        exact_blocker=error,
        failure_planes=["gate_coverage"],
        commands_run=[f"write_gateway_reset_receipt({session_key})"],
        artifacts_inspected=[old_session_id, new_session_id, reason, "automatic" if automatic else "manual"],
        event="gateway_receipt_failed",
    )



def write_cron_continuity_anomaly_incident(
    *,
    event: str,
    job_id: str,
    job_name: Optional[str],
    schedule_kind: Optional[str],
    error: str,
) -> Dict[str, Any]:
    return create_or_update_continuity_incident(
        verdict="DEGRADED_CONTINUE",
        transition_type="cron_continuity",
        protected_transitions_blocked=False,
        summary="Cron continuity receipt/reporting failed.",
        exact_blocker=error,
        failure_planes=["gate_coverage"],
        commands_run=[f"write_cron_continuity_receipt({job_id})"],
        artifacts_inspected=[job_id, job_name or "", schedule_kind or "", event],
        event="cron_receipt_failed",
    )



def detect_missing_gateway_reset_receipt(
    *,
    session_key: str,
    old_session_id: str,
    new_session_id: str,
    reason: str,
    automatic: bool,
) -> Dict[str, Any]:
    latest = _read_latest_report("gateway-reset")
    issues = []
    if latest is None:
        issues.append("Missing latest gateway reset receipt")
    else:
        freshness = freshness_status(
            latest.get("generated_at"),
            max_age_sec=load_continuity_freshness_policy()["max_report_age_sec"],
        )
        if freshness["stale"]:
            issues.append("Gateway reset receipt is stale")
        if latest.get("old_session_id") != old_session_id:
            issues.append("Gateway reset receipt old_session_id mismatch")
        if latest.get("new_session_id") != new_session_id:
            issues.append("Gateway reset receipt new_session_id mismatch")
        if latest.get("reason") != reason:
            issues.append("Gateway reset receipt reason mismatch")
        if bool(latest.get("automatic")) != bool(automatic):
            issues.append("Gateway reset receipt automatic flag mismatch")
    if issues:
        incident = create_or_update_continuity_incident(
            verdict="DEGRADED_CONTINUE",
            transition_type="gateway_reset",
            protected_transitions_blocked=False,
            summary="Expected gateway reset continuity receipt was missing or inconsistent.",
            exact_blocker=issues[0],
            failure_planes=["gate_coverage"],
            commands_run=[f"detect_missing_gateway_reset_receipt({session_key})"],
            artifacts_inspected=[old_session_id, new_session_id, reason, "automatic" if automatic else "manual"],
            event="gateway_receipt_missing_or_inconsistent",
        )
        return {"status": "MISSING", "issues": issues, "incident_id": incident.get("incident_id")}
    return {"status": "PRESENT", "issues": []}



def detect_missing_cron_continuity_receipt(
    *,
    event: str,
    job_id: str,
    job_name: Optional[str],
    schedule_kind: Optional[str],
) -> Dict[str, Any]:
    latest = _read_latest_report("cron-continuity")
    issues = []
    if latest is None:
        issues.append("Missing latest cron continuity receipt")
    else:
        freshness = freshness_status(
            latest.get("generated_at"),
            max_age_sec=load_continuity_freshness_policy()["max_report_age_sec"],
        )
        if freshness["stale"]:
            issues.append("Cron continuity receipt is stale")
        if latest.get("event") != event:
            issues.append("Cron continuity receipt event mismatch")
        if latest.get("job_id") != job_id:
            issues.append("Cron continuity receipt job_id mismatch")
        if latest.get("schedule_kind") != schedule_kind:
            issues.append("Cron continuity receipt schedule_kind mismatch")
    if issues:
        incident = create_or_update_continuity_incident(
            verdict="DEGRADED_CONTINUE",
            transition_type="cron_continuity",
            protected_transitions_blocked=False,
            summary="Expected cron continuity receipt was missing or inconsistent.",
            exact_blocker=issues[0],
            failure_planes=["gate_coverage"],
            commands_run=[f"detect_missing_cron_continuity_receipt({job_id})"],
            artifacts_inspected=[job_id, job_name or "", schedule_kind or "", event],
            event="cron_receipt_missing_or_inconsistent",
        )
        return {"status": "MISSING", "issues": issues, "incident_id": incident.get("incident_id")}
    return {"status": "PRESENT", "issues": []}



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

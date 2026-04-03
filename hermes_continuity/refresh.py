"""Automatic continuity refresh helpers for gateway reset transitions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from hermes_constants import get_hermes_home

from .checkpoint import generate_checkpoint
from .incidents import create_or_update_continuity_incident
from .knowledge import refresh_continuity_knowledge_plane
from .readiness import verify_single_machine_readiness
from .rehydrate import rehydrate_latest_checkpoint
from .reporting import write_json_report
from .schema import iso_z, now_utc
from .verify import verify_latest_checkpoint


def _resolve_runtime_cwd(explicit_cwd: str | Path | None = None) -> Path:
    if explicit_cwd:
        return Path(explicit_cwd).expanduser().resolve()

    for env_name in ("TERMINAL_CWD", "MESSAGING_CWD"):
        value = os.environ.get(env_name)
        if value and str(value).strip():
            return Path(value).expanduser().resolve()

    home = get_hermes_home().resolve()
    config_path = home / "config.yaml"
    if config_path.exists():
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            payload = {}
        cwd_value = ((payload.get("terminal") or {}).get("cwd") or "").strip()
        if cwd_value:
            return Path(cwd_value).expanduser().resolve()

    return Path.cwd().resolve()


def _augment_gateway_reset_receipt(payload: Dict[str, Any]) -> None:
    report_path = payload.get("gateway_reset_report_path")
    latest_path = payload.get("gateway_reset_latest_path")
    if not report_path or not latest_path:
        return

    update = {
        "post_reset_refresh": {
            "status": payload.get("status"),
            "generated_at": payload.get("generated_at"),
            "checkpoint_id": (payload.get("checkpoint") or {}).get("checkpoint_id"),
            "verify_status": (payload.get("verify") or {}).get("status"),
            "rehydrate_status": (payload.get("rehydrate") or {}).get("status"),
            "readiness_status": (payload.get("readiness") or {}).get("status"),
            "report_path": payload.get("latest_report_path"),
            "cwd": payload.get("cwd"),
        }
    }

    for raw_path in (report_path, latest_path):
        path = Path(raw_path)
        if not path.exists():
            continue
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt.update(update)
        path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")


def run_post_reset_continuity_refresh(
    *,
    session_key: str,
    session_id: str,
    reason: str,
    automatic: bool,
    gateway_reset_report_path: str | None = None,
    gateway_reset_latest_path: str | None = None,
    cwd: str | Path | None = None,
) -> Dict[str, Any]:
    home = get_hermes_home().resolve()
    cwd_path = _resolve_runtime_cwd(cwd)

    checkpoint = generate_checkpoint(session_id=session_id, cwd=cwd_path)
    verify = verify_latest_checkpoint()
    rehydrate = rehydrate_latest_checkpoint(target_session_id=session_id)
    readiness = verify_single_machine_readiness(home)
    knowledge = refresh_continuity_knowledge_plane(home=home)
    knowledge_health = knowledge.get("health") or {}

    failing_steps = [
        name
        for name, result in (
            ("checkpoint", checkpoint),
            ("verify", verify),
            ("rehydrate", rehydrate),
            ("single-machine-readiness", readiness),
        )
        if str(result.get("status") or "").upper() == "FAIL"
    ]
    warnings = [
        name
        for name, result in (
            ("verify", verify),
            ("rehydrate", rehydrate),
            ("single-machine-readiness", readiness),
        )
        if str(result.get("status") or "").upper() == "WARN"
    ]
    informational_warnings = [
        name
        for name, result in (
            ("knowledge-health", knowledge_health),
        )
        if str(result.get("status") or "").upper() in {"WARN", "FAIL"}
    ]
    status = "FAIL" if failing_steps else ("WARN" if warnings else "PASS")
    payload = {
        "generated_at": iso_z(now_utc()),
        "kind": "post_reset_continuity_refresh",
        "transition_type": "gateway_reset",
        "status": status,
        "session_key": session_key,
        "session_id": session_id,
        "reason": reason,
        "automatic": automatic,
        "cwd": str(cwd_path),
        "operator_summary": (
            "Automatic post-reset continuity refresh completed."
            if status == "PASS"
            else "Automatic post-reset continuity refresh completed with warnings."
            if status == "WARN"
            else "Automatic post-reset continuity refresh failed."
        )
        + (
            " Knowledge Plane needs operator review, but that derived layer did not block the refresh."
            if informational_warnings
            else ""
        ),
        "checkpoint": checkpoint,
        "verify": verify,
        "rehydrate": rehydrate,
        "readiness": readiness,
        "knowledge": knowledge,
        "failing_steps": failing_steps,
        "warning_steps": warnings,
        "informational_warning_steps": informational_warnings,
        "gateway_reset_report_path": gateway_reset_report_path,
        "gateway_reset_latest_path": gateway_reset_latest_path,
    }
    report_path, latest_path = write_json_report(home / "continuity" / "reports", "post-reset-refresh", payload)
    payload["report_path"] = report_path
    payload["latest_report_path"] = latest_path
    _augment_gateway_reset_receipt(payload)

    if status == "FAIL":
        create_or_update_continuity_incident(
            verdict="DEGRADED_CONTINUE",
            transition_type="gateway_reset",
            protected_transitions_blocked=False,
            summary="Automatic post-reset continuity refresh failed.",
            exact_blocker=", ".join(failing_steps) or "unknown_post_reset_refresh_failure",
            exact_remediation="Inspect the post-reset refresh report, then rerun checkpoint -> verify -> rehydrate from the new session.",
            failure_planes=["gate_coverage", "integrity"],
            commands_run=["run_post_reset_continuity_refresh"],
            artifacts_inspected=[report_path, gateway_reset_latest_path or "", gateway_reset_report_path or ""],
            event="post_reset_refresh_failed",
        )
    return payload

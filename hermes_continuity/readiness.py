"""Single-machine readiness gate for Hermes continuity."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

from hermes_constants import get_hermes_home

from .freshness import continuity_report_freshness_semantics, load_continuity_freshness_policy
from .incidents import continuity_status_snapshot
from .receipts import self_heal_operator_event_surfaces
from .reporting import write_json_report
from .schema import SCHEMA_VERSION, iso_z, now_utc


def _load_benchmark_payload() -> Dict[str, Any]:
    bench_path = Path(__file__).resolve().parents[1] / "bench" / "continuity" / "run.py"
    try:
        spec = importlib.util.spec_from_file_location("hermes_continuity_bench_run_readiness", bench_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load continuity benchmark module: {bench_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run_benchmark()
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": str(exc),
            "passed_count": 0,
            "failed_count": 0,
            "case_count": 0,
            "results": [],
        }


def _profile_name(home: Path) -> str:
    default_home = (Path.home() / ".hermes").resolve()
    profiles_root = (default_home / "profiles").resolve()
    resolved = home.resolve()
    if resolved == default_home:
        return "default"
    try:
        rel = resolved.relative_to(profiles_root)
        if len(rel.parts) == 1:
            return rel.parts[0]
    except ValueError:
        pass
    return "custom"


def _report_ok(reports: Dict[str, Any], name: str) -> bool:
    item = reports.get(name) or {}
    freshness = item.get("freshness") or {}
    return bool(item.get("exists")) and item.get("status") == "PASS" and not freshness.get("stale")


def _report_issue(reports: Dict[str, Any], name: str) -> str:
    item = reports.get(name) or {}
    freshness = item.get("freshness") or {}
    if not item.get("exists"):
        return "missing"
    if freshness.get("stale"):
        return "stale"
    if item.get("status") != "PASS":
        return str(item.get("status") or "unknown").lower()
    return "ok"


def _report_status(reports: Dict[str, Any], name: str) -> str:
    item = reports.get(name) or {}
    return str(item.get("status") or "unknown").upper()


def _report_exists_and_fresh(reports: Dict[str, Any], name: str) -> bool:
    item = reports.get(name) or {}
    freshness = item.get("freshness") or {}
    return bool(item.get("exists")) and not freshness.get("stale")


def _high_pressure_sessions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if (row.get("context_used_pct") or 0) >= 0.8]


def _readiness_session_rows(snapshot: Dict[str, Any], current_profile: str) -> List[Dict[str, Any]]:
    rows = list(snapshot.get("sessions") or [])
    if not rows:
        return []

    current_profile_rows = rows
    if any("activity_state" in row for row in rows):
        active_rows = [row for row in rows if row.get("activity_state") == "ACTIVE"]
    else:
        active_rows = rows

    if any(("is_current_profile" in row) or ("profile_name" in row) for row in rows):
        current_profile_rows = [
            row for row in rows if row.get("is_current_profile") or row.get("profile_name") == current_profile
        ]
        current_rows = [
            row
            for row in active_rows
            if row.get("is_current_profile") or row.get("profile_name") == current_profile
        ]
        if current_rows:
            return current_rows

    if active_rows:
        return active_rows
    if current_profile_rows:
        return current_profile_rows
    return rows


def build_single_machine_readiness_report(home: Path | None = None) -> Dict[str, Any]:
    home = (home or get_hermes_home()).resolve()
    current_profile = _profile_name(home)
    self_heal_operator_event_surfaces(home=home)
    snapshot = continuity_status_snapshot(home)
    policy = load_continuity_freshness_policy(home)

    from .dashboard import build_continuity_incident_snapshot, build_continuity_sessions_snapshot

    sessions_snapshot = build_continuity_sessions_snapshot()
    incident_snapshot = build_continuity_incident_snapshot()
    benchmark = _load_benchmark_payload()

    errors: List[str] = []
    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []
    reports = snapshot.get("reports") or {}
    manifest_freshness = snapshot.get("manifest_freshness") or {}
    anchor_freshness = snapshot.get("anchor_freshness") or {}
    session_rows = _readiness_session_rows(sessions_snapshot, current_profile)
    high_pressure = _high_pressure_sessions(session_rows)

    def _record(name: str, ok: bool, detail: str, *, severity: str = "error") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        if ok:
            return
        if severity == "warning":
            warnings.append(detail)
        else:
            errors.append(detail)

    _record(
        "checkpoint_manifest_fresh",
        bool(snapshot.get("manifest_exists")) and not manifest_freshness.get("stale"),
        "Latest checkpoint manifest must exist and be fresh for the active profile.",
    )
    _record(
        "anchor_fresh",
        bool(snapshot.get("anchor_exists")) and not anchor_freshness.get("stale"),
        "Latest continuity anchor must exist and be fresh for the active profile.",
    )
    _record(
        "verify_report_green",
        _report_exists_and_fresh(reports, "verify") and _report_status(reports, "verify") in {"PASS", "WARN"},
        f"verify report must be PASS/WARN and fresh (currently {_report_issue(reports, 'verify')}).",
    )
    _record(
        "rehydrate_report_green",
        _report_exists_and_fresh(reports, "rehydrate") and _report_status(reports, "rehydrate") in {"PASS", "WARN"},
        f"rehydrate report must be PASS/WARN and fresh (currently {_report_issue(reports, 'rehydrate')}).",
        severity="warning" if _report_issue(reports, "rehydrate") == "stale" else "error",
    )
    _record(
        "benchmark_green",
        benchmark.get("status") == "PASS",
        "Continuity benchmark must pass before the single-machine readiness gate is green.",
    )
    _record(
        "active_sessions_visible",
        sessions_snapshot.get("session_count", 0) > 0,
        "At least one active Hermes session must be visible to the continuity dashboard.",
    )
    _record(
        "no_open_fail_closed_incidents",
        int(incident_snapshot.get("fail_closed") or 0) == 0,
        "Open FAIL_CLOSED incidents must be resolved before declaring the machine ready.",
    )

    gateway_issue = _report_issue(reports, "gateway-reset")
    cron_issue = _report_issue(reports, "cron-continuity")
    gateway_semantics = continuity_report_freshness_semantics("gateway-reset", (reports.get("gateway-reset") or {}).get("freshness"))
    cron_semantics = continuity_report_freshness_semantics("cron-continuity", (reports.get("cron-continuity") or {}).get("freshness"))
    _record(
        "gateway_reset_surface_exercised",
        gateway_issue == "ok",
        f"gateway-reset reporting is stale or failing; refresh the gateway continuity surface before operator use ({gateway_semantics.get('display_state', 'STALE')}).",
        severity="warning" if gateway_issue in {"missing", "stale"} else "error",
    )
    _record(
        "cron_continuity_surface_exercised",
        cron_issue == "ok",
        f"cron-continuity reporting is stale or failing; refresh the cron continuity surface before operator use ({cron_semantics.get('display_state', 'STALE')}).",
        severity="warning" if cron_issue in {"missing", "stale"} else "error",
    )

    if high_pressure:
        warnings.append(
            f"{len(high_pressure)} active session(s) are above 80% context usage; compact or checkpoint soon."
        )

    if _report_status(reports, "verify") == "WARN" and _report_exists_and_fresh(reports, "verify"):
        warnings.append(
            "Verify passed with warnings; inspect the latest verify report before a long operator run."
        )

    if _report_issue(reports, "rehydrate") == "stale":
        warnings.append(
            "Rehydrate has not been re-exercised against the newest continuity checkpoint yet."
        )

    ext = snapshot.get("external_memory") or {}
    pending_external = int(ext.get("PENDING") or 0)
    quarantined_external = int(ext.get("QUARANTINED") or 0)
    if pending_external or quarantined_external:
        warnings.append(
            "External-memory queues are non-empty; review quarantined/pending candidates before calling the machine clean."
        )

    if errors:
        status = "FAIL"
        operator_summary = "Single-machine readiness failed closed. Fix the blocking continuity prerequisites below."
        remediation = [
            "Bring verify and rehydrate back to a safe fresh state.",
            "Run the continuity benchmark again.",
            "Resolve any open FAIL_CLOSED incident before dropping the control panel on top.",
        ]
    elif warnings:
        status = "WARN"
        operator_summary = "Single-machine readiness is usable with warnings, but not every operator surface has been exercised recently."
        remediation = [
            "Exercise the gateway-reset and cron-continuity surfaces if they are still marked missing.",
            "Drain or adjudicate any pending external-memory queue items.",
            "Compact or checkpoint any high-pressure sessions before a long operator run.",
        ]
    else:
        status = "PASS"
        operator_summary = "Single-machine one-human-many-agents readiness is green for the active Hermes profile."
        remediation = []

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(now_utc()),
        "kind": "single_machine_readiness",
        "status": status,
        "operator_summary": operator_summary,
        "remediation": remediation,
        "warnings": warnings,
        "errors": errors,
        "required_checks": [item["name"] for item in checks],
        "checks": checks,
        "profile": {
            "name": current_profile,
            "hermes_home": str(home),
        },
        "freshness_policy": policy,
        "checkpoint": {
            "checkpoint_id": snapshot.get("checkpoint_id"),
            "manifest_exists": snapshot.get("manifest_exists", False),
            "manifest_freshness": manifest_freshness,
            "anchor_exists": snapshot.get("anchor_exists", False),
            "anchor_freshness": anchor_freshness,
        },
        "reports": {
            name: reports.get(name)
            for name in (
                "verify",
                "rehydrate",
                "gateway-reset",
                "cron-continuity",
            )
        },
        "benchmark": {
            "status": benchmark.get("status", "ERROR"),
            "passed_count": benchmark.get("passed_count", 0),
            "failed_count": benchmark.get("failed_count", 0),
            "case_count": benchmark.get("case_count", 0),
        },
        "incidents": {
            "open": incident_snapshot.get("open", 0),
            "resolved": incident_snapshot.get("resolved", 0),
            "fail_closed": incident_snapshot.get("fail_closed", 0),
            "degraded": incident_snapshot.get("degraded", 0),
            "unsafe_pass": incident_snapshot.get("unsafe_pass", 0),
        },
        "sessions": {
            "session_count": sessions_snapshot.get("session_count", 0),
            "high_pressure_count": len(high_pressure),
            "highest_context_used_pct": max((row.get("context_used_pct") or 0) for row in session_rows) if session_rows else None,
            "active": [
                {
                    "session_key": row.get("session_key"),
                    "session_id": row.get("session_id"),
                    "platform": row.get("platform"),
                    "model": row.get("model"),
                    "context_used_pct": row.get("context_used_pct"),
                    "updated_at": row.get("updated_at"),
                }
                for row in session_rows[:5]
            ],
        },
        "external_memory": ext,
    }


def write_single_machine_readiness_report(home: Path, payload: Dict[str, Any]) -> tuple[str, str]:
    return write_json_report(home / "continuity" / "reports", "single-machine-readiness", payload)


def verify_single_machine_readiness(home: Path | None = None) -> Dict[str, Any]:
    home = (home or get_hermes_home()).resolve()
    payload = build_single_machine_readiness_report(home)
    report_path, latest_path = write_single_machine_readiness_report(home, payload)
    return {
        "status": payload.get("status"),
        "report_path": report_path,
        "latest_report_path": latest_path,
        "payload": payload,
    }


def main(argv: List[str] | None = None) -> int:
    del argv
    result = verify_single_machine_readiness()
    print(json.dumps(result["payload"], indent=2, sort_keys=True))
    return 1 if result["status"] == "FAIL" else 0

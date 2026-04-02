"""Structured continuity dashboard aggregation helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

from .incidents import continuity_status_snapshot, list_continuity_incidents
from .schema import iso_z, now_utc



def _load_benchmark_payload() -> Dict[str, Any]:
    bench_path = Path(__file__).resolve().parents[1] / "bench" / "continuity" / "run.py"
    try:
        spec = importlib.util.spec_from_file_location("hermes_continuity_bench_run", bench_path)
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



def build_continuity_incident_snapshot() -> Dict[str, Any]:
    listing = list_continuity_incidents()
    incidents = listing.get("incidents") or []
    open_incidents = [item for item in incidents if item.get("incident_state", "OPEN") == "OPEN"]
    resolved_incidents = [item for item in incidents if item.get("incident_state", "OPEN") == "RESOLVED"]

    def _open_verdict_count(verdict: str) -> int:
        return sum(1 for item in open_incidents if item.get("verdict") == verdict)

    return {
        "generated_at": iso_z(now_utc()),
        "status": listing.get("status", "OK"),
        "incident_count": listing.get("incident_count", len(incidents)),
        "open": len(open_incidents),
        "resolved": len(resolved_incidents),
        "fail_closed": _open_verdict_count("FAIL_CLOSED"),
        "degraded": _open_verdict_count("DEGRADED_CONTINUE"),
        "unsafe_pass": _open_verdict_count("UNSAFE_PASS"),
        "recent": incidents[:10],
    }



def _load_session_runtime_details(session_id: str) -> Dict[str, Any]:
    from hermes_state import SessionDB

    db = SessionDB()
    try:
        return db.get_session(session_id) or {}
    finally:
        db.close()



def _get_context_limit(model: str, base_url: str = "") -> int | None:
    from agent.model_metadata import get_model_context_length

    return get_model_context_length(model, base_url=base_url) if model else None



def build_continuity_sessions_snapshot() -> Dict[str, Any]:
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore

    config = GatewayConfig()
    store = SessionStore(sessions_dir=config.sessions_dir, config=config)
    sessions = store.list_sessions()
    rows: List[Dict[str, Any]] = []
    for entry in sessions:
        runtime = _load_session_runtime_details(entry.session_id)
        model = runtime.get("model")
        base_url = runtime.get("billing_base_url") or ""
        context_limit = _get_context_limit(model, base_url=base_url)
        total_tokens = int(entry.total_tokens or 0)
        used_pct = None
        remaining_pct = None
        if context_limit and context_limit > 0:
            used_pct = round(total_tokens / context_limit, 4)
            remaining_pct = round(max(0.0, 1.0 - used_pct), 4)
        rows.append(
            {
                "session_key": entry.session_key,
                "session_id": entry.session_id,
                "platform": entry.platform.value if entry.platform else None,
                "chat_type": entry.chat_type,
                "model": model,
                "total_tokens": total_tokens,
                "context_limit": context_limit,
                "context_used_pct": used_pct,
                "context_remaining_pct": remaining_pct,
                "updated_at": entry.updated_at.isoformat(),
                "estimated_cost_usd": entry.estimated_cost_usd,
                "cost_status": entry.cost_status,
            }
        )
    return {
        "generated_at": iso_z(now_utc()),
        "session_count": len(rows),
        "sessions": rows,
    }



def build_continuity_summary() -> Dict[str, Any]:
    snapshot = continuity_status_snapshot()
    benchmark = _load_benchmark_payload()
    incident_snapshot = build_continuity_incident_snapshot()

    return {
        "generated_at": iso_z(now_utc()),
        "status": {
            "checkpoint_id": snapshot.get("checkpoint_id"),
            "manifest": {
                "exists": snapshot.get("manifest_exists", False),
                **(snapshot.get("manifest_freshness") or {}),
            },
            "anchor": {
                "exists": snapshot.get("anchor_exists", False),
                **(snapshot.get("anchor_freshness") or {}),
            },
        },
        "reports": snapshot.get("reports") or {},
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
            "recent": incident_snapshot.get("recent", []),
        },
        "external_memory": snapshot.get("external_memory") or {},
    }

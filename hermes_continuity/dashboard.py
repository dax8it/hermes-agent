"""Structured continuity dashboard aggregation helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict

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

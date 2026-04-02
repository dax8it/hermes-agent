"""Guarded operator actions for the continuity dashboard."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .checkpoint import generate_checkpoint
from .incidents import add_note_to_continuity_incident, resolve_continuity_incident
from .rehydrate import rehydrate_latest_checkpoint
from .verify import verify_latest_checkpoint


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def _load_benchmark_payload() -> Dict[str, Any]:
    bench_path = Path(__file__).resolve().parents[1] / "bench" / "continuity" / "run.py"
    spec = importlib.util.spec_from_file_location("hermes_continuity_bench_run_actions", bench_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load continuity benchmark module: {bench_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_benchmark()



def _action_result(action: str, fn, *args, **kwargs) -> Dict[str, Any]:
    started_at = _iso_now()
    try:
        result = fn(*args, **kwargs)
        return {
            "ok": True,
            "action": action,
            "started_at": started_at,
            "finished_at": _iso_now(),
            "result": result,
            "errors": [],
        }
    except Exception as exc:
        return {
            "ok": False,
            "action": action,
            "started_at": started_at,
            "finished_at": _iso_now(),
            "result": None,
            "errors": [str(exc)],
        }



def run_checkpoint_action(session_id: str, cwd: str | None = None) -> Dict[str, Any]:
    return _action_result("checkpoint", generate_checkpoint, session_id, cwd=Path(cwd).resolve() if cwd else None)



def run_verify_action() -> Dict[str, Any]:
    return _action_result("verify", verify_latest_checkpoint)



def run_rehydrate_action(target_session_id: str) -> Dict[str, Any]:
    return _action_result("rehydrate", rehydrate_latest_checkpoint, target_session_id=target_session_id)



def run_benchmark_action() -> Dict[str, Any]:
    return _action_result("benchmark", _load_benchmark_payload)



def add_incident_note_action(incident_id: str, note: str) -> Dict[str, Any]:
    return _action_result("incident-note", add_note_to_continuity_incident, incident_id, note=note)



def resolve_incident_action(incident_id: str, resolution_summary: str) -> Dict[str, Any]:
    return _action_result("incident-resolve", resolve_continuity_incident, incident_id, resolution_summary=resolution_summary)

#!/usr/bin/env python3
"""Behavioral Hermes continuity benchmark harness.

This harness runs continuity scenarios inside isolated temporary HERMES_HOME
sandboxes so it can be executed locally and in CI without relying on the
operator's real profile state.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gateway.config import GatewayConfig, Platform, SessionResetPolicy
from gateway.session import SessionSource, SessionStore
from hermes_continuity.checkpoint import generate_checkpoint
from hermes_continuity.external_memory import (
    ingest_external_memory_candidate,
    list_external_memory_candidates,
    promote_external_memory_candidate,
)
from hermes_continuity.incidents import get_continuity_incident, list_continuity_incidents
from hermes_continuity.rehydrate import rehydrate_latest_checkpoint
from hermes_continuity.verify import verify_latest_checkpoint
from hermes_state import SessionDB


@contextmanager
def hermes_home_sandbox() -> Path:
    old = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory(prefix="hermes-continuity-bench-") as td:
        home = Path(td)
        for subdir in ("memories", "sessions", "cron", "logs", "skills"):
            (home / subdir).mkdir(parents=True, exist_ok=True)
        os.environ["HERMES_HOME"] = str(home)
        try:
            yield home
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old


def load_cases(cases_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in cases_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _write_minimal_config(
    home: Path,
    *,
    external_memory_enabled: bool = True,
    trusted_source_agents: List[str] | None = None,
    allowed_source_kinds: List[str] | None = None,
    trusted_source_profiles: List[str] | None = None,
    allowed_workspace_prefixes: List[str] | None = None,
    require_evidence_for_kinds: List[str] | None = None,
) -> None:
    continuity_cfg = {
        "enabled": True,
        "checkpoint_on_compact": True,
        "fail_closed_on_compact": True,
        "verify_before_rehydrate": True,
        "write_derived_state": True,
        "external_memory_enabled": external_memory_enabled,
    }
    if trusted_source_agents is not None:
        continuity_cfg["external_memory_trusted_source_agents"] = trusted_source_agents
    if allowed_source_kinds is not None:
        continuity_cfg["external_memory_allowed_source_kinds"] = allowed_source_kinds
    if trusted_source_profiles is not None:
        continuity_cfg["external_memory_trusted_source_profiles"] = trusted_source_profiles
    if allowed_workspace_prefixes is not None:
        continuity_cfg["external_memory_allowed_workspace_prefixes"] = allowed_workspace_prefixes
    if require_evidence_for_kinds is not None:
        continuity_cfg["external_memory_require_evidence_for_kinds"] = require_evidence_for_kinds
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": "openai/gpt-5.4-mini",
                "toolsets": ["hermes-cli", "file"],
                "skills": {"external_dirs": []},
                "continuity": continuity_cfg,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_memory_files(home: Path) -> None:
    memories = home / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "MEMORY.md").write_text("Stable environment note\n", encoding="utf-8")
    (memories / "USER.md").write_text("Alex prefers direct answers\n", encoding="utf-8")


def _prepare_project(tmp_root: Path, name: str = "project") -> Path:
    project = tmp_root / name
    project.mkdir(parents=True, exist_ok=True)
    (project / ".git").mkdir(exist_ok=True)
    (project / "AGENTS.md").write_text("# project instructions\n", encoding="utf-8")
    return project


def _seed_session(home: Path, session_id: str) -> None:
    db = SessionDB(db_path=home / "state.db")
    try:
        db.create_session(session_id, "telegram", model="openai/gpt-5.4-mini")
        db.append_message(session_id, "user", "hello continuity")
    finally:
        db.close()


def _create_checkpoint_fixture(home: Path, *, session_id: str, project_name: str) -> Dict[str, Any]:
    _write_minimal_config(home)
    _write_memory_files(home)
    _seed_session(home, session_id)
    project = _prepare_project(home, name=project_name)
    checkpoint = generate_checkpoint(session_id=session_id, cwd=project)
    return {"project": project, "checkpoint": checkpoint}


def scenario_checkpoint_verify_pass() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        fixture = _create_checkpoint_fixture(home, session_id="sess_ok", project_name="project")
        checkpoint = fixture["checkpoint"]
        verify = verify_latest_checkpoint()

        ok = checkpoint["status"] == "PASS" and verify["status"] == "PASS"
        return {
            "ok": ok,
            "details": {
                "checkpoint_status": checkpoint["status"],
                "verify_status": verify["status"],
                "checkpoint_id": checkpoint.get("checkpoint_id"),
            },
        }


def scenario_verify_detects_mutation() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        _create_checkpoint_fixture(home, session_id="sess_mutate", project_name="project_mutate")
        (home / "memories" / "MEMORY.md").write_text("mutated\n", encoding="utf-8")
        verify = verify_latest_checkpoint()

        ok = verify["status"] == "FAIL" and bool(verify.get("errors"))
        return {
            "ok": ok,
            "details": {
                "verify_status": verify["status"],
                "errors": verify["errors"],
            },
        }


def scenario_anchor_signature_tamper() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        fixture = _create_checkpoint_fixture(home, session_id="sess_anchor_sig", project_name="project_anchor_sig")
        checkpoint = fixture["checkpoint"]
        anchor_path = Path(checkpoint["anchor_path"])
        latest_anchor_path = Path(checkpoint["latest_anchor_path"])
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        anchor["signature"] = "ZmFrZV9zaWduYXR1cmU="
        anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
        latest_anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
        verify = verify_latest_checkpoint()

        ok = verify["status"] == "FAIL" and any("Invalid continuity anchor signature" in err for err in verify["errors"])
        return {
            "ok": ok,
            "details": {
                "verify_status": verify["status"],
                "errors": verify["errors"],
            },
        }


def scenario_anchor_manifest_tamper() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        fixture = _create_checkpoint_fixture(home, session_id="sess_anchor_manifest", project_name="project_anchor_manifest")
        checkpoint = fixture["checkpoint"]
        latest_manifest_path = Path(checkpoint["latest_manifest_path"])
        manifest = json.loads(latest_manifest_path.read_text(encoding="utf-8"))
        manifest["config"]["selected_model"] = "tampered-model"
        latest_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        verify = verify_latest_checkpoint()

        ok = verify["status"] == "FAIL" and any("Anchored artifact digest mismatch" in err for err in verify["errors"])
        return {
            "ok": ok,
            "details": {
                "verify_status": verify["status"],
                "errors": verify["errors"],
            },
        }


def scenario_rehydrate_fail_closed() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        _write_minimal_config(home)
        _write_memory_files(home)
        _seed_session(home, "sess_rehydrate")
        project = _prepare_project(home)

        generate_checkpoint(session_id="sess_rehydrate", cwd=project)
        (home / "memories" / "MEMORY.md").write_text("mutated\n", encoding="utf-8")
        result = rehydrate_latest_checkpoint(target_session_id="sess_blocked")

        db = SessionDB(db_path=home / "state.db")
        try:
            target_exists = db.get_session("sess_blocked") is not None
        finally:
            db.close()

        ok = result["status"] == "FAIL" and not target_exists
        return {
            "ok": ok,
            "details": {
                "rehydrate_status": result["status"],
                "target_exists": target_exists,
                "errors": result.get("errors") or [],
            },
        }


def scenario_missing_anchor_artifact() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        fixture = _create_checkpoint_fixture(home, session_id="sess_missing_anchor", project_name="project_missing_anchor")
        checkpoint = fixture["checkpoint"]
        anchor_path = Path(checkpoint["anchor_path"])
        latest_anchor_path = Path(checkpoint["latest_anchor_path"])
        if anchor_path.exists():
            anchor_path.unlink()
        if latest_anchor_path.exists():
            latest_anchor_path.unlink()
        verify = verify_latest_checkpoint()

        ok = verify["status"] == "FAIL" and any("Missing continuity anchor for checkpoint" in err for err in verify["errors"])
        return {
            "ok": ok,
            "details": {
                "verify_status": verify["status"],
                "errors": verify.get("errors") or [],
            },
        }


def scenario_gateway_auto_reset_receipt() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
        store = SessionStore(sessions_dir=home / "sessions", config=config)
        source = SessionSource(platform=Platform.TELEGRAM, chat_id="123", user_id="u1")

        first = store.get_or_create_session(source)
        first.total_tokens = 42
        first.updated_at = datetime.now() - timedelta(minutes=5)
        store._save()
        second = store.get_or_create_session(source)

        receipt_path = home / "continuity" / "reports" / "gateway-reset-latest.json"
        exists = receipt_path.exists()
        payload = json.loads(receipt_path.read_text(encoding="utf-8")) if exists else {}
        ok = exists and payload.get("reason") == "idle" and payload.get("old_session_id") == first.session_id and payload.get("new_session_id") == second.session_id
        return {
            "ok": ok,
            "details": {
                "receipt_path": str(receipt_path),
                "exists": exists,
                "payload": payload,
            },
        }


def scenario_cron_stale_fast_forward_receipt() -> Dict[str, Any]:
    import importlib

    with hermes_home_sandbox() as home:
        cron_jobs = importlib.import_module("cron.jobs")
        old_cron_dir = cron_jobs.CRON_DIR
        old_jobs_file = cron_jobs.JOBS_FILE
        old_output_dir = cron_jobs.OUTPUT_DIR
        old_now = cron_jobs._hermes_now
        try:
            cron_jobs.CRON_DIR = home / "cron"
            cron_jobs.JOBS_FILE = home / "cron" / "jobs.json"
            cron_jobs.OUTPUT_DIR = home / "cron" / "output"

            now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
            cron_jobs._hermes_now = lambda: now

            job = cron_jobs.create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
            jobs = [cron_jobs.get_job(job["id"])]
            jobs[0]["next_run_at"] = (now - timedelta(hours=2)).isoformat()
            cron_jobs.save_jobs(jobs)
            due = cron_jobs.get_due_jobs()

            receipt_path = home / "continuity" / "reports" / "cron-continuity-latest.json"
            exists = receipt_path.exists()
            payload = json.loads(receipt_path.read_text(encoding="utf-8")) if exists else {}
            ok = due == [] and exists and payload.get("event") == "stale_fast_forward" and payload.get("job_id") == job["id"]
            return {
                "ok": ok,
                "details": {
                    "receipt_path": str(receipt_path),
                    "exists": exists,
                    "payload": payload,
                },
            }
        finally:
            cron_jobs.CRON_DIR = old_cron_dir
            cron_jobs.JOBS_FILE = old_jobs_file
            cron_jobs.OUTPUT_DIR = old_output_dir
            cron_jobs._hermes_now = old_now


def scenario_gateway_receipt_anomaly_incident() -> Dict[str, Any]:
    import gateway.session as gateway_session

    with hermes_home_sandbox() as home:
        config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
        store = SessionStore(sessions_dir=home / "sessions", config=config)
        source = SessionSource(platform=Platform.TELEGRAM, chat_id="123", user_id="u1")
        first = store.get_or_create_session(source)
        first.total_tokens = 42
        first.updated_at = datetime.now() - timedelta(minutes=5)
        store._save()

        real_write = gateway_session.write_gateway_reset_receipt

        def boom(**kwargs):
            raise RuntimeError("gateway receipt write failed")

        gateway_session.write_gateway_reset_receipt = boom
        try:
            store.get_or_create_session(source)
        finally:
            gateway_session.write_gateway_reset_receipt = real_write

        listing = list_continuity_incidents()
        matching = [row for row in listing["incidents"] if row["transition_type"] == "gateway_reset"]
        incident = get_continuity_incident(matching[0]["incident_id"]) if matching else {"status": "NOT_FOUND", "payload": {}}
        ok = len(matching) == 1 and incident.get("payload", {}).get("verdict") == "DEGRADED_CONTINUE"
        return {
            "ok": ok,
            "details": {
                "incident_count": len(matching),
                "incident": incident.get("payload") or {},
            },
        }


def scenario_cron_receipt_anomaly_incident() -> Dict[str, Any]:
    import importlib

    with hermes_home_sandbox() as home:
        cron_jobs = importlib.import_module("cron.jobs")
        old_cron_dir = cron_jobs.CRON_DIR
        old_jobs_file = cron_jobs.JOBS_FILE
        old_output_dir = cron_jobs.OUTPUT_DIR
        old_now = cron_jobs._hermes_now
        real_write = cron_jobs.write_cron_continuity_receipt
        try:
            cron_jobs.CRON_DIR = home / "cron"
            cron_jobs.JOBS_FILE = home / "cron" / "jobs.json"
            cron_jobs.OUTPUT_DIR = home / "cron" / "output"
            now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
            cron_jobs._hermes_now = lambda: now

            job = cron_jobs.create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
            jobs = [cron_jobs.get_job(job["id"])]
            jobs[0]["next_run_at"] = (now - timedelta(minutes=10)).isoformat()
            cron_jobs.save_jobs(jobs)

            def boom(**kwargs):
                raise RuntimeError("cron receipt write failed")

            cron_jobs.write_cron_continuity_receipt = boom
            due = cron_jobs.get_due_jobs()
            listing = list_continuity_incidents()
            matching = [row for row in listing["incidents"] if row["transition_type"] == "cron_continuity"]
            incident = get_continuity_incident(matching[0]["incident_id"]) if matching else {"status": "NOT_FOUND", "payload": {}}
            ok = len(due) == 1 and len(matching) == 1 and incident.get("payload", {}).get("verdict") == "DEGRADED_CONTINUE"
            return {
                "ok": ok,
                "details": {
                    "due_count": len(due),
                    "incident_count": len(matching),
                    "incident": incident.get("payload") or {},
                },
            }
        finally:
            cron_jobs.CRON_DIR = old_cron_dir
            cron_jobs.JOBS_FILE = old_jobs_file
            cron_jobs.OUTPUT_DIR = old_output_dir
            cron_jobs._hermes_now = old_now
            cron_jobs.write_cron_continuity_receipt = real_write


def scenario_external_memory_ingest_quarantine() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        _write_minimal_config(home)
        result = ingest_external_memory_candidate(
            {
                "source_kind": "external_worker",
                "source_session_id": "sess_ext_ingest",
                "source_agent": "sparky",
                "target": "memory",
                "content": "External continuity candidate for quarantine.",
            }
        )
        listing = list_external_memory_candidates(state="QUARANTINED")
        ok = result["status"] == "QUARANTINED" and any(
            row["candidate_id"] == result["candidate_id"] for row in listing["candidates"]
        )
        return {
            "ok": ok,
            "details": {
                "candidate_id": result.get("candidate_id"),
                "ingest_status": result.get("status"),
                "listed_count": listing.get("candidate_count"),
            },
        }


def scenario_external_memory_promote() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        _write_minimal_config(home)
        result = ingest_external_memory_candidate(
            {
                "source_kind": "external_worker",
                "source_session_id": "sess_ext_promote",
                "source_agent": "smarty",
                "target": "user",
                "content": "Alex wants deterministic continuity proofs.",
            }
        )
        promoted = promote_external_memory_candidate(result["candidate_id"], reviewer="filippo")
        user_text = (home / "memories" / "USER.md").read_text(encoding="utf-8")
        ok = promoted["status"] == "PROMOTED" and "deterministic continuity proofs" in user_text
        return {
            "ok": ok,
            "details": {
                "candidate_id": result.get("candidate_id"),
                "promotion_status": promoted.get("status"),
            },
        }


def scenario_external_memory_provenance_policy() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        _write_minimal_config(
            home,
            trusted_source_agents=["smarty"],
            trusted_source_profiles=["smarty"],
            allowed_workspace_prefixes=["/trusted/worktrees/"],
            require_evidence_for_kinds=["external_worker"],
        )
        result = ingest_external_memory_candidate(
            {
                "source_kind": "external_worker",
                "source_session_id": "sess_ext_provenance",
                "source_agent": "sparky",
                "source_profile": "sparky",
                "source_workspace": "/tmp/rogue-worktree",
                "target": "memory",
                "content": "This should be blocked by provenance policy.",
            }
        )
        errors = result.get("errors") or []
        ok = (
            result["status"] == "REJECTED"
            and any("not trusted by policy" in err for err in errors)
            and any("source_workspace" in err for err in errors)
            and any("evidence is required" in err for err in errors)
        )
        return {
            "ok": ok,
            "details": {
                "ingest_status": result.get("status"),
                "errors": errors,
            },
        }


def scenario_external_memory_recovery() -> Dict[str, Any]:
    import hermes_continuity.external_memory as ext

    with hermes_home_sandbox() as home:
        _write_minimal_config(home)
        ingest = ingest_external_memory_candidate(
            {
                "source_kind": "external_worker",
                "source_session_id": "sess_ext_recover",
                "source_agent": "smarty",
                "target": "memory",
                "content": "Recovery-safe external memory fact.",
            }
        )
        candidate_id = ingest["candidate_id"]
        real_atomic = ext.atomic_json_write
        failed_once = {"value": False}

        def flaky_atomic(path, payload):
            if (
                not failed_once["value"]
                and Path(path).parent.name == "promoted"
                and Path(path).name == f"{candidate_id}.json"
            ):
                failed_once["value"] = True
                raise OSError("simulated promoted write failure")
            return real_atomic(path, payload)

        ext.atomic_json_write = flaky_atomic
        try:
            first = promote_external_memory_candidate(candidate_id, reviewer="filippo")
        finally:
            ext.atomic_json_write = real_atomic
        second = promote_external_memory_candidate(candidate_id, reviewer="filippo")
        mem_text = (home / "memories" / "MEMORY.md").read_text(encoding="utf-8")
        ok = (
            first["status"] == "RECOVERY_REQUIRED"
            and second["status"] == "PROMOTED"
            and mem_text.count("Recovery-safe external memory fact.") == 1
        )
        return {
            "ok": ok,
            "details": {
                "candidate_id": candidate_id,
                "first_status": first.get("status"),
                "second_status": second.get("status"),
            },
        }


SCENARIOS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "checkpoint_verify_pass": scenario_checkpoint_verify_pass,
    "verify_detects_mutation": scenario_verify_detects_mutation,
    "anchor_signature_tamper": scenario_anchor_signature_tamper,
    "anchor_manifest_tamper": scenario_anchor_manifest_tamper,
    "missing_anchor_artifact": scenario_missing_anchor_artifact,
    "rehydrate_fail_closed": scenario_rehydrate_fail_closed,
    "gateway_auto_reset_receipt": scenario_gateway_auto_reset_receipt,
    "gateway_receipt_anomaly_incident": scenario_gateway_receipt_anomaly_incident,
    "cron_stale_fast_forward_receipt": scenario_cron_stale_fast_forward_receipt,
    "cron_receipt_anomaly_incident": scenario_cron_receipt_anomaly_incident,
    "external_memory_ingest_quarantine": scenario_external_memory_ingest_quarantine,
    "external_memory_promote": scenario_external_memory_promote,
    "external_memory_provenance_policy": scenario_external_memory_provenance_policy,
    "external_memory_recovery": scenario_external_memory_recovery,
}


def run_benchmark(cases_path: Path | None = None) -> Dict[str, Any]:
    cases_path = cases_path or Path(__file__).with_name("cases.jsonl")
    cases = load_cases(cases_path)
    results: List[Dict[str, Any]] = []
    passed = 0
    failed = 0

    for case in cases:
        scenario_name = case["scenario"]
        handler = SCENARIOS[scenario_name]
        result = handler()
        ok = bool(result["ok"])
        passed += 1 if ok else 0
        failed += 0 if ok else 1
        results.append(
            {
                "case_id": case["case_id"],
                "description": case.get("description"),
                "scenario": scenario_name,
                "status": "PASS" if ok else "FAIL",
                "details": result.get("details", {}),
            }
        )

    return {
        "benchmark": "hermes-continuity-v0",
        "cases_path": str(cases_path.resolve()),
        "case_count": len(cases),
        "passed_count": passed,
        "failed_count": failed,
        "status": "PASS" if failed == 0 else "FAIL",
        "results": results,
    }


def main() -> int:
    result = run_benchmark()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

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


def _write_minimal_config(home: Path) -> None:
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": "openai/gpt-5.4-mini",
                "toolsets": ["hermes-cli", "file"],
                "skills": {"external_dirs": []},
                "continuity": {
                    "enabled": True,
                    "checkpoint_on_compact": True,
                    "fail_closed_on_compact": True,
                    "verify_before_rehydrate": True,
                    "write_derived_state": True,
                },
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


def scenario_checkpoint_verify_pass() -> Dict[str, Any]:
    with hermes_home_sandbox() as home:
        _write_minimal_config(home)
        _write_memory_files(home)
        _seed_session(home, "sess_ok")
        project = _prepare_project(home)

        checkpoint = generate_checkpoint(session_id="sess_ok", cwd=project)
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
        _write_minimal_config(home)
        _write_memory_files(home)
        _seed_session(home, "sess_mutate")
        project = _prepare_project(home)

        generate_checkpoint(session_id="sess_mutate", cwd=project)
        (home / "memories" / "MEMORY.md").write_text("mutated\n", encoding="utf-8")
        verify = verify_latest_checkpoint()

        ok = verify["status"] == "FAIL" and any("Digest mismatch for memory file" in err for err in verify["errors"])
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


SCENARIOS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "checkpoint_verify_pass": scenario_checkpoint_verify_pass,
    "verify_detects_mutation": scenario_verify_detects_mutation,
    "rehydrate_fail_closed": scenario_rehydrate_fail_closed,
    "gateway_auto_reset_receipt": scenario_gateway_auto_reset_receipt,
    "cron_stale_fast_forward_receipt": scenario_cron_stale_fast_forward_receipt,
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

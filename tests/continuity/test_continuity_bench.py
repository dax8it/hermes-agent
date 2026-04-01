"""Smoke tests for the minimal continuity benchmark harness."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

BENCH_RUN_PATH = Path(__file__).resolve().parents[2] / "bench/continuity/run.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("continuity_bench_run_test", BENCH_RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_benchmark_runs_with_missing_artifacts_and_reports_warn():
    module = _load_module()
    result = module.run_benchmark()
    assert result["benchmark"] == "hermes-continuity-v0"
    assert result["case_count"] >= 1
    assert result["status"] in {"PASS", "WARN"}
    assert len(result["results"]) == result["case_count"]


def test_benchmark_reads_cases_file():
    cases_path = Path(__file__).resolve().parents[2] / "bench/continuity/cases.jsonl"
    rows = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(row["case_id"] == "gateway_reset_latest_report" for row in rows)
    assert any(row["case_id"] == "cron_continuity_latest_report" for row in rows)

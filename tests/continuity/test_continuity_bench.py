"""Behavioral tests for the continuity benchmark harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path

BENCH_RUN_PATH = Path(__file__).resolve().parents[2] / "bench/continuity/run.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("continuity_bench_run_test", BENCH_RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_benchmark_runs_behavioral_cases_and_passes():
    module = _load_module()
    result = module.run_benchmark()
    assert result["benchmark"] == "hermes-continuity-v0"
    assert result["case_count"] == 8
    assert result["failed_count"] == 0
    assert result["status"] == "PASS"
    assert {row["scenario"] for row in result["results"]} == {
        "checkpoint_verify_pass",
        "verify_detects_mutation",
        "rehydrate_fail_closed",
        "gateway_auto_reset_receipt",
        "cron_stale_fast_forward_receipt",
        "external_memory_ingest_quarantine",
        "external_memory_promote",
        "external_memory_recovery",
    }


def test_benchmark_reads_behavioral_case_file():
    module = _load_module()
    rows = module.load_cases(Path(__file__).resolve().parents[2] / "bench/continuity/cases.jsonl")
    assert any(row["scenario"] == "checkpoint_verify_pass" for row in rows)
    assert any(row["scenario"] == "cron_stale_fast_forward_receipt" for row in rows)
    assert any(row["scenario"] == "external_memory_ingest_quarantine" for row in rows)
    assert any(row["scenario"] == "external_memory_promote" for row in rows)
    assert any(row["scenario"] == "external_memory_recovery" for row in rows)

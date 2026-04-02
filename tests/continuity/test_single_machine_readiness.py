"""Tests for single-machine readiness reporting."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load_module():
    from hermes_continuity import readiness

    return readiness


def test_single_machine_readiness_passes_with_green_core_surfaces(tmp_path, monkeypatch):
    readiness = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    manifests_dir = hermes_home / "continuity" / "manifests"
    anchors_dir = hermes_home / "continuity" / "anchors"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rehydrate_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    anchors_dir.mkdir(parents=True, exist_ok=True)

    manifests_dir.joinpath("latest.json").write_text(
        json.dumps({"checkpoint_id": "ckpt_ready", "schema_version": "hermes-total-recall-v0", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    anchors_dir.joinpath("latest.json").write_text(
        json.dumps({"schema_version": "hermes-total-recall-anchor-v0", "signature_algorithm": "ed25519", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    for name in ("verify", "gateway-reset", "cron-continuity"):
        reports_dir.joinpath(f"{name}-latest.json").write_text(
            json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
            encoding="utf-8",
        )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        readiness,
        "_load_benchmark_payload",
        lambda: {"status": "PASS", "passed_count": 18, "failed_count": 0, "case_count": 18, "results": []},
    )
    monkeypatch.setattr(
        "hermes_continuity.dashboard.build_continuity_sessions_snapshot",
        lambda: {
            "generated_at": "2099-04-01T00:00:00Z",
            "session_count": 1,
            "sessions": [
                {
                    "session_key": "agent:main:telegram:dm:123",
                    "session_id": "sess_1",
                    "platform": "telegram",
                    "model": "gpt-5.4",
                    "context_used_pct": 0.5,
                    "updated_at": "2099-04-01T00:00:00Z",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "hermes_continuity.dashboard.build_continuity_incident_snapshot",
        lambda: {"open": 0, "resolved": 0, "fail_closed": 0, "degraded": 0, "unsafe_pass": 0},
    )

    result = readiness.verify_single_machine_readiness()

    assert result["status"] == "PASS"
    payload = result["payload"]
    assert payload["status"] == "PASS"
    assert payload["sessions"]["session_count"] == 1
    assert payload["benchmark"]["status"] == "PASS"
    assert Path(result["report_path"]).exists()


def test_single_machine_readiness_fails_closed_when_verify_surface_is_missing(tmp_path, monkeypatch):
    readiness = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    manifests_dir = hermes_home / "continuity" / "manifests"
    anchors_dir = hermes_home / "continuity" / "anchors"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rehydrate_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    anchors_dir.mkdir(parents=True, exist_ok=True)

    manifests_dir.joinpath("latest.json").write_text(
        json.dumps({"checkpoint_id": "ckpt_ready", "schema_version": "hermes-total-recall-v0", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    anchors_dir.joinpath("latest.json").write_text(
        json.dumps({"schema_version": "hermes-total-recall-anchor-v0", "signature_algorithm": "ed25519", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        readiness,
        "_load_benchmark_payload",
        lambda: {"status": "PASS", "passed_count": 18, "failed_count": 0, "case_count": 18, "results": []},
    )
    monkeypatch.setattr(
        "hermes_continuity.dashboard.build_continuity_sessions_snapshot",
        lambda: {"generated_at": "2099-04-01T00:00:00Z", "session_count": 1, "sessions": [{"context_used_pct": 0.5}]},
    )
    monkeypatch.setattr(
        "hermes_continuity.dashboard.build_continuity_incident_snapshot",
        lambda: {"open": 0, "resolved": 0, "fail_closed": 0, "degraded": 0, "unsafe_pass": 0},
    )

    result = readiness.verify_single_machine_readiness()

    assert result["status"] == "FAIL"
    payload = result["payload"]
    assert payload["status"] == "FAIL"
    assert any("verify report" in err for err in payload["errors"])
    assert Path(result["latest_report_path"]).exists()

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


def test_single_machine_readiness_ignores_idle_cross_profile_pressure(tmp_path, monkeypatch):
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
            "session_count": 2,
            "active_session_count": 1,
            "sessions": [
                {
                    "profile_name": "filippo",
                    "is_current_profile": True,
                    "activity_state": "ACTIVE",
                    "session_key": "agent:main:telegram:dm:123",
                    "session_id": "sess_live",
                    "platform": "telegram",
                    "model": "gpt-5.4",
                    "context_used_pct": 0.12,
                    "updated_at": "2099-04-01T00:00:00Z",
                },
                {
                    "profile_name": "default",
                    "is_current_profile": False,
                    "activity_state": "IDLE",
                    "session_key": "agent:main:telegram:dm:old",
                    "session_id": "sess_old",
                    "platform": "telegram",
                    "model": "gpt-5.4-mini",
                    "context_used_pct": 0.91,
                    "updated_at": "2099-03-31T00:00:00Z",
                },
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
    assert payload["sessions"]["high_pressure_count"] == 0
    assert payload["sessions"]["highest_context_used_pct"] == 0.12
    assert [item["session_id"] for item in payload["sessions"]["active"]] == ["sess_live"]


def test_single_machine_readiness_warns_for_active_current_profile_pressure(tmp_path, monkeypatch):
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
            "active_session_count": 1,
            "sessions": [
                {
                    "profile_name": "filippo",
                    "is_current_profile": True,
                    "activity_state": "ACTIVE",
                    "session_key": "agent:main:telegram:dm:123",
                    "session_id": "sess_hot",
                    "platform": "telegram",
                    "model": "gpt-5.4",
                    "context_used_pct": 0.87,
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

    assert result["status"] == "WARN"
    payload = result["payload"]
    assert payload["status"] == "WARN"
    assert payload["sessions"]["high_pressure_count"] == 1
    assert payload["sessions"]["highest_context_used_pct"] == 0.87
    assert any("above 80% context usage" in warning for warning in payload["warnings"])


def test_single_machine_readiness_warns_when_gateway_and_cron_receipts_are_stale(tmp_path, monkeypatch):
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
    reports_dir.joinpath("verify-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    reports_dir.joinpath("gateway-reset-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2020-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    reports_dir.joinpath("cron-continuity-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2020-01-01T00:00:00Z"}),
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
            "active_session_count": 1,
            "sessions": [
                {
                    "profile_name": "filippo",
                    "is_current_profile": True,
                    "activity_state": "ACTIVE",
                    "session_key": "agent:main:telegram:dm:123",
                    "session_id": "sess_live",
                    "platform": "telegram",
                    "model": "gpt-5.4",
                    "context_used_pct": 0.2,
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

    assert result["status"] == "WARN"
    payload = result["payload"]
    assert payload["status"] == "WARN"
    assert not payload["errors"]
    assert any("gateway-reset reporting is stale" in warning for warning in payload["warnings"])
    assert any("cron-continuity reporting is stale" in warning for warning in payload["warnings"])


def test_single_machine_readiness_treats_verify_warn_and_stale_rehydrate_as_warnings(tmp_path, monkeypatch):
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
    reports_dir.joinpath("verify-latest.json").write_text(
        json.dumps({"status": "WARN", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    reports_dir.joinpath("gateway-reset-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    reports_dir.joinpath("cron-continuity-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2020-01-01T00:00:00Z"}),
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
            "active_session_count": 1,
            "sessions": [
                {
                    "profile_name": "filippo",
                    "is_current_profile": True,
                    "activity_state": "ACTIVE",
                    "session_key": "agent:main:telegram:dm:123",
                    "session_id": "sess_live",
                    "platform": "telegram",
                    "model": "gpt-5.4",
                    "context_used_pct": 0.2,
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

    assert result["status"] == "WARN"
    payload = result["payload"]
    assert payload["status"] == "WARN"
    assert not payload["errors"]
    assert any("Verify passed with warnings" in warning for warning in payload["warnings"])
    assert any("Rehydrate has not been re-exercised" in warning for warning in payload["warnings"])

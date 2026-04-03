"""Tests for automatic continuity refresh after gateway resets."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch


def test_post_reset_refresh_runs_checkpoint_verify_rehydrate_and_readiness(tmp_path):
    from hermes_continuity.refresh import run_post_reset_continuity_refresh

    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    gateway_report = reports_dir / "gateway-reset-latest.json"
    gateway_report.write_text(
        json.dumps({"status": "PASS", "generated_at": "2026-04-03T10:00:00Z"}),
        encoding="utf-8",
    )

    checkpoint_result = {"status": "PASS", "checkpoint_id": "ckpt_1"}
    verify_result = {"status": "PASS", "report_path": "/tmp/verify.json"}
    rehydrate_result = {"status": "PASS", "report_path": "/tmp/rehydrate.json"}
    readiness_result = {
        "status": "PASS",
        "payload": {"status": "PASS", "operator_summary": "Machine ready."},
    }

    with patch("hermes_continuity.refresh.generate_checkpoint", return_value=checkpoint_result) as mocked_checkpoint, patch(
        "hermes_continuity.refresh.verify_latest_checkpoint", return_value=verify_result
    ) as mocked_verify, patch(
        "hermes_continuity.refresh.rehydrate_latest_checkpoint", return_value=rehydrate_result
    ) as mocked_rehydrate, patch(
        "hermes_continuity.refresh.verify_single_machine_readiness", return_value=readiness_result
    ) as mocked_readiness:
        result = run_post_reset_continuity_refresh(
            session_key="agent:main:telegram:dm:123",
            session_id="sess_new",
            reason="daily",
            automatic=True,
            gateway_reset_report_path=str(gateway_report),
            gateway_reset_latest_path=str(gateway_report),
            cwd="/tmp/project",
        )

    mocked_checkpoint.assert_called_once()
    mocked_verify.assert_called_once_with()
    mocked_rehydrate.assert_called_once_with(target_session_id="sess_new")
    mocked_readiness.assert_called_once()
    assert result["status"] == "PASS"
    assert Path(result["latest_report_path"]).exists()

    updated_gateway_report = json.loads(gateway_report.read_text(encoding="utf-8"))
    assert updated_gateway_report["post_reset_refresh"]["status"] == "PASS"
    assert updated_gateway_report["post_reset_refresh"]["checkpoint_id"] == "ckpt_1"
    assert updated_gateway_report["post_reset_refresh"]["verify_status"] == "PASS"


def test_post_reset_refresh_warns_without_creating_incident(tmp_path):
    from hermes_continuity.refresh import run_post_reset_continuity_refresh

    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    gateway_report = reports_dir / "gateway-reset-latest.json"
    gateway_report.write_text(
        json.dumps({"status": "PASS", "generated_at": "2026-04-03T10:00:00Z"}),
        encoding="utf-8",
    )

    with patch("hermes_continuity.refresh.generate_checkpoint", return_value={"status": "PASS", "checkpoint_id": "ckpt_1"}), patch(
        "hermes_continuity.refresh.verify_latest_checkpoint", return_value={"status": "PASS"}
    ), patch(
        "hermes_continuity.refresh.rehydrate_latest_checkpoint", return_value={"status": "WARN"}
    ), patch(
        "hermes_continuity.refresh.verify_single_machine_readiness", return_value={"status": "WARN", "payload": {"status": "WARN"}}
    ), patch("hermes_continuity.refresh.create_or_update_continuity_incident") as mocked_incident:
        result = run_post_reset_continuity_refresh(
            session_key="agent:main:telegram:dm:123",
            session_id="sess_new",
            reason="daily",
            automatic=True,
            gateway_reset_report_path=str(gateway_report),
            gateway_reset_latest_path=str(gateway_report),
            cwd="/tmp/project",
        )

    assert result["status"] == "WARN"
    mocked_incident.assert_not_called()

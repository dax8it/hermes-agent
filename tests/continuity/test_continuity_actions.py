"""Tests for guarded continuity action helpers."""

from __future__ import annotations

from unittest.mock import patch

from hermes_continuity import actions



def test_run_checkpoint_action_calls_generate_checkpoint_with_explicit_session_and_cwd():
    with patch("hermes_continuity.actions.generate_checkpoint", return_value={"status": "PASS", "checkpoint_id": "ckpt_1"}) as mocked:
        result = actions.run_checkpoint_action(session_id="sess_1", cwd="/tmp/project")

    mocked.assert_called_once()
    args, kwargs = mocked.call_args
    assert args[0] == "sess_1"
    assert str(kwargs["cwd"]).endswith("/tmp/project")
    assert result["ok"] is True
    assert result["action"] == "checkpoint"
    assert result["result"]["checkpoint_id"] == "ckpt_1"



def test_run_verify_action_calls_verify_latest_checkpoint():
    with patch("hermes_continuity.actions.verify_latest_checkpoint", return_value={"status": "PASS"}) as mocked:
        result = actions.run_verify_action()

    mocked.assert_called_once_with()
    assert result["ok"] is True
    assert result["action"] == "verify"
    assert result["result"]["status"] == "PASS"



def test_run_rehydrate_action_calls_rehydrate_latest_checkpoint_with_target_session():
    with patch("hermes_continuity.actions.rehydrate_latest_checkpoint", return_value={"status": "PASS", "target_session_id": "sess_2"}) as mocked:
        result = actions.run_rehydrate_action(target_session_id="sess_2")

    mocked.assert_called_once_with(target_session_id="sess_2")
    assert result["ok"] is True
    assert result["action"] == "rehydrate"
    assert result["result"]["target_session_id"] == "sess_2"



def test_run_benchmark_action_returns_benchmark_payload():
    with patch("hermes_continuity.actions._load_benchmark_payload", return_value={"status": "PASS", "case_count": 18}) as mocked:
        result = actions.run_benchmark_action()

    mocked.assert_called_once_with()
    assert result["ok"] is True
    assert result["action"] == "benchmark"
    assert result["result"]["case_count"] == 18



def test_add_incident_note_action_calls_note_helper():
    with patch("hermes_continuity.actions.add_note_to_continuity_incident", return_value={"status": "OK", "incident_id": "incident_1"}) as mocked:
        result = actions.add_incident_note_action(incident_id="incident_1", note="Operator reviewed.")

    mocked.assert_called_once_with("incident_1", note="Operator reviewed.")
    assert result["ok"] is True
    assert result["action"] == "incident-note"
    assert result["result"]["incident_id"] == "incident_1"



def test_resolve_incident_action_calls_resolve_helper():
    with patch("hermes_continuity.actions.resolve_continuity_incident", return_value={"status": "OK", "incident_id": "incident_1", "payload": {"incident_state": "RESOLVED"}}) as mocked:
        result = actions.resolve_incident_action(incident_id="incident_1", resolution_summary="Resolved by operator.")

    mocked.assert_called_once_with("incident_1", resolution_summary="Resolved by operator.")
    assert result["ok"] is True
    assert result["action"] == "incident-resolve"
    assert result["result"]["payload"]["incident_state"] == "RESOLVED"

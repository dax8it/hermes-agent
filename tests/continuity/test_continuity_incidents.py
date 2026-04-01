"""Tests for continuity incident logging and postmortem artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load_module():
    from hermes_continuity import incidents

    return incidents


def test_create_continuity_incident_writes_json_and_markdown_artifacts(tmp_path):
    incidents = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    (hermes_home / "continuity" / "reports").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "reports" / "verify-latest.json").write_text(
        json.dumps({"status": "FAIL", "generated_at": "2026-04-01T00:00:00Z"}),
        encoding="utf-8",
    )

    result = incidents.create_continuity_incident(
        verdict="FAIL_CLOSED",
        transition_type="compaction",
        protected_transitions_blocked=True,
        failure_planes=["integrity", "custody"],
        summary="Anchor verification failed before compaction.",
        exact_blocker="Invalid continuity anchor signature",
        exact_remediation="Regenerate checkpoint and anchor from known-good state",
        commands_run=["python scripts/continuity/hermes_verify.py"],
        artifacts_inspected=[str(hermes_home / "continuity" / "reports" / "verify-latest.json")],
    )

    assert result["status"] == "OK"
    json_path = Path(result["json_path"])
    md_path = Path(result["markdown_path"])
    assert json_path.exists()
    assert md_path.exists()
    assert Path(result["latest_json_path"]).exists()
    assert Path(result["latest_markdown_path"]).exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "hermes-continuity-incident-v0"
    assert payload["verdict"] == "FAIL_CLOSED"
    assert payload["transition_type"] == "compaction"
    assert payload["status_snapshot"]["reports"]["verify"]["status"] == "FAIL"

    markdown = md_path.read_text(encoding="utf-8")
    assert "# Continuity Incident" in markdown
    assert "FAIL_CLOSED" in markdown
    assert "Anchor verification failed before compaction." in markdown


def test_append_continuity_incident_event_updates_timeline_and_markdown(tmp_path):
    incidents = _load_module()
    created = incidents.create_continuity_incident(
        verdict="FAIL_CLOSED",
        transition_type="verification",
        protected_transitions_blocked=True,
        failure_planes=["integrity"],
        summary="Verification failed.",
    )

    updated = incidents.append_continuity_incident_event(
        created["incident_id"],
        event="rerun_failed",
        detail="Verification failed again after rerun.",
        commands_run=["python scripts/continuity/hermes_verify.py"],
    )

    assert updated["status"] == "OK"
    payload = updated["payload"]
    assert len(payload["timeline"]) == 2
    assert payload["timeline"][-1]["event"] == "rerun_failed"
    assert "python scripts/continuity/hermes_verify.py" in payload["commands_run"]
    markdown = Path(updated["markdown_path"]).read_text(encoding="utf-8")
    assert "rerun_failed" in markdown


def test_create_or_update_fail_closed_incident_reuses_latest_matching_incident(tmp_path):
    incidents = _load_module()
    first = incidents.create_or_update_fail_closed_incident(
        transition_type="verification",
        summary="Continuity verification failed before a protected transition could proceed.",
        exact_blocker="Missing latest checkpoint manifest",
        failure_planes=["integrity"],
        commands_run=["python scripts/continuity/hermes_verify.py"],
        event="verification_failed",
    )
    second = incidents.create_or_update_fail_closed_incident(
        transition_type="verification",
        summary="Continuity verification failed before a protected transition could proceed.",
        exact_blocker="Missing latest checkpoint manifest",
        failure_planes=["integrity"],
        commands_run=["python scripts/continuity/hermes_verify.py"],
        event="verification_failed_again",
    )

    assert first["incident_id"] == second["incident_id"]
    shown = incidents.get_continuity_incident(first["incident_id"])
    assert shown["status"] == "OK"
    assert len(shown["payload"]["timeline"]) == 2
    assert shown["payload"]["timeline"][-1]["event"] == "verification_failed_again"


def test_list_and_show_continuity_incidents(tmp_path):
    incidents = _load_module()

    created = incidents.create_continuity_incident(
        verdict="UNSAFE_PASS",
        transition_type="external_memory_promotion",
        protected_transitions_blocked=False,
        failure_planes=["gate_coverage", "external_memory"],
        summary="Canonical memory was mutated before policy denial.",
    )

    listing = incidents.list_continuity_incidents()
    assert listing["status"] == "OK"
    assert listing["incident_count"] >= 1
    assert any(row["incident_id"] == created["incident_id"] for row in listing["incidents"])

    shown = incidents.get_continuity_incident(created["incident_id"])
    assert shown["status"] == "OK"
    assert shown["payload"]["verdict"] == "UNSAFE_PASS"
    assert shown["payload"]["summary"] == "Canonical memory was mutated before policy denial."


def test_verify_fail_auto_creates_or_updates_incident(tmp_path):
    from hermes_continuity import verify as verify_module
    incidents = _load_module()

    first = verify_module.verify_latest_checkpoint()
    second = verify_module.verify_latest_checkpoint()

    assert first["status"] == "FAIL"
    assert second["status"] == "FAIL"
    listing = incidents.list_continuity_incidents()
    verification_incidents = [row for row in listing["incidents"] if row["transition_type"] == "verification"]
    assert len(verification_incidents) == 1
    shown = incidents.get_continuity_incident(verification_incidents[0]["incident_id"])
    assert len(shown["payload"]["timeline"]) >= 2


def test_rehydrate_fail_auto_creates_incident(tmp_path):
    from hermes_continuity import rehydrate as rehydrate_module
    incidents = _load_module()

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_auto")

    assert result["status"] == "FAIL"
    listing = incidents.list_continuity_incidents()
    assert any(row["transition_type"] == "rehydrate" for row in listing["incidents"])

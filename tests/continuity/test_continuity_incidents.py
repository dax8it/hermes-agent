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

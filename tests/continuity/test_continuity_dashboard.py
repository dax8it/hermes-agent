"""Tests for continuity dashboard summary helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _load_dashboard_module():
    from hermes_continuity import dashboard

    return dashboard


def _load_incidents_module():
    from hermes_continuity import incidents

    return incidents


def _monotonic_now_utc():
    current = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)

    def _next():
        nonlocal current
        value = current
        current = current + timedelta(seconds=1)
        return value

    return _next


def test_build_continuity_summary_includes_status_reports_benchmark_and_incident_counts(tmp_path, monkeypatch):
    dashboard = _load_dashboard_module()
    incidents = _load_incidents_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    monkeypatch.setattr(incidents, "now_utc", _monotonic_now_utc())

    (hermes_home / "continuity" / "manifests").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "anchors").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "reports").mkdir(parents=True, exist_ok=True)

    (hermes_home / "continuity" / "manifests" / "latest.json").write_text(
        json.dumps({
            "checkpoint_id": "ckpt_summary",
            "schema_version": "hermes-total-recall-v0",
            "generated_at": "2099-04-01T00:00:00Z",
        }),
        encoding="utf-8",
    )
    (hermes_home / "continuity" / "anchors" / "latest.json").write_text(
        json.dumps({
            "schema_version": "hermes-total-recall-anchor-v0",
            "signature_algorithm": "ed25519",
            "generated_at": "2099-04-01T00:00:00Z",
        }),
        encoding="utf-8",
    )
    (hermes_home / "continuity" / "reports" / "verify-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-01T00:00:00Z"}),
        encoding="utf-8",
    )

    incidents.create_continuity_incident(
        verdict="DEGRADED_CONTINUE",
        transition_type="gateway_reset",
        protected_transitions_blocked=False,
        failure_planes=["gate_coverage"],
        summary="Gateway receipt is stale.",
    )
    resolved = incidents.create_continuity_incident(
        verdict="FAIL_CLOSED",
        transition_type="verification",
        protected_transitions_blocked=True,
        failure_planes=["integrity"],
        summary="Verification failed closed.",
    )
    incidents.resolve_continuity_incident(
        resolved["incident_id"],
        resolution_summary="Operator regenerated checkpoint and reran verify.",
    )

    monkeypatch.setattr(
        dashboard,
        "_load_benchmark_payload",
        lambda: {"status": "PASS", "passed_count": 18, "case_count": 18, "failed_count": 0},
    )

    summary = dashboard.build_continuity_summary()

    assert summary["status"]["checkpoint_id"] == "ckpt_summary"
    assert summary["status"]["manifest"]["exists"] is True
    assert summary["status"]["manifest"]["stale"] is False
    assert summary["status"]["anchor"]["exists"] is True
    assert summary["reports"]["verify"]["status"] == "PASS"
    assert summary["reports"]["verify"]["freshness"]["stale"] is False
    assert summary["benchmark"]["status"] == "PASS"
    assert summary["benchmark"]["case_count"] == 18
    assert summary["incidents"]["open"] == 1
    assert summary["incidents"]["resolved"] == 1
    assert summary["incidents"]["degraded"] == 1
    assert summary["incidents"]["fail_closed"] == 0


def test_build_continuity_incident_snapshot_aggregates_open_and_resolved_verdicts(tmp_path, monkeypatch):
    dashboard = _load_dashboard_module()
    incidents = _load_incidents_module()
    monkeypatch.setattr(incidents, "now_utc", _monotonic_now_utc())

    fail_closed = incidents.create_continuity_incident(
        verdict="FAIL_CLOSED",
        transition_type="compaction",
        protected_transitions_blocked=True,
        failure_planes=["integrity"],
        summary="Compaction blocked.",
    )
    incidents.create_continuity_incident(
        verdict="DEGRADED_CONTINUE",
        transition_type="cron_continuity",
        protected_transitions_blocked=False,
        failure_planes=["gate_coverage"],
        summary="Cron receipt missing.",
    )
    unsafe = incidents.create_continuity_incident(
        verdict="UNSAFE_PASS",
        transition_type="external_memory_promotion",
        protected_transitions_blocked=False,
        failure_planes=["external_memory"],
        summary="Unsafe promotion occurred.",
    )
    incidents.resolve_continuity_incident(
        unsafe["incident_id"],
        resolution_summary="Unsafe pass documented and mitigated.",
    )

    snapshot = dashboard.build_continuity_incident_snapshot()

    assert snapshot["incident_count"] == 3
    assert snapshot["open"] == 2
    assert snapshot["resolved"] == 1
    assert snapshot["fail_closed"] == 1
    assert snapshot["degraded"] == 1
    assert snapshot["unsafe_pass"] == 0
    assert any(item["incident_id"] == fail_closed["incident_id"] for item in snapshot["recent"])

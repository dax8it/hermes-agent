"""Tests for continuity dashboard summary helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gateway.config import GatewayConfig, Platform
from gateway.session import SessionSource, SessionStore


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


def _make_gateway_source() -> SessionSource:
    return SessionSource(platform=Platform.TELEGRAM, chat_id="123", user_id="u1")


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



def test_build_continuity_sessions_snapshot_includes_context_pressure(tmp_path, monkeypatch):
    dashboard = _load_dashboard_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    config = GatewayConfig(sessions_dir=hermes_home / "sessions")
    store = SessionStore(sessions_dir=config.sessions_dir, config=config)
    source = _make_gateway_source()

    entry = store.get_or_create_session(source)
    store.update_session(
        entry.session_key,
        input_tokens=4000,
        output_tokens=800,
        cache_read_tokens=200,
        cache_write_tokens=0,
        model="gpt-5.4",
        provider="openai-codex",
        base_url="",
    )

    monkeypatch.setattr(
        dashboard,
        "_load_session_runtime_details",
        lambda session_id: {"model": "gpt-5.4", "billing_base_url": ""},
    )
    monkeypatch.setattr(dashboard, "_get_context_limit", lambda model, base_url="": 10000)

    snapshot = dashboard.build_continuity_sessions_snapshot()

    assert snapshot["session_count"] == 1
    item = snapshot["sessions"][0]
    assert item["session_key"] == entry.session_key
    assert item["session_id"] == entry.session_id
    assert item["model"] == "gpt-5.4"
    assert item["total_tokens"] == 5000
    assert item["context_limit"] == 10000
    assert item["context_used_pct"] == 0.5
    assert item["context_remaining_pct"] == 0.5



def test_build_continuity_sessions_snapshot_returns_null_pressure_when_model_unknown(tmp_path, monkeypatch):
    dashboard = _load_dashboard_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    config = GatewayConfig(sessions_dir=hermes_home / "sessions")
    store = SessionStore(sessions_dir=config.sessions_dir, config=config)
    source = _make_gateway_source()

    entry = store.get_or_create_session(source)
    store.update_session(entry.session_key, input_tokens=100, output_tokens=20)
    monkeypatch.setattr(dashboard, "_load_session_runtime_details", lambda session_id: {})
    monkeypatch.setattr(dashboard, "_get_context_limit", lambda model, base_url="": None)

    snapshot = dashboard.build_continuity_sessions_snapshot()

    item = snapshot["sessions"][0]
    assert item["model"] is None
    assert item["context_limit"] is None
    assert item["context_used_pct"] is None
    assert item["context_remaining_pct"] is None

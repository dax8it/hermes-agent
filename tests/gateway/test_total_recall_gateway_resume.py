"""Tests for gateway continuity reset receipts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from gateway.config import GatewayConfig, Platform, SessionResetPolicy
from gateway.session import SessionSource, SessionStore


def _make_source() -> SessionSource:
    return SessionSource(platform=Platform.TELEGRAM, chat_id="123", user_id="u1")


def test_auto_reset_writes_gateway_continuity_receipt(tmp_path):
    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 42
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()

    second = store.get_or_create_session(source)

    report_path = Path(os.environ["HERMES_HOME"]) / "continuity" / "reports" / "gateway-reset-latest.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["kind"] == "gateway_session_reset"
    assert report["event_class"] == "automatic_reset"
    assert report["reason"] == "idle"
    assert report["automatic"] is True
    assert "automatic idle reset" in report["operator_summary"].lower()
    assert report["old_session_id"] == first.session_id
    assert report["new_session_id"] == second.session_id
    assert report["had_activity"] is True
    assert report["subject"]["session_key"] == first.session_key


def test_auto_reset_runs_post_reset_continuity_refresh(tmp_path, monkeypatch):
    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 42
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()

    captured = {}

    def _record(**kwargs):
        captured.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr("gateway.session.run_post_reset_continuity_refresh", _record)
    second = store.get_or_create_session(source)

    assert captured["session_key"] == first.session_key
    assert captured["session_id"] == second.session_id
    assert captured["reason"] == "idle"
    assert captured["automatic"] is True


def test_manual_reset_writes_gateway_continuity_receipt(tmp_path):
    config = GatewayConfig()
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    store._save()

    reset = store.reset_session(first.session_key)

    report_path = Path(os.environ["HERMES_HOME"]) / "continuity" / "reports" / "gateway-reset-latest.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["kind"] == "gateway_session_reset"
    assert report["event_class"] == "manual_reset"
    assert report["reason"] == "manual_reset"
    assert report["automatic"] is False
    assert report["old_session_id"] == first.session_id
    assert report["new_session_id"] == reset.session_id


def test_manual_reset_runs_post_reset_continuity_refresh(tmp_path, monkeypatch):
    config = GatewayConfig()
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    store._save()

    captured = {}

    def _record(**kwargs):
        captured.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr("gateway.session.run_post_reset_continuity_refresh", _record)
    reset = store.reset_session(first.session_key)

    assert reset is not None
    assert captured["session_key"] == first.session_key
    assert captured["session_id"] == reset.session_id
    assert captured["reason"] == "manual_reset"
    assert captured["automatic"] is False


def test_auto_reset_receipt_failure_creates_gateway_incident(tmp_path, monkeypatch):
    from hermes_continuity import incidents as incidents_module

    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()

    def boom(**kwargs):
        raise RuntimeError("gateway receipt write failed")

    monkeypatch.setattr("gateway.session.write_gateway_reset_receipt", boom)
    store.get_or_create_session(source)

    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "gateway_reset"]
    assert len(matching) == 1
    shown = incidents_module.get_continuity_incident(matching[0]["incident_id"])
    assert shown["payload"]["verdict"] == "DEGRADED_CONTINUE"


def test_auto_reset_refresh_failure_creates_gateway_incident(tmp_path, monkeypatch):
    from hermes_continuity import incidents as incidents_module

    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()

    def boom(**kwargs):
        raise RuntimeError("post-reset refresh exploded")

    monkeypatch.setattr("gateway.session.run_post_reset_continuity_refresh", boom)
    store.get_or_create_session(source)

    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "gateway_reset"]
    assert len(matching) == 1
    shown = incidents_module.get_continuity_incident(matching[0]["incident_id"])
    assert shown["payload"]["summary"] == "Automatic post-reset continuity refresh failed to run."


def test_missing_gateway_receipt_detection_creates_incident(tmp_path):
    from hermes_continuity import incidents as incidents_module
    from hermes_continuity.receipts import detect_missing_gateway_reset_receipt

    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()
    second = store.get_or_create_session(source)

    report_path = Path(os.environ["HERMES_HOME"]) / "continuity" / "reports" / "gateway-reset-latest.json"
    report_path.unlink()
    detected = detect_missing_gateway_reset_receipt(
        session_key=first.session_key,
        old_session_id=first.session_id,
        new_session_id=second.session_id,
        reason="idle",
        automatic=True,
    )

    assert detected["status"] == "MISSING"
    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "gateway_reset"]
    assert len(matching) == 1


def test_stale_gateway_receipt_detection_creates_incident(tmp_path):
    from hermes_continuity import incidents as incidents_module
    from hermes_continuity.receipts import detect_missing_gateway_reset_receipt

    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()
    second = store.get_or_create_session(source)

    report_path = Path(os.environ["HERMES_HOME"]) / "continuity" / "reports" / "gateway-reset-latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["generated_at"] = "2020-01-01T00:00:00Z"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    detected = detect_missing_gateway_reset_receipt(
        session_key=first.session_key,
        old_session_id=first.session_id,
        new_session_id=second.session_id,
        reason="idle",
        automatic=True,
    )

    assert detected["status"] == "MISSING"
    assert any("stale" in issue.lower() for issue in detected["issues"])
    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "gateway_reset"]
    assert len(matching) == 1


def test_repeated_auto_resets_rotate_sessions_and_refresh_each_time(tmp_path, monkeypatch):
    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    refresh_calls = []

    def _record(**kwargs):
        refresh_calls.append(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr("gateway.session.run_post_reset_continuity_refresh", _record)

    first = store.get_or_create_session(source)
    first.total_tokens = 11
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()

    second = store.get_or_create_session(source)
    second.total_tokens = 17
    second.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()

    third = store.get_or_create_session(source)

    assert len(refresh_calls) == 2
    assert refresh_calls[0]["session_id"] == second.session_id
    assert refresh_calls[1]["session_id"] == third.session_id
    assert refresh_calls[0]["automatic"] is True
    assert refresh_calls[1]["automatic"] is True

    report_path = Path(os.environ["HERMES_HOME"]) / "continuity" / "reports" / "gateway-reset-latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["old_session_id"] == second.session_id
    assert report["new_session_id"] == third.session_id
    assert report["subject"]["old_session_id"] == second.session_id
    assert report["subject"]["new_session_id"] == third.session_id


def test_successful_auto_reset_receipt_can_self_heal_when_it_only_goes_stale(tmp_path):
    from hermes_continuity.receipts import self_heal_operator_event_surfaces

    config = GatewayConfig(default_reset_policy=SessionResetPolicy(mode="idle", idle_minutes=1))
    store = SessionStore(sessions_dir=tmp_path / "sessions", config=config)
    source = _make_source()

    first = store.get_or_create_session(source)
    first.total_tokens = 7
    first.updated_at = datetime.now() - timedelta(minutes=5)
    store._save()
    second = store.get_or_create_session(source)

    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rehydrate_dir.mkdir(parents=True, exist_ok=True)

    reports_dir.joinpath("verify-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-03T00:00:00Z"}),
        encoding="utf-8",
    )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-03T00:00:00Z"}),
        encoding="utf-8",
    )

    report_path = reports_dir / "gateway-reset-latest.json"
    stale_report = json.loads(report_path.read_text(encoding="utf-8"))
    stale_report["generated_at"] = "2020-01-01T00:00:00Z"
    report_path.write_text(json.dumps(stale_report), encoding="utf-8")

    result = self_heal_operator_event_surfaces()

    assert result["status"] == "OK"
    assert result["healed_targets"] == ["gateway-reset", "cron-continuity"]

    healed = json.loads(report_path.read_text(encoding="utf-8"))
    assert healed["event_class"] == "surface_self_heal"
    assert healed["maintenance"] is True
    assert healed["previous_receipt"]["old_session_id"] == first.session_id
    assert healed["previous_receipt"]["new_session_id"] == second.session_id

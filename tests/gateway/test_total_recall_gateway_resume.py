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
    assert report["reason"] == "idle"
    assert report["automatic"] is True
    assert report["old_session_id"] == first.session_id
    assert report["new_session_id"] == second.session_id
    assert report["had_activity"] is True


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
    assert report["reason"] == "manual_reset"
    assert report["automatic"] is False
    assert report["old_session_id"] == first.session_id
    assert report["new_session_id"] == reset.session_id


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

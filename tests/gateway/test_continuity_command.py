"""Tests for gateway /continuity command."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource, build_session_key


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(text=text, source=_make_source(), message_id="m1")


def _make_runner(session_entry: SessionEntry):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")})
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = session_entry
    runner.session_store.load_transcript.return_value = []
    runner.session_store.has_any_sessions.return_value = True
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._session_db = None
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._show_reasoning = False
    runner._is_user_authorized = lambda _source: True
    runner._set_session_env = lambda _context: None
    runner._should_send_voice_reply = lambda *_args, **_kwargs: False
    runner._send_voice_reply = AsyncMock()
    runner._capture_gateway_honcho_if_configured = lambda *args, **kwargs: None
    runner._emit_gateway_run_progress = AsyncMock()
    return runner


@pytest.mark.asyncio
async def test_continuity_in_help_output():
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    from gateway.hooks import HookRegistry
    runner.hooks = HookRegistry()
    result = await runner._handle_help_command(_make_event("/help"))
    assert "/continuity" in result


@pytest.mark.asyncio
async def test_handle_continuity_command_formats_benchmark():
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    with patch("hermes_continuity.admin.run_continuity_admin_command", return_value={"status": "OK", "kind": "benchmark", "payload": {"status": "PASS", "passed_count": 11, "case_count": 11, "results": []}}):
        result = await runner._handle_continuity_command(_make_event("/continuity benchmark"))
    assert "Continuity benchmark: PASS" in result
    assert "Cases: 11/11 passed" in result


@pytest.mark.asyncio
async def test_handle_continuity_command_formats_status():
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    with patch(
        "hermes_continuity.admin.run_continuity_admin_command",
        return_value={
            "status": "OK",
            "kind": "status",
            "payload": {
                "hermes_home": "/tmp/hermes",
                "checkpoint_id": "ckpt_1",
                "manifest_exists": True,
                "anchor_exists": True,
                "reports": {"verify": {"status": "PASS", "exists": True}},
                "external_memory": {"QUARANTINED": 1, "PENDING": 0, "PROMOTED": 2, "REJECTED": 0},
            },
        },
    ):
        result = await runner._handle_continuity_command(_make_event("/continuity status"))
    assert "Continuity status" in result
    assert "Checkpoint: ckpt_1" in result
    assert "verify: PASS" in result


@pytest.mark.asyncio
async def test_handle_continuity_command_panel_returns_api_server_url():
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    runner.config.platforms[Platform.API_SERVER] = PlatformConfig(enabled=True, extra={"host": "127.0.0.1", "port": 8879})
    result = await runner._handle_continuity_command(_make_event("/continuity panel"))
    assert "http://127.0.0.1:8879/continuity/" in result
    assert "API server: enabled" in result

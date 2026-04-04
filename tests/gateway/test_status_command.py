"""Tests for gateway /status behavior and token persistence."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource, build_session_key
from gateway.run import _history_visible_to_agent


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        source=_make_source(),
        message_id="m1",
    )


def _make_runner(session_entry: SessionEntry):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = session_entry
    runner.session_store.load_transcript.return_value = []
    runner.session_store.has_any_sessions.return_value = True
    runner.session_store.append_to_transcript = MagicMock()
    runner.session_store.rewrite_transcript = MagicMock()
    runner.session_store.update_session = MagicMock()
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._session_runtime_status = {}
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
async def test_status_command_reports_running_agent_without_interrupt(monkeypatch):
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
        total_tokens=321,
    )
    runner = _make_runner(session_entry)
    running_agent = MagicMock()
    runner._running_agents[build_session_key(_make_source())] = running_agent

    result = await runner._handle_message(_make_event("/status"))

    assert "**Session ID:** `sess-1`" in result
    assert "**Tokens:** 321" in result
    assert "**Agent Running:** Yes ⚡" in result
    assert "**Runtime State:** `running`" in result
    running_agent.interrupt.assert_not_called()
    assert runner._pending_messages == {}


@pytest.mark.asyncio
async def test_explicit_session_query_returns_real_session_id(monkeypatch):
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-real-123456",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)

    result = await runner._handle_message(_make_event("what session are you on"))

    assert "Hermes session identity" in result
    assert "`sess-real-123456`" in result
    assert "runtime_state: `idle`" in result
    assert "Profile" in result
    assert runner.session_store.append_to_transcript.call_count == 2
    first_call = runner.session_store.append_to_transcript.call_args_list[0]
    second_call = runner.session_store.append_to_transcript.call_args_list[1]
    assert first_call.args[0] == "sess-real-123456"
    assert first_call.args[1]["role"] == "user"
    assert first_call.args[1]["content"] == "what session are you on"
    assert second_call.args[0] == "sess-real-123456"
    assert second_call.args[1]["role"] == "assistant"
    assert "Hermes session identity" in second_call.args[1]["content"]


@pytest.mark.asyncio
async def test_explicit_runtime_query_reports_compacting(monkeypatch):
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-real-123456",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    runner._running_agents[session_entry.session_key] = MagicMock()
    status = runner._get_session_runtime_status(session_entry.session_key)
    status["compaction_active"] = True
    status["compaction_started_at"] = datetime.now().timestamp()
    status["last_progress_at"] = datetime.now().timestamp()

    result = await runner._handle_message(_make_event("are you compacting"))

    assert "Hermes runtime state" in result
    assert "runtime_state: `compacting`" in result
    assert "Compacting context now" in result
    assert runner.session_store.append_to_transcript.call_count == 2
    assert runner.session_store.append_to_transcript.call_args_list[0].args[1]["content"] == "are you compacting"
    assert "Hermes runtime state" in runner.session_store.append_to_transcript.call_args_list[1].args[1]["content"]


@pytest.mark.asyncio
async def test_explicit_session_query_persists_even_while_agent_running(monkeypatch):
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-running-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    running_agent = MagicMock()
    runner._running_agents[session_entry.session_key] = running_agent

    result = await runner._handle_message(_make_event("what session are you on"))

    assert "Hermes session identity" in result
    running_agent.interrupt.assert_not_called()
    assert runner.session_store.append_to_transcript.call_count == 2


def test_record_runtime_status_event_throttles_duplicate_context_pressure():
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)

    first = runner._record_runtime_status_event(
        session_entry.session_key,
        "context_pressure",
        "warning",
    )
    second = runner._record_runtime_status_event(
        session_entry.session_key,
        "context_pressure",
        "warning",
    )

    assert first is True
    assert second is False


def test_record_runtime_status_event_throttles_duplicate_compaction():
    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)

    first = runner._record_runtime_status_event(
        session_entry.session_key,
        "compaction",
        "Compacting context now.",
    )
    second = runner._record_runtime_status_event(
        session_entry.session_key,
        "compaction",
        "Compacting context now.",
    )

    assert first is True
    assert second is False


def test_history_visible_to_agent_skips_session_meta_and_keeps_tool_context():
    history = [
        {"role": "session_meta", "content": "very large tool blob"},
        {"role": "system", "content": "rebuilt elsewhere"},
        {"role": "user", "content": "hello", "timestamp": "t1"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "tc1"}],
            "timestamp": "t2",
        },
        {"role": "tool", "content": "tool output", "tool_call_id": "tc1", "timestamp": "t3"},
    ]

    visible = _history_visible_to_agent(history)

    assert [msg["role"] for msg in visible] == ["user", "assistant", "tool"]
    assert all("timestamp" not in msg for msg in visible)


@pytest.mark.asyncio
async def test_handle_message_persists_agent_token_counts(monkeypatch):
    import gateway.run as gateway_run

    session_entry = SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner = _make_runner(session_entry)
    runner.session_store.load_transcript.return_value = [{"role": "user", "content": "earlier"}]
    runner._run_agent = AsyncMock(
        return_value={
            "final_response": "ok",
            "messages": [],
            "tools": [],
            "history_offset": 0,
            "last_prompt_tokens": 80,
            "input_tokens": 120,
            "output_tokens": 45,
            "model": "openai/test-model",
        }
    )

    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})
    monkeypatch.setattr(
        "agent.model_metadata.get_model_context_length",
        lambda *_args, **_kwargs: 100000,
    )

    result = await runner._handle_message(_make_event("hello"))

    assert result == "ok"
    runner.session_store.update_session.assert_called_once_with(
        session_entry.session_key,
        input_tokens=120,
        output_tokens=45,
        cache_read_tokens=0,
        cache_write_tokens=0,
        last_prompt_tokens=80,
        model="openai/test-model",
        estimated_cost_usd=None,
        cost_status=None,
        cost_source=None,
        provider=None,
        base_url=None,
    )

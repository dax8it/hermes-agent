"""Tests for fail-closed continuity gating during compaction."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from run_agent import AIAgent
from hermes_state import SessionDB


class _DummyTodoStore:
    def format_for_injection(self):
        return None


def _make_agent(tmp_path) -> AIAgent:
    agent = AIAgent.__new__(AIAgent)
    agent.session_id = "sess_compact"
    agent.model = "openai/gpt-5.4-mini"
    agent.platform = "cli"
    agent.logs_dir = tmp_path / "logs"
    agent.logs_dir.mkdir(parents=True, exist_ok=True)
    agent.session_log_file = agent.logs_dir / "session_sess_compact.json"
    agent._todo_store = _DummyTodoStore()
    agent._cached_system_prompt = "old-system"
    agent._context_pressure_warned = True
    agent._last_flushed_db_idx = 5
    agent._continuity_config = {
        "enabled": True,
        "checkpoint_on_compact": True,
        "fail_closed_on_compact": True,
    }
    agent._build_system_prompt = MagicMock(return_value="new-system")
    agent._invalidate_system_prompt = MagicMock()
    agent.flush_memories = MagicMock()
    agent._safe_print = MagicMock()
    agent.quiet_mode = True

    compressor = MagicMock()
    compressor.compress.return_value = [{"role": "user", "content": "summary"}]
    compressor.threshold_tokens = 1000
    compressor.last_prompt_tokens = 0
    compressor.last_completion_tokens = 0
    agent.context_compressor = compressor

    db = SessionDB(db_path=Path(tmp_path) / "state.db")
    db.create_session("sess_compact", "cli", model="openai/gpt-5.4-mini")
    db.append_message("sess_compact", "user", "before compaction")
    agent._session_db = db
    return agent


def test_compaction_blocks_when_continuity_verification_fails(tmp_path):
    agent = _make_agent(tmp_path)
    original_session_id = agent.session_id

    with patch("run_agent.checkpoint_and_verify_before_compaction") as guard:
        guard.return_value = {
            "ok": False,
            "checkpoint": {"checkpoint_id": "ckpt_fail"},
            "verify": {"status": "FAIL", "errors": ["Digest mismatch"]},
            "report_path": str(Path(tmp_path) / "continuity/reports/compact-gate-latest.json"),
            "blocked": True,
        }
        with pytest.raises(RuntimeError, match="Continuity gate blocked compaction"):
            agent._compress_context([
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ], "system prompt")

    assert agent.session_id == original_session_id
    assert agent._session_db.get_session(original_session_id) is not None
    assert agent._last_flushed_db_idx == 5
    agent._session_db.close()


def test_compaction_continues_when_continuity_verification_passes(tmp_path):
    agent = _make_agent(tmp_path)
    old_session_id = agent.session_id

    with patch("run_agent.checkpoint_and_verify_before_compaction") as guard:
        guard.return_value = {
            "ok": True,
            "checkpoint": {"checkpoint_id": "ckpt_ok"},
            "verify": {"status": "PASS", "errors": [], "warnings": []},
            "report_path": str(Path(tmp_path) / "continuity/reports/compact-gate-latest.json"),
            "blocked": False,
        }
        compressed, new_system_prompt = agent._compress_context([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ], "system prompt")

    assert compressed == [{"role": "user", "content": "summary"}]
    assert new_system_prompt == "new-system"
    assert agent.session_id != old_session_id
    assert agent._session_db.get_session(old_session_id)["end_reason"] == "compression"
    assert agent._session_db.get_session(agent.session_id)["parent_session_id"] == old_session_id
    agent._session_db.close()


def test_compaction_gate_skipped_when_continuity_disabled(tmp_path):
    agent = _make_agent(tmp_path)
    agent._continuity_config = {"enabled": False}

    with patch("run_agent.checkpoint_and_verify_before_compaction") as guard:
        agent._compress_context([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ], "system prompt")
        guard.assert_not_called()

    agent._session_db.close()

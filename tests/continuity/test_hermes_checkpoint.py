"""Tests for scripts/continuity/hermes_checkpoint.py."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

from hermes_state import SessionDB

CHECKPOINT_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/continuity/hermes_checkpoint.py"


@pytest.fixture
def checkpoint_module():
    spec = importlib.util.spec_from_file_location("hermes_checkpoint_test", CHECKPOINT_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_minimal_config(hermes_home: Path) -> None:
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": "openai/gpt-5.4-mini",
                "toolsets": ["hermes-cli", "file"],
                "skills": {"external_dirs": []},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_memory_files(hermes_home: Path) -> None:
    memories = hermes_home / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "MEMORY.md").write_text("Stable environment note\n", encoding="utf-8")
    (memories / "USER.md").write_text("Alex prefers direct answers\n", encoding="utf-8")


def test_generate_checkpoint_writes_latest_manifest_and_derived_state(checkpoint_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "AGENTS.md").write_text("# project instructions\n", encoding="utf-8")

    _write_minimal_config(hermes_home)
    _write_memory_files(hermes_home)

    db = SessionDB(db_path=hermes_home / "state.db")
    db.create_session("sess_checkpoint", "telegram", model="openai/gpt-5.4-mini")
    db.append_message("sess_checkpoint", "user", "hello checkpoint")
    db.close()

    result = checkpoint_module.generate_checkpoint(session_id="sess_checkpoint", cwd=project)

    assert result["status"] == "PASS"
    manifest_path = Path(result["manifest_path"])
    latest_path = Path(result["latest_manifest_path"])
    assert manifest_path.exists()
    assert latest_path.exists()

    manifest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "hermes-total-recall-v0"
    assert manifest["session"]["active_session_id"] == "sess_checkpoint"
    assert manifest["session"]["lineage_root_session_id"] == "sess_checkpoint"
    assert manifest["verification"]["required_checks"]

    state_json = Path(manifest["derived_state"]["state_json_path"])
    state_md = Path(manifest["derived_state"]["state_md_path"])
    assert state_json.exists()
    assert state_md.exists()

    derived = json.loads(state_json.read_text(encoding="utf-8"))
    assert derived["active_session_id"] == "sess_checkpoint"
    assert derived["lineage_root_session_id"] == "sess_checkpoint"

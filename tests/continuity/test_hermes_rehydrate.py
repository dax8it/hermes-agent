"""Tests for scripts/continuity/hermes_rehydrate.py."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

from hermes_state import SessionDB


CHECKPOINT_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/continuity/hermes_checkpoint.py"
VERIFY_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/continuity/hermes_verify.py"
REHYDRATE_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/continuity/hermes_rehydrate.py"


@pytest.fixture
def checkpoint_module():
    spec = importlib.util.spec_from_file_location("hermes_checkpoint_for_rehydrate_test", CHECKPOINT_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verify_module():
    spec = importlib.util.spec_from_file_location("hermes_verify_for_rehydrate_test", VERIFY_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rehydrate_module():
    spec = importlib.util.spec_from_file_location("hermes_rehydrate_test", REHYDRATE_SCRIPT_PATH)
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


def _prepare_checkpoint(checkpoint_module, hermes_home: Path, project: Path, session_id: str = "sess_root") -> None:
    _write_minimal_config(hermes_home)
    _write_memory_files(hermes_home)

    db = SessionDB(db_path=hermes_home / "state.db")
    db.create_session(session_id, "telegram", model="openai/gpt-5.4-mini")
    db.append_message(session_id, "user", "Hello from Telegram")
    db.close()

    project.mkdir(parents=True, exist_ok=True)
    (project / ".git").mkdir(exist_ok=True)
    (project / "AGENTS.md").write_text("# project instructions\n", encoding="utf-8")

    checkpoint_module.generate_checkpoint(session_id=session_id, cwd=project)


def test_rehydrate_latest_checkpoint_creates_receipt_and_target_session(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_source")

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_rehydrated")

    assert result["status"] == "PASS"
    assert result["resulting_session_id"] == "sess_rehydrated"
    assert result["resulting_session_created"] is True
    assert Path(result["report_path"]).exists()

    receipt = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["source_session_id"] == "sess_source"
    assert receipt["resulting_session_id"] == "sess_rehydrated"
    assert receipt["resulting_session_created"] is True
    assert receipt["target_session_contract"]["canonical_name"] == "target_session_id"
    assert receipt["target_session_contract"]["cli_flag"] == "--target-session-id"
    assert receipt["session_outcome"]["mode"] == "new_target_session"
    assert receipt["accepted_authorities"]
    assert any(item["kind"] == "checkpoint_manifest" for item in receipt["accepted_authorities"])
    assert receipt["rejected_conflicting_artifacts"] == []

    db = SessionDB(db_path=hermes_home / "state.db")
    target = db.get_session("sess_rehydrated")
    db.close()
    assert target is not None
    assert target["parent_session_id"] == "sess_source"

    latest = json.loads((hermes_home / "continuity/rehydrate/rehydrate-latest.json").read_text(encoding="utf-8"))
    assert latest["resulting_session_id"] == "sess_rehydrated"


def test_rehydrate_allows_explicit_reuse_of_checkpoint_source_session(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_source_reuse"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_source_reuse")

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_source_reuse")

    assert result["status"] == "PASS"
    assert result["resulting_session_id"] == "sess_source_reuse"
    assert result["resulting_session_created"] is False

    receipt = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["source_session_id"] == "sess_source_reuse"
    assert receipt["resulting_session_id"] == "sess_source_reuse"
    assert receipt["resulting_session_created"] is False
    assert receipt["session_outcome"]["mode"] == "source_session_reuse"
    assert receipt["session_outcome"]["reuse_mode"] == "source_session"
    assert any(
        item["kind"] == "target_session" and item.get("reuse_mode") == "source_session"
        for item in receipt["accepted_authorities"]
    )


def test_rehydrate_fails_closed_when_verification_breaks(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_fail"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_fail")

    (hermes_home / "memories" / "MEMORY.md").write_text("mutated\n", encoding="utf-8")

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_should_not_create")

    assert result["status"] == "FAIL"
    assert any("Digest mismatch for memory file" in err for err in result["errors"])

    db = SessionDB(db_path=hermes_home / "state.db")
    assert db.get_session("sess_should_not_create") is None
    db.close()

    receipt = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "FAIL"
    assert any("Digest mismatch for memory file" in err for err in receipt["errors"])
    assert receipt["failure_class"] == "stale_live_checkpoint"
    assert "stale" in receipt["operator_summary"].lower()
    assert any("fresh checkpoint" in item.lower() for item in receipt["remediation"])
    assert receipt["incident"]["incident_id"].startswith("incident_")
    assert receipt["incident"]["transition_type"] == "rehydrate"
    assert receipt["incident"]["verdict"] == "FAIL_CLOSED"


def test_rehydrate_allows_warn_verification_and_preserves_warning_status(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_warn"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)

    _write_minimal_config(hermes_home)
    _write_memory_files(hermes_home)

    db = SessionDB(db_path=hermes_home / "state.db")
    db.create_session("sess_warn_source", "telegram", model="openai/gpt-5.4-mini")
    db.close()

    checkpoint_module.generate_checkpoint(session_id="sess_warn_source", cwd=project)

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_warn_target")

    assert result["status"] == "WARN"
    assert result["resulting_session_id"] == "sess_warn_target"
    assert result["resulting_session_created"] is True

    receipt = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "WARN"
    assert receipt["warnings"]


def test_rehydrate_rejects_target_session_without_source_lineage(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_rootless"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)

    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_rootless_source")

    manifest_path = hermes_home / "continuity" / "manifests" / "latest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["session"]["active_session_id"] = None
    manifest["session"]["lineage_root_session_id"] = None
    manifest["derived_state"] = {}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    checkpoint_manifest_path = hermes_home / "continuity" / "manifests" / f"{manifest['checkpoint_id']}.json"
    checkpoint_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    from hermes_continuity.anchors import write_anchor

    write_anchor(
        checkpoint_id=manifest["checkpoint_id"],
        manifest_path=checkpoint_manifest_path,
        latest_manifest_path=manifest_path,
        derived_state={},
    )

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_rootless")

    assert result["status"] == "FAIL"
    assert any("Cannot materialize a target session without a source_session_id" in err for err in result["errors"])
    db = SessionDB(db_path=hermes_home / "state.db")
    assert db.get_session("sess_rootless") is None
    db.close()


def test_rehydrate_rejects_target_session_from_unrelated_lineage(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_cross_lineage"
    project.mkdir()
    monkeypatch.chdir(project)

    db = SessionDB(db_path=hermes_home / "state.db")
    db.create_session("sess_cron_parent", "cron", model="openai/gpt-5.4-mini")
    db.create_session("sess_existing_target", "cron", model="openai/gpt-5.4-mini", parent_session_id="sess_cron_parent")
    db.close()

    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_telegram_source")

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_existing_target")

    assert result["status"] == "FAIL"
    assert result["errors"]

    receipt = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert receipt["failure_class"] == "target_session_conflict"
    assert "conflicts with an existing session lineage" in receipt["operator_summary"]
    assert receipt["target_session_id_requested"] == "sess_existing_target"


def test_rehydrate_fails_closed_when_state_db_is_unavailable_during_target_creation(checkpoint_module, rehydrate_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_state_db_churn"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_db_source")

    original_create = SessionDB.create_session

    def _locked_create(self, session_id, source, **kwargs):
        if session_id == "sess_db_locked_target":
            raise RuntimeError("database is locked")
        return original_create(self, session_id, source, **kwargs)

    monkeypatch.setattr(SessionDB, "create_session", _locked_create)

    result = rehydrate_module.rehydrate_latest_checkpoint(target_session_id="sess_db_locked_target")

    assert result["status"] == "FAIL"
    assert any("State DB unavailable while materializing target session" in err for err in result["errors"])

    receipt = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert receipt["failure_class"] == "target_session_state_db_unavailable"
    assert "state db was unavailable" in receipt["operator_summary"].lower()

    db = SessionDB(db_path=hermes_home / "state.db")
    assert db.get_session("sess_db_locked_target") is None
    db.close()


def test_rehydrate_main_accepts_target_session_id_alias(checkpoint_module, rehydrate_module, tmp_path, monkeypatch, capsys):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_alias"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_alias_source")

    exit_code = rehydrate_module.main(["--target-session-id", "sess_alias_target"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "PASS"
    assert output["resulting_session_id"] == "sess_alias_target"
    assert output["resulting_session_created"] is True
    assert output["target_session_contract"]["canonical_name"] == "target_session_id"

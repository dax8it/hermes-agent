"""Tests for scripts/continuity/hermes_verify.py."""

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


@pytest.fixture
def checkpoint_module():
    spec = importlib.util.spec_from_file_location("hermes_checkpoint_for_verify_test", CHECKPOINT_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verify_module():
    spec = importlib.util.spec_from_file_location("hermes_verify_test", VERIFY_SCRIPT_PATH)
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


def test_verify_latest_checkpoint_passes_on_matching_artifacts(checkpoint_module, verify_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project)

    result = verify_module.verify_latest_checkpoint()

    assert result["status"] == "PASS"
    assert result["errors"] == []
    assert result["warnings"] == []

    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["manifest"]["active_session_id"] == "sess_root"
    assert report["required_checks"]
    assert report["anchor"]["checkpoint_id"] == report["checkpoint_id"]
    assert report["anchor"]["signature_algorithm"] == "ed25519"

    latest = json.loads((hermes_home / "continuity/reports/verify-latest.json").read_text(encoding="utf-8"))
    assert latest["status"] == "PASS"


def test_verify_latest_checkpoint_fails_when_memory_digest_changes(checkpoint_module, verify_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_mutation"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_digest")

    (hermes_home / "memories" / "MEMORY.md").write_text("Stable environment note\nmutated\n", encoding="utf-8")

    result = verify_module.verify_latest_checkpoint()

    assert result["status"] == "FAIL"
    assert any("Digest mismatch for memory file" in err for err in result["errors"])
    latest = json.loads((hermes_home / "continuity/reports/verify-latest.json").read_text(encoding="utf-8"))
    assert latest["failure_class"] == "stale_live_checkpoint"
    assert "live profile state" in latest["operator_summary"]
    assert any("fresh checkpoint" in item.lower() for item in latest["remediation"])
    assert latest["status"] == "FAIL"


def test_verify_latest_checkpoint_fails_when_manifest_missing(verify_module):
    result = verify_module.verify_latest_checkpoint()

    assert result["status"] == "FAIL"
    assert any("Missing latest checkpoint manifest" in err for err in result["errors"])
    assert Path(result["report_path"]).exists()


def test_verify_latest_checkpoint_fails_when_anchor_signature_is_tampered(checkpoint_module, verify_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_anchor_tamper"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_anchor")

    latest_anchor_path = hermes_home / "continuity" / "anchors" / "latest.json"
    latest_anchor = json.loads(latest_anchor_path.read_text(encoding="utf-8"))
    anchor_path = hermes_home / "continuity" / "anchors" / f"{latest_anchor['checkpoint_id']}.json"
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    anchor["signature"] = "ZmFrZV9zaWduYXR1cmU="
    anchor_path.write_text(json.dumps(anchor), encoding="utf-8")

    result = verify_module.verify_latest_checkpoint()

    assert result["status"] == "FAIL"
    assert any("Invalid continuity anchor signature" in err for err in result["errors"])


def test_verify_latest_checkpoint_fails_when_latest_manifest_is_tampered_after_anchor(checkpoint_module, verify_module, tmp_path, monkeypatch):
    hermes_home = Path(os.environ["HERMES_HOME"])
    project = tmp_path / "project_manifest_tamper"
    project.mkdir()
    monkeypatch.chdir(project)
    _prepare_checkpoint(checkpoint_module, hermes_home, project, session_id="sess_manifest")

    manifest_path = hermes_home / "continuity" / "manifests" / "latest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["config"]["selected_model"] = "tampered-model"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_module.verify_latest_checkpoint()

    assert result["status"] == "FAIL"
    assert any("Anchored artifact digest mismatch" in err for err in result["errors"])


def test_verify_main_fails_closed_on_malformed_explicit_manifest(verify_module, tmp_path, capsys):
    manifest_path = tmp_path / "bad-manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    exit_code = verify_module.main(["--manifest-path", str(manifest_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "FAIL"
    assert any("Unable to read checkpoint manifest" in err for err in output["errors"])
    assert Path(output["report_path"]).exists()


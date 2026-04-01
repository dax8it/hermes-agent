"""Tests for scripts/continuity/hermes_external_memory.py."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import yaml

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/continuity/hermes_external_memory.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("hermes_external_memory_cli_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_external_memory_config(hermes_home: Path, *, enabled: bool = True) -> None:
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump({"continuity": {"external_memory_enabled": enabled}}, sort_keys=False),
        encoding="utf-8",
    )


def test_cli_ingest_list_show_promote_flow(capsys):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    exit_code = module.main([
        "ingest",
        "--source-kind", "external_worker",
        "--source-session-id", "sess_cli_1",
        "--source-agent", "sparky",
        "--target", "memory",
        "--content", "CLI imported memory candidate",
    ])
    ingest = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert ingest["status"] == "QUARANTINED"

    exit_code = module.main(["list", "--state", "QUARANTINED"])
    listing = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert any(row["candidate_id"] == ingest["candidate_id"] for row in listing["candidates"])

    exit_code = module.main(["show", ingest["candidate_id"]])
    shown = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert shown["candidate"]["content"] == "CLI imported memory candidate"

    exit_code = module.main(["promote", ingest["candidate_id"], "--reviewer", "filippo"])
    promoted = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert promoted["status"] == "PROMOTED"

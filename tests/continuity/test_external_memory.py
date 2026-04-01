"""Tests for external memory inbox -> review -> promote flow."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml


def _load_module():
    from hermes_continuity import external_memory

    return external_memory


def _write_external_memory_config(hermes_home: Path, *, enabled: bool = True) -> None:
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "continuity": {
                    "external_memory_enabled": enabled,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_ingest_external_memory_candidate_writes_inbox_and_quarantine(tmp_path, monkeypatch):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    result = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_worker_1",
            "source_agent": "sparky",
            "target": "memory",
            "content": "Repo uses fail-closed compaction continuity gating.",
            "evidence": ["commit:d2eaab57"],
        }
    )

    assert result["status"] == "QUARANTINED"
    inbox_path = Path(result["inbox_path"])
    quarantine_path = Path(result["quarantine_path"])
    assert inbox_path.exists()
    assert quarantine_path.exists()
    assert Path(result["receipt_path"]).exists()

    candidate = json.loads(quarantine_path.read_text(encoding="utf-8"))
    assert candidate["schema_version"] == "hermes-external-memory-v0"
    assert candidate["state"] == "QUARANTINED"
    assert candidate["target"] == "memory"
    assert candidate["provenance"]["source_kind"] == "external_worker"
    assert candidate["candidate_sha256"]

    inbox = json.loads(inbox_path.read_text(encoding="utf-8"))
    assert inbox["candidate_id"] == candidate["candidate_id"]
    assert inbox["raw_payload"]["source_agent"] == "sparky"


def test_list_and_show_external_memory_candidates_expose_admin_surface(tmp_path, monkeypatch):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    ingest = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_worker_admin",
            "source_agent": "sparky",
            "target": "memory",
            "content": "Admin surface should expose this candidate.",
        }
    )

    listing = module.list_external_memory_candidates(state="QUARANTINED")
    assert listing["status"] == "OK"
    assert listing["candidate_count"] >= 1
    assert any(row["candidate_id"] == ingest["candidate_id"] for row in listing["candidates"])

    shown = module.get_external_memory_candidate(ingest["candidate_id"])
    assert shown["status"] == "OK"
    assert shown["candidate"]["content"] == "Admin surface should expose this candidate."


def test_promote_external_memory_candidate_updates_canonical_memory_and_moves_candidate(tmp_path, monkeypatch):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    ingest = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_worker_2",
            "source_agent": "smarty",
            "target": "user",
            "content": "Alex wants measurable continuity advantages, not vague memory vibes.",
        }
    )

    result = module.promote_external_memory_candidate(
        ingest["candidate_id"],
        reviewer="filippo",
    )

    assert result["status"] == "PROMOTED"
    assert Path(result["promotion_receipt_path"]).exists()
    assert Path(result["promoted_path"]).exists()
    assert not Path(ingest["quarantine_path"]).exists()

    user_memory = (hermes_home / "memories" / "USER.md").read_text(encoding="utf-8")
    assert "Alex wants measurable continuity advantages" in user_memory

    promoted = json.loads(Path(result["promoted_path"]).read_text(encoding="utf-8"))
    assert promoted["state"] == "PROMOTED"
    assert promoted["review"]["reviewer"] == "filippo"


def test_reject_external_memory_candidate_moves_candidate_without_writing_memory(tmp_path, monkeypatch):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    ingest = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_worker_3",
            "source_agent": "sparky",
            "target": "memory",
            "content": "Temporary task note that should not be promoted.",
        }
    )

    result = module.reject_external_memory_candidate(
        ingest["candidate_id"],
        reviewer="filippo",
        reason="temporary task state",
    )

    assert result["status"] == "REJECTED"
    assert Path(result["decision_receipt_path"]).exists()
    assert Path(result["rejected_path"]).exists()
    assert not Path(ingest["quarantine_path"]).exists()

    memory_path = hermes_home / "memories" / "MEMORY.md"
    if memory_path.exists():
        assert "Temporary task note that should not be promoted." not in memory_path.read_text(encoding="utf-8")


def test_ingest_external_memory_candidate_rejects_when_disabled():
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=False)

    result = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_disabled",
            "target": "memory",
            "content": "should be blocked",
        }
    )

    assert result["status"] == "REJECTED"
    assert any("external_memory_enabled" in err for err in result["errors"])


def test_ingest_external_memory_candidate_rejects_malformed_payload():
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    result = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "target": "memory",
            "content": "missing source_session_id",
        }
    )

    assert result["status"] == "REJECTED"
    assert any("source_session_id" in err for err in result["errors"])


def test_promote_external_memory_candidate_fails_if_candidate_is_tampered(tmp_path, monkeypatch):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    ingest = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_worker_4",
            "source_agent": "sparky",
            "target": "memory",
            "content": "Trusted continuity fact",
        }
    )
    quarantine_path = Path(ingest["quarantine_path"])
    candidate = json.loads(quarantine_path.read_text(encoding="utf-8"))
    candidate["content"] = "Tampered continuity fact"
    quarantine_path.write_text(json.dumps(candidate), encoding="utf-8")

    result = module.promote_external_memory_candidate(ingest["candidate_id"], reviewer="filippo")

    assert result["status"] == "FAILED"
    assert any("content_sha256 mismatch" in err or "candidate_sha256 mismatch" in err for err in result["errors"])
    assert quarantine_path.exists()


def test_promote_external_memory_candidate_recovers_from_archive_failure_without_duplicate_memory(tmp_path, monkeypatch):
    module = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    _write_external_memory_config(hermes_home, enabled=True)

    ingest = module.ingest_external_memory_candidate(
        {
            "source_kind": "external_worker",
            "source_session_id": "sess_worker_5",
            "source_agent": "smarty",
            "target": "memory",
            "content": "Recovery-safe promoted fact",
        }
    )

    real_atomic = module.atomic_json_write
    candidate_id = ingest["candidate_id"]
    failed_once = {"value": False}

    def flaky_atomic(path, payload):
        if (
            not failed_once["value"]
            and Path(path).parent.name == "promoted"
            and Path(path).name == f"{candidate_id}.json"
        ):
            failed_once["value"] = True
            raise OSError("simulated promoted write failure")
        return real_atomic(path, payload)

    monkeypatch.setattr(module, "atomic_json_write", flaky_atomic)
    first = module.promote_external_memory_candidate(candidate_id, reviewer="filippo")
    assert first["status"] == "RECOVERY_REQUIRED"
    pending_path = Path(first["pending_path"])
    assert pending_path.exists()

    listing = module.list_external_memory_candidates(state="PENDING")
    assert any(row["candidate_id"] == candidate_id for row in listing["candidates"])

    monkeypatch.setattr(module, "atomic_json_write", real_atomic)
    second = module.promote_external_memory_candidate(candidate_id, reviewer="filippo")
    assert second["status"] == "PROMOTED"
    assert not pending_path.exists()

    memory_path = hermes_home / "memories" / "MEMORY.md"
    text = memory_path.read_text(encoding="utf-8")
    assert text.count("Recovery-safe promoted fact") == 1

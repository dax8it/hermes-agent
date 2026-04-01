"""Checkpoint generation for Hermes Total Recall continuity v0."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from hermes_state import SessionDB
from utils import atomic_json_write

from .anchors import write_anchor
from .schema import REQUIRED_CHECKS, SCHEMA_VERSION, iso_z, now_utc, slug_ts
from .state_snapshot import (
    hermes_home,
    project_context_files,
    session_lineage,
    sha256_file,
    state_db_metadata,
    write_derived_state,
)


def _checkpoint_id(session_id: str) -> str:
    return f"ckpt_{slug_ts(now_utc())}_{session_id}"


def generate_checkpoint(session_id: str, cwd: Optional[Path] = None) -> Dict[str, Any]:
    home = hermes_home()
    cwd = Path(cwd or Path.cwd()).resolve()
    continuity_dir = home / "continuity"
    manifests_dir = continuity_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    config_path = home / "config.yaml"
    memory_path = home / "memories" / "MEMORY.md"
    user_path = home / "memories" / "USER.md"
    state_db_path = home / "state.db"

    db = SessionDB(db_path=state_db_path)
    try:
        session, lineage_root_session_id = session_lineage(db, session_id)
    finally:
        db.close()

    generated_at = iso_z(now_utc())
    checkpoint_id = _checkpoint_id(session_id)
    derived_state = write_derived_state(
        continuity_dir,
        session_id=session_id,
        lineage_root_session_id=lineage_root_session_id,
        cwd=cwd,
    )

    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": checkpoint_id,
        "generated_at": generated_at,
        "profile": {
            "profile_name": home.name,
            "hermes_home": str(home),
        },
        "session": {
            "active_session_id": session_id,
            "lineage_root_session_id": lineage_root_session_id,
            "parent_session_id": session.get("parent_session_id"),
            "source": session.get("source"),
            "started_at": session.get("started_at"),
            "message_count": session.get("message_count"),
            "tool_call_count": session.get("tool_call_count"),
        },
        "memory": {
            "memory_path": str(memory_path.resolve()),
            "memory_sha256": sha256_file(memory_path) if memory_path.exists() else None,
            "user_path": str(user_path.resolve()),
            "user_sha256": sha256_file(user_path) if user_path.exists() else None,
        },
        "config": {
            "config_path": str(config_path.resolve()),
            "config_sha256": sha256_file(config_path) if config_path.exists() else None,
            "selected_model": session.get("model"),
        },
        "state_db": state_db_metadata(state_db_path),
        "project_context": {
            "cwd": str(cwd),
            "files": project_context_files(cwd),
        },
        "derived_state": derived_state,
        "verification": {
            "required_checks": REQUIRED_CHECKS,
        },
    }

    manifest_path = manifests_dir / f"{checkpoint_id}.json"
    latest_path = manifests_dir / "latest.json"
    atomic_json_write(manifest_path, manifest)
    atomic_json_write(latest_path, manifest)
    anchor_info = write_anchor(
        checkpoint_id=checkpoint_id,
        manifest_path=manifest_path,
        latest_manifest_path=latest_path,
        derived_state=derived_state,
    )

    return {
        "status": "PASS",
        "checkpoint_id": checkpoint_id,
        "manifest_path": str(manifest_path.resolve()),
        "latest_manifest_path": str(latest_path.resolve()),
        "anchor_path": anchor_info["anchor_path"],
        "latest_anchor_path": anchor_info["latest_anchor_path"],
        "public_key_path": anchor_info["public_key_path"],
        "session_id": session_id,
        "lineage_root_session_id": lineage_root_session_id,
    }

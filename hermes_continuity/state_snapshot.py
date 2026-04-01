"""State snapshot helpers for Hermes continuity checkpoints."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from hermes_constants import get_hermes_home
from hermes_state import SessionDB
from utils import atomic_json_write

from .schema import iso_z, now_utc


def hermes_home() -> Path:
    return get_hermes_home().resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def session_lineage(db: SessionDB, session_id: str) -> Tuple[Dict[str, Any], str]:
    session = db.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found in state.db: {session_id}")
    cursor = session
    visited: set[str] = set()
    while cursor.get("parent_session_id") and cursor["id"] not in visited:
        visited.add(cursor["id"])
        parent_id = cursor.get("parent_session_id")
        parent = db.get_session(parent_id) if parent_id else None
        if not parent:
            raise ValueError(f"Missing lineage parent referenced by state.db: {parent_id}")
        cursor = parent
    return session, cursor["id"]


def project_context_files(cwd: Path) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for name, required in (("AGENTS.md", True), ("SOUL.md", False), ("USER.md", False)):
        path = cwd / name
        if not path.exists():
            continue
        files.append(
            {
                "kind": name,
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "required": required,
            }
        )
    return files


def state_db_metadata(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "sha256": sha256_file(path) if path.exists() else None,
        "fts_available": False,
    }
    if not path.exists():
        return info
    try:
        with sqlite3.connect(str(path)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
            ).fetchone()
        info["fts_available"] = bool(row)
    except Exception:
        info["fts_available"] = False
    return info


def write_derived_state(
    continuity_dir: Path,
    *,
    session_id: str,
    lineage_root_session_id: str,
    cwd: Path,
) -> Dict[str, str]:
    state_dir = continuity_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_json_path = state_dir / "STATE.json"
    state_md_path = state_dir / "STATE.md"
    payload = {
        "schema_version": "hermes-total-recall-v0-derived-state",
        "generated_at": iso_z(now_utc()),
        "active_session_id": session_id,
        "lineage_root_session_id": lineage_root_session_id,
        "cwd": str(cwd.resolve()),
    }
    atomic_json_write(state_json_path, payload)
    state_md_path.write_text(
        "\n".join(
            [
                "# Hermes Total Recall Derived State",
                "",
                f"- generated_at: {payload['generated_at']}",
                f"- active_session_id: {session_id}",
                f"- lineage_root_session_id: {lineage_root_session_id}",
                f"- cwd: {cwd.resolve()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "state_json_path": str(state_json_path.resolve()),
        "state_md_path": str(state_md_path.resolve()),
    }

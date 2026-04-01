"""Verification for Hermes Total Recall continuity artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hermes_constants import get_hermes_home
from hermes_state import SessionDB

from .anchors import verify_anchor_for_checkpoint
from .incidents import create_or_update_fail_closed_incident
from .reporting import write_json_report
from .schema import REQUIRED_CHECKS, REQUIRED_MANIFEST_KEYS, SCHEMA_VERSION, iso_z, now_utc
from .state_snapshot import load_json, sha256_file


def manifest_load_failure_report(manifest_path: Path, error: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(now_utc()),
        "checkpoint_path": str(manifest_path.resolve()),
        "checkpoint_id": None,
        "status": "FAIL",
        "required_checks": REQUIRED_CHECKS,
        "warnings": [],
        "errors": [error],
        "manifest": None,
    }


def load_latest_manifest(hermes_home: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Path], List[str]]:
    errors: List[str] = []
    manifest_path = hermes_home / "continuity" / "manifests" / "latest.json"
    if not manifest_path.exists():
        errors.append(f"Missing latest checkpoint manifest: {manifest_path}")
        return None, manifest_path, errors
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        errors.append(f"Unable to read latest checkpoint manifest: {exc}")
        return None, manifest_path, errors
    if not isinstance(manifest, dict):
        errors.append("Latest checkpoint manifest is not a JSON object")
        return None, manifest_path, errors
    return manifest, manifest_path, errors


def compare_declared_file(path_str: str, digest: Optional[str], label: str, required: bool = True) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []
    path = Path(path_str)
    if not path.exists():
        message = f"Missing {label}: {path}"
        if required:
            errors.append(message)
        else:
            warnings.append(message)
        return warnings, errors
    if digest:
        actual = sha256_file(path)
        if actual != digest:
            errors.append(f"Digest mismatch for {label}: {path}")
    return warnings, errors


def verify_state_db(manifest: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []
    state_db = manifest.get("state_db") or {}
    path = Path(state_db.get("path", ""))
    active_session_id = (manifest.get("session") or {}).get("active_session_id")
    lineage_root_session_id = (manifest.get("session") or {}).get("lineage_root_session_id")

    if not path.exists():
        errors.append(f"Missing state.db: {path}")
        return warnings, errors

    try:
        db = SessionDB(db_path=path)
    except Exception as exc:
        errors.append(f"Unable to open state.db: {exc}")
        return warnings, errors

    try:
        if active_session_id:
            session = db.get_session(active_session_id)
            if not session:
                errors.append(f"Active session not found in state.db: {active_session_id}")
            else:
                if int(session.get("message_count") or 0) == 0:
                    warnings.append(f"Active session has no persisted messages: {active_session_id}")
                lineage_cursor = session
                visited = set()
                while lineage_cursor and lineage_cursor.get("parent_session_id") and lineage_cursor["id"] not in visited:
                    visited.add(lineage_cursor["id"])
                    parent_id = lineage_cursor.get("parent_session_id")
                    parent = db.get_session(parent_id) if parent_id else None
                    if not parent:
                        errors.append(f"Missing lineage parent referenced by state.db: {parent_id}")
                        break
                    lineage_cursor = parent
                if lineage_root_session_id and lineage_cursor and lineage_cursor.get("id") != lineage_root_session_id:
                    errors.append(
                        "Lineage root mismatch: manifest root "
                        f"{lineage_root_session_id} != state.db root {lineage_cursor.get('id')}"
                    )
        else:
            warnings.append("No active_session_id declared in manifest")
    finally:
        db.close()

    if bool(state_db.get("fts_available")):
        try:
            with sqlite3.connect(str(path)) as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
                ).fetchone()
            if not row:
                errors.append("Expected FTS table messages_fts is missing from state.db")
        except Exception as exc:
            errors.append(f"Unable to inspect FTS availability in state.db: {exc}")

    return warnings, errors


def verify_project_context(manifest: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []
    files = (manifest.get("project_context") or {}).get("files") or []
    required_seen = False
    for item in files:
        path = Path(item.get("path", ""))
        kind = item.get("kind") or path.name
        required = bool(item.get("required"))
        if kind == "AGENTS.md":
            required_seen = True
        if not path.exists():
            msg = f"Missing project context file: {path}"
            if required:
                errors.append(msg)
            else:
                warnings.append(msg)
            continue
        expected = item.get("sha256")
        if expected and sha256_file(path) != expected:
            errors.append(f"Digest mismatch for project context file: {path}")
    if not required_seen:
        warnings.append("No required AGENTS.md reference declared in manifest")
    return warnings, errors


def verify_manifest(manifest: Dict[str, Any], manifest_path: Path) -> Dict[str, Any]:
    warnings: List[str] = []
    errors: List[str] = []
    anchor_summary: Dict[str, Any] | None = None

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"Unexpected schema_version: {manifest.get('schema_version')} (expected {SCHEMA_VERSION})"
        )

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append(f"Missing required manifest key: {key}")

    profile = manifest.get("profile") or {}
    hermes_home = get_hermes_home().resolve()
    manifest_home = Path(profile.get("hermes_home", "")) if profile.get("hermes_home") else None
    if manifest_home and manifest_home.resolve() != hermes_home:
        warnings.append(
            f"Manifest hermes_home {manifest_home.resolve()} differs from active HERMES_HOME {hermes_home}"
        )

    memory = manifest.get("memory") or {}
    config = manifest.get("config") or {}
    state_db = manifest.get("state_db") or {}

    for label, key in (("memory", "memory_path"), ("user", "user_path")):
        item_path = memory.get(key)
        if item_path:
            w, e = compare_declared_file(item_path, memory.get(f"{label}_sha256"), f"{label} file")
            warnings.extend(w)
            errors.extend(e)
        else:
            errors.append(f"Missing declared path for {label} file")

    if config.get("config_path"):
        w, e = compare_declared_file(config["config_path"], config.get("config_sha256"), "config file")
        warnings.extend(w)
        errors.extend(e)
    else:
        errors.append("Missing declared config_path")

    w, e = verify_state_db(manifest)
    warnings.extend(w)
    errors.extend(e)

    derived_state = manifest.get("derived_state") or {}
    state_json_path = derived_state.get("state_json_path")
    state_md_path = derived_state.get("state_md_path")
    if state_json_path:
        state_json = Path(state_json_path)
        if not state_json.exists():
            warnings.append(f"Missing derived state file: {state_json}")
        else:
            try:
                derived = load_json(state_json)
                if derived.get("active_session_id") != (manifest.get("session") or {}).get("active_session_id"):
                    errors.append("Derived STATE.json active_session_id does not match manifest")
                if derived.get("lineage_root_session_id") != (manifest.get("session") or {}).get("lineage_root_session_id"):
                    errors.append("Derived STATE.json lineage_root_session_id does not match manifest")
            except Exception as exc:
                errors.append(f"Unable to parse derived STATE.json: {exc}")
    if state_md_path and not Path(state_md_path).exists():
        warnings.append(f"Missing derived state file: {state_md_path}")

    w, e = verify_project_context(manifest)
    warnings.extend(w)
    errors.extend(e)

    state_db_exists = bool(state_db.get("exists"))
    if not state_db_exists:
        errors.append("Manifest state_db.exists is false")

    checkpoint_id = manifest.get("checkpoint_id")
    if checkpoint_id:
        canonical_manifest_path = manifest_path.parent / f"{checkpoint_id}.json"
        latest_manifest_path = manifest_path.parent / "latest.json"
        anchor_warnings, anchor_errors, anchor = verify_anchor_for_checkpoint(
            checkpoint_id=checkpoint_id,
            manifest_path=canonical_manifest_path,
            latest_manifest_path=latest_manifest_path,
        )
        warnings.extend(anchor_warnings)
        errors.extend(anchor_errors)
        if anchor:
            anchor_summary = {
                "checkpoint_id": anchor.get("checkpoint_id"),
                "public_key_path": anchor.get("public_key_path"),
                "entry_count": len(anchor.get("entries") or []),
                "signature_algorithm": anchor.get("signature_algorithm"),
            }
    else:
        errors.append("Missing checkpoint_id required for continuity anchor verification")

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(now_utc()),
        "checkpoint_path": str(manifest_path.resolve()),
        "checkpoint_id": manifest.get("checkpoint_id"),
        "status": status,
        "required_checks": REQUIRED_CHECKS,
        "warnings": warnings,
        "errors": errors,
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "profile_name": profile.get("profile_name"),
            "hermes_home": profile.get("hermes_home"),
            "active_session_id": (manifest.get("session") or {}).get("active_session_id"),
        },
        "anchor": anchor_summary,
    }


def write_verify_report(hermes_home: Path, report: Dict[str, Any]) -> Tuple[str, str]:
    return write_json_report(hermes_home / "continuity" / "reports", "verify", report)


def verify_latest_checkpoint() -> Dict[str, Any]:
    hermes_home = get_hermes_home().resolve()
    manifest, manifest_path, load_errors = load_latest_manifest(hermes_home)
    if not manifest:
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": iso_z(now_utc()),
            "checkpoint_path": str(manifest_path.resolve()) if manifest_path else None,
            "checkpoint_id": None,
            "status": "FAIL",
            "required_checks": REQUIRED_CHECKS,
            "warnings": [],
            "errors": load_errors,
            "manifest": None,
        }
        report_path, latest_path = write_verify_report(hermes_home, report)
        create_or_update_fail_closed_incident(
            transition_type="verification",
            summary="Continuity verification failed before a protected transition could proceed.",
            exact_blocker=(load_errors or ["Unknown verification load failure"])[0],
            failure_planes=["integrity"],
            commands_run=["python scripts/continuity/hermes_verify.py"],
            artifacts_inspected=[str(Path(report_path).resolve())],
            event="verification_failed",
        )
        return {
            "status": "FAIL",
            "report_path": report_path,
            "latest_report_path": latest_path,
            "manifest_path": str(manifest_path.resolve()) if manifest_path else None,
            "warnings": [],
            "errors": load_errors,
        }

    report = verify_manifest(manifest, manifest_path)
    report_path, latest_path = write_verify_report(hermes_home, report)
    if report["status"] == "FAIL":
        create_or_update_fail_closed_incident(
            transition_type="verification",
            summary="Continuity verification failed before a protected transition could proceed.",
            exact_blocker=(report.get("errors") or ["Unknown verification failure"])[0],
            failure_planes=["integrity"],
            commands_run=["python scripts/continuity/hermes_verify.py"],
            artifacts_inspected=[str(Path(report_path).resolve()), str(manifest_path.resolve())],
            event="verification_failed",
        )
    return {
        "status": report["status"],
        "report_path": report_path,
        "latest_report_path": latest_path,
        "manifest_path": str(manifest_path.resolve()),
        "warnings": report["warnings"],
        "errors": report["errors"],
    }


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify Hermes Total Recall v0 continuity artifacts.")
    parser.add_argument(
        "--manifest-path",
        default=None,
        help="Optional explicit checkpoint manifest path; defaults to continuity/manifests/latest.json.",
    )
    args = parser.parse_args(argv)

    hermes_home = get_hermes_home().resolve()
    if args.manifest_path:
        manifest_path = Path(args.manifest_path)
        if not manifest_path.exists():
            report = manifest_load_failure_report(
                manifest_path,
                f"Missing checkpoint manifest: {manifest_path}",
            )
        else:
            try:
                manifest = load_json(manifest_path)
            except Exception as exc:
                report = manifest_load_failure_report(
                    manifest_path,
                    f"Unable to read checkpoint manifest: {exc}",
                )
            else:
                report = verify_manifest(manifest, manifest_path)
        report_path, latest_path = write_verify_report(hermes_home, report)
        payload = {
            "status": report["status"],
            "report_path": report_path,
            "latest_report_path": latest_path,
            "manifest_path": str(manifest_path.resolve()),
            "warnings": report["warnings"],
            "errors": report["errors"],
        }
        print(json.dumps(payload, indent=2))
        return 0 if report["status"] in {"PASS", "WARN"} else 1

    result = verify_latest_checkpoint()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"PASS", "WARN"} else 1

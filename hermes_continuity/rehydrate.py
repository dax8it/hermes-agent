"""Rehydrate Hermes continuity from validated artifacts only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hermes_constants import get_hermes_home
from hermes_state import SessionDB
from utils import atomic_json_write

from .incidents import create_or_update_fail_closed_incident
from .schema import REQUIRED_MANIFEST_KEYS, SCHEMA_VERSION, iso_z, now_utc, slug_ts
from .state_snapshot import load_json, sha256_file
from .verify import verify_latest_checkpoint


def ensure_latest_verification() -> Tuple[Dict[str, Any], Path]:
    verification_result = verify_latest_checkpoint()
    report_path = Path(verification_result["report_path"])
    report = load_json(report_path)
    return report, report_path


def declared_artifacts(manifest: Dict[str, Any], manifest_path: Path) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = [
        {
            "kind": "checkpoint_manifest",
            "label": "latest checkpoint manifest",
            "path": str(manifest_path.resolve()),
            "sha256": sha256_file(manifest_path),
            "authority": True,
        }
    ]

    memory = manifest.get("memory") or {}
    config = manifest.get("config") or {}
    state_db = manifest.get("state_db") or {}
    project_context = manifest.get("project_context") or {}
    derived_state = manifest.get("derived_state") or {}

    for kind, label, key, digest_key in (
        ("memory_file", "MEMORY.md", "memory_path", "memory_sha256"),
        ("user_file", "USER.md", "user_path", "user_sha256"),
        ("config_file", "config.yaml", "config_path", "config_sha256"),
        ("state_db", "state.db", "path", "sha256"),
    ):
        section = memory if kind in {"memory_file", "user_file"} else config if kind == "config_file" else state_db
        path = section.get(key)
        digest = section.get(digest_key)
        if path:
            artifacts.append(
                {
                    "kind": kind,
                    "label": label,
                    "path": path,
                    "sha256": digest,
                    "authority": True,
                }
            )

    for item in project_context.get("files") or []:
        artifacts.append(
            {
                "kind": "project_context_file",
                "label": item.get("kind") or Path(item.get("path", "")).name,
                "path": item.get("path"),
                "sha256": item.get("sha256"),
                "required": bool(item.get("required")),
                "authority": True,
            }
        )

    for kind, path_key in (("derived_state_json", "state_json_path"), ("derived_state_md", "state_md_path")):
        path = derived_state.get(path_key)
        if path:
            artifacts.append(
                {
                    "kind": kind,
                    "label": Path(path).name,
                    "path": path,
                    "authority": True,
                }
            )

    return artifacts


def compare_path_digest(path_str: str, digest: Optional[str], label: str) -> Optional[str]:
    path = Path(path_str)
    if not path.exists():
        return f"Missing declared {label}: {path}"
    if digest and sha256_file(path) != digest:
        return f"Digest mismatch for {label}: {path}"
    return None


def create_or_validate_target_session(
    hermes_home: Path,
    manifest: Dict[str, Any],
    target_session_id: Optional[str],
) -> Tuple[Optional[str], bool, List[Dict[str, Any]], List[str]]:
    accepted: List[Dict[str, Any]] = []
    rejected: List[str] = []
    created = False
    session_info = manifest.get("session") or {}
    source_session_id = session_info.get("active_session_id")
    lineage_root_session_id = session_info.get("lineage_root_session_id")

    if not target_session_id:
        return source_session_id, created, accepted, rejected
    if not source_session_id or not lineage_root_session_id:
        rejected.append("Cannot materialize a target session without a source_session_id and lineage_root_session_id")
        return None, False, accepted, rejected

    state_db_path = hermes_home / "state.db"
    db = SessionDB(db_path=state_db_path)
    try:
        existing = db.get_session(target_session_id)
        if existing:
            if existing.get("parent_session_id") != source_session_id:
                rejected.append(
                    f"Target session already exists with incompatible parent_session_id: {existing.get('parent_session_id')}"
                )
                return None, False, accepted, rejected
            accepted.append(
                {
                    "kind": "target_session",
                    "label": target_session_id,
                    "session_id": target_session_id,
                    "created": False,
                    "authority": True,
                }
            )
            return target_session_id, False, accepted, rejected

        db.create_session(
            target_session_id,
            source="rehydrate",
            model=(manifest.get("config") or {}).get("selected_model"),
            parent_session_id=source_session_id,
        )
        created = True
        accepted.append(
            {
                "kind": "target_session",
                "label": target_session_id,
                "session_id": target_session_id,
                "created": True,
                "parent_session_id": source_session_id,
                "authority": True,
            }
        )
        return target_session_id, created, accepted, rejected
    finally:
        db.close()


def rehydrate_latest_checkpoint(target_session_id: Optional[str] = None) -> Dict[str, Any]:
    hermes_home = get_hermes_home().resolve()
    verify_report, verify_report_path = ensure_latest_verification()
    manifest_path = Path(verify_report["checkpoint_path"])
    manifest = load_json(manifest_path) if manifest_path.exists() else {}

    errors: List[str] = []
    warnings: List[str] = list(verify_report.get("warnings") or [])
    rejected: List[Dict[str, Any]] = []

    if verify_report.get("status") == "FAIL":
        errors.extend(verify_report.get("errors") or [])
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": iso_z(now_utc()),
            "rehydrate_id": None,
            "status": "FAIL",
            "warnings": warnings,
            "errors": errors,
            "source_manifest_path": str(verify_report.get("checkpoint_path") or ""),
            "verification_report_path": str(verify_report_path.resolve()),
            "manifest": None,
            "accepted_authorities": [],
            "rejected_conflicting_artifacts": rejected,
        }
        return _write_rehydrate_receipt(hermes_home, report)

    if not manifest_path.exists():
        errors.append(f"Missing checkpoint manifest: {manifest_path}")
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": iso_z(now_utc()),
            "rehydrate_id": None,
            "status": "FAIL",
            "warnings": warnings,
            "errors": errors,
            "source_manifest_path": str(manifest_path),
            "verification_report_path": str(verify_report_path.resolve()),
            "manifest": None,
            "accepted_authorities": [],
            "rejected_conflicting_artifacts": rejected,
        }
        return _write_rehydrate_receipt(hermes_home, report)

    manifest_errors: List[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            manifest_errors.append(f"Missing required manifest key: {key}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        manifest_errors.append(
            f"Unexpected schema_version: {manifest.get('schema_version')} (expected {SCHEMA_VERSION})"
        )

    memory = manifest.get("memory") or {}
    config = manifest.get("config") or {}
    state_db = manifest.get("state_db") or {}
    project_context = manifest.get("project_context") or {}
    derived_state = manifest.get("derived_state") or {}

    for label, key in (("memory", "memory_path"), ("user", "user_path")):
        item_path = memory.get(key)
        if item_path:
            err = compare_path_digest(item_path, memory.get(f"{label}_sha256"), f"{label} file")
            if err:
                manifest_errors.append(err)
        else:
            manifest_errors.append(f"Missing declared path for {label} file")

    if config.get("config_path"):
        err = compare_path_digest(config["config_path"], config.get("config_sha256"), "config file")
        if err:
            manifest_errors.append(err)
    else:
        manifest_errors.append("Missing declared config_path")

    if state_db.get("path"):
        err = compare_path_digest(state_db["path"], state_db.get("sha256"), "state.db")
        if err:
            manifest_errors.append(err)
    else:
        manifest_errors.append("Missing declared state.db path")

    for item in project_context.get("files") or []:
        path = item.get("path")
        if not path:
            manifest_errors.append("Missing declared project context file path")
            continue
        declared = Path(path)
        if not declared.exists():
            if item.get("required"):
                manifest_errors.append(f"Missing required project context file: {declared}")
            else:
                warnings.append(f"Missing project context file: {declared}")
            continue
        expected = item.get("sha256")
        if expected and sha256_file(declared) != expected:
            manifest_errors.append(f"Digest mismatch for project context file: {declared}")

    for path_key in ("state_json_path", "state_md_path"):
        derived_path = derived_state.get(path_key)
        if derived_path and not Path(derived_path).exists():
            warnings.append(f"Missing derived state file: {derived_path}")

    if manifest_errors:
        errors.extend(manifest_errors)
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": iso_z(now_utc()),
            "rehydrate_id": None,
            "status": "FAIL",
            "warnings": warnings,
            "errors": errors,
            "source_manifest_path": str(manifest_path.resolve()),
            "verification_report_path": str(verify_report_path.resolve()),
            "manifest": {
                "schema_version": manifest.get("schema_version"),
                "checkpoint_id": manifest.get("checkpoint_id"),
                "profile_name": (manifest.get("profile") or {}).get("profile_name"),
                "hermes_home": (manifest.get("profile") or {}).get("hermes_home"),
            },
            "accepted_authorities": declared_artifacts(manifest, manifest_path),
            "rejected_conflicting_artifacts": rejected,
            "resulting_session_id": None,
            "resulting_session_created": False,
        }
        return _write_rehydrate_receipt(hermes_home, report)

    target_resolved, created, target_acceptances, target_rejections = create_or_validate_target_session(
        hermes_home,
        manifest,
        target_session_id,
    )
    rejected.extend({"kind": "target_session", "reason": reason} for reason in target_rejections)

    if target_rejections:
        errors.extend(target_rejections)
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": iso_z(now_utc()),
            "rehydrate_id": None,
            "status": "FAIL",
            "warnings": warnings,
            "errors": errors,
            "source_manifest_path": str(manifest_path.resolve()),
            "verification_report_path": str(verify_report_path.resolve()),
            "manifest": {
                "schema_version": manifest.get("schema_version"),
                "checkpoint_id": manifest.get("checkpoint_id"),
                "profile_name": (manifest.get("profile") or {}).get("profile_name"),
                "hermes_home": (manifest.get("profile") or {}).get("hermes_home"),
            },
            "accepted_authorities": declared_artifacts(manifest, manifest_path) + target_acceptances,
            "rejected_conflicting_artifacts": rejected,
            "resulting_session_id": target_resolved,
            "resulting_session_created": created,
        }
        return _write_rehydrate_receipt(hermes_home, report)

    accepted = declared_artifacts(manifest, manifest_path) + target_acceptances
    rehydrate_id = f"{slug_ts(now_utc())}_{(target_resolved or 'no-session')}"
    final_status = "WARN" if warnings else "PASS"
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(now_utc()),
        "rehydrate_id": rehydrate_id,
        "status": final_status,
        "warnings": warnings,
        "errors": [],
        "source_manifest_path": str(manifest_path.resolve()),
        "verification_report_path": str(verify_report_path.resolve()),
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "checkpoint_id": manifest.get("checkpoint_id"),
            "profile_name": (manifest.get("profile") or {}).get("profile_name"),
            "hermes_home": (manifest.get("profile") or {}).get("hermes_home"),
            "active_session_id": (manifest.get("session") or {}).get("active_session_id"),
            "lineage_root_session_id": (manifest.get("session") or {}).get("lineage_root_session_id"),
        },
        "accepted_authorities": accepted,
        "rejected_conflicting_artifacts": rejected,
        "source_session_id": (manifest.get("session") or {}).get("active_session_id"),
        "resulting_session_id": target_resolved,
        "resulting_session_created": created,
    }
    return _write_rehydrate_receipt(hermes_home, report, rollback_session_id=target_resolved if created else None)


def _write_rehydrate_receipt(
    hermes_home: Path,
    report: Dict[str, Any],
    rollback_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    rehydrate_dir.mkdir(parents=True, exist_ok=True)
    ts = slug_ts(now_utc())
    report_path = rehydrate_dir / f"rehydrate-{ts}.json"
    latest_path = rehydrate_dir / "rehydrate-latest.json"
    try:
        atomic_json_write(report_path, report)
        atomic_json_write(latest_path, report)
    except Exception:
        if rollback_session_id:
            try:
                db = SessionDB(db_path=hermes_home / "state.db")
                try:
                    db.delete_session(rollback_session_id)
                finally:
                    db.close()
            except Exception:
                pass
        raise
    result = {
        "status": report["status"],
        "rehydrate_id": report.get("rehydrate_id"),
        "report_path": str(report_path.resolve()),
        "latest_report_path": str(latest_path.resolve()),
        "source_manifest_path": report.get("source_manifest_path"),
        "verification_report_path": report.get("verification_report_path"),
        "warnings": report.get("warnings") or [],
        "errors": report.get("errors") or [],
        "resulting_session_id": report.get("resulting_session_id"),
        "resulting_session_created": report.get("resulting_session_created", False),
    }
    if report.get("status") == "FAIL":
        create_or_update_fail_closed_incident(
            transition_type="rehydrate",
            summary="Continuity rehydrate failed closed before state restoration could continue.",
            exact_blocker=(report.get("errors") or ["Unknown rehydrate failure"])[0],
            failure_planes=["rehydrate"],
            commands_run=["python scripts/continuity/hermes_rehydrate.py"],
            artifacts_inspected=[str(report_path.resolve())],
            event="rehydrate_failed",
        )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Rehydrate Hermes Total Recall v0 from validated continuity artifacts.")
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional target session ID to materialize in state.db for the rehydrated continuation.",
    )
    args = parser.parse_args(argv)

    result = rehydrate_latest_checkpoint(target_session_id=args.session_id)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"PASS", "WARN"} else 1

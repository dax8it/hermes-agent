"""External memory inbox -> quarantine -> promote flow for continuity-safe imports."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from utils import atomic_json_write

from .reporting import write_json_report
from .schema import iso_z, now_utc, slug_ts
from .state_snapshot import hermes_home

EXTERNAL_MEMORY_SCHEMA = "hermes-external-memory-v0"


def _external_memory_root(home: Optional[Path] = None) -> Path:
    return (home or hermes_home()) / "continuity" / "external-memory"


def _paths(home: Optional[Path] = None) -> Dict[str, Path]:
    root = _external_memory_root(home)
    return {
        "root": root,
        "inbox": root / "inbox",
        "quarantine": root / "quarantine",
        "pending": root / "pending",
        "promoted": root / "promoted",
        "rejected": root / "rejected",
    }


def _canonical_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate_id(normalized_core: Dict[str, Any]) -> Tuple[str, str]:
    fingerprint = hashlib.sha256(_canonical_json_bytes(normalized_core)).hexdigest()
    return f"cand_{slug_ts(now_utc())}_{fingerprint[:12]}", fingerprint


def _ensure_dirs(home: Optional[Path] = None) -> Dict[str, Path]:
    paths = _paths(home)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _normalize_payload(payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    source_kind = str(payload.get("source_kind") or "").strip()
    source_session_id = str(payload.get("source_session_id") or "").strip()
    target = str(payload.get("target") or "").strip()
    content = str(payload.get("content") or "").strip()

    if not source_kind:
        errors.append("Missing required field: source_kind")
    if not source_session_id:
        errors.append("Missing required field: source_session_id")
    if target not in {"memory", "user"}:
        errors.append("Invalid target; expected 'memory' or 'user'")
    if not content:
        errors.append("Missing required field: content")

    evidence = payload.get("evidence") or []
    if not isinstance(evidence, list):
        errors.append("Invalid evidence; expected a list")
        evidence = []

    normalized_core = {
        "schema_version": EXTERNAL_MEMORY_SCHEMA,
        "action": "add",
        "target": target,
        "content": content,
        "content_sha256": _sha256_text(content) if content else None,
        "provenance": {
            "source_kind": source_kind,
            "source_session_id": source_session_id,
            "source_agent": payload.get("source_agent"),
            "source_profile": payload.get("source_profile"),
            "source_workspace": payload.get("source_workspace"),
            "source_model": payload.get("source_model"),
        },
        "evidence": evidence,
    }
    if errors:
        return None, errors

    candidate_id, fingerprint = _candidate_id(normalized_core)
    candidate = {
        **normalized_core,
        "candidate_id": candidate_id,
        "candidate_sha256": fingerprint,
        "received_at": iso_z(now_utc()),
        "state": "QUARANTINED",
        "review": None,
    }
    return candidate, errors


def _continuity_external_memory_config(home: Optional[Path] = None) -> Dict[str, Any]:
    home = home or hermes_home()
    config_path = home / "config.yaml"
    continuity: Dict[str, Any] = {}
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            continuity = raw.get("continuity") or {}
        except Exception:
            continuity = {}
    return {
        "external_memory_enabled": bool(continuity.get("external_memory_enabled", False)),
    }


def _candidate_core(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": candidate.get("schema_version"),
        "action": candidate.get("action"),
        "target": candidate.get("target"),
        "content": candidate.get("content"),
        "content_sha256": candidate.get("content_sha256"),
        "provenance": candidate.get("provenance"),
        "evidence": candidate.get("evidence") or [],
    }


def _validate_candidate_integrity(candidate: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    content = str(candidate.get("content") or "")
    declared_content_sha = candidate.get("content_sha256")
    if _sha256_text(content) != declared_content_sha:
        errors.append("External memory candidate content_sha256 mismatch")
    candidate_sha = candidate.get("candidate_sha256")
    recomputed = hashlib.sha256(_canonical_json_bytes(_candidate_core(candidate))).hexdigest()
    if candidate_sha != recomputed:
        errors.append("External memory candidate candidate_sha256 mismatch")
    if candidate.get("state") not in {"QUARANTINED", "PROMOTION_PENDING"}:
        errors.append(f"External memory candidate not promotable from state {candidate.get('state')}")
    return errors


@contextmanager
def _memory_store_context():
    from tools import memory_tool as memory_tool_module

    old_memory_dir = memory_tool_module.MEMORY_DIR
    try:
        memory_tool_module.MEMORY_DIR = hermes_home() / "memories"
        store = memory_tool_module.MemoryStore()
        store.load_from_disk()
        yield store
    finally:
        memory_tool_module.MEMORY_DIR = old_memory_dir


def ingest_external_memory_candidate(payload: Dict[str, Any]) -> Dict[str, Any]:
    home = hermes_home()
    paths = _ensure_dirs(home)
    cfg = _continuity_external_memory_config(home)
    if not cfg["external_memory_enabled"]:
        receipt = {
            "generated_at": iso_z(now_utc()),
            "kind": "external_memory_ingest",
            "status": "REJECTED",
            "candidate_id": None,
            "errors": ["External memory inbox is disabled by continuity.external_memory_enabled"],
            "raw_payload": payload,
        }
        receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-ingest", receipt)
        return {
            "status": "REJECTED",
            "errors": receipt["errors"],
            "receipt_path": receipt_path,
            "latest_receipt_path": latest_path,
        }
    candidate, errors = _normalize_payload(payload)
    if errors:
        receipt = {
            "generated_at": iso_z(now_utc()),
            "kind": "external_memory_ingest",
            "status": "REJECTED",
            "candidate_id": None,
            "errors": errors,
            "raw_payload": payload,
        }
        receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-ingest", receipt)
        return {
            "status": "REJECTED",
            "errors": errors,
            "receipt_path": receipt_path,
            "latest_receipt_path": latest_path,
        }

    inbox_path = paths["inbox"] / f"{candidate['candidate_id']}.json"
    quarantine_path = paths["quarantine"] / f"{candidate['candidate_id']}.json"
    atomic_json_write(inbox_path, {
        "candidate_id": candidate["candidate_id"],
        "received_at": candidate["received_at"],
        "raw_payload": payload,
    })
    atomic_json_write(quarantine_path, candidate)

    receipt = {
        "generated_at": iso_z(now_utc()),
        "kind": "external_memory_ingest",
        "status": "QUARANTINED",
        "candidate_id": candidate["candidate_id"],
        "target": candidate["target"],
        "candidate_sha256": candidate["candidate_sha256"],
        "quarantine_path": str(quarantine_path.resolve()),
        "inbox_path": str(inbox_path.resolve()),
    }
    receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-ingest", receipt)
    return {
        "status": "QUARANTINED",
        "candidate_id": candidate["candidate_id"],
        "inbox_path": str(inbox_path.resolve()),
        "quarantine_path": str(quarantine_path.resolve()),
        "receipt_path": receipt_path,
        "latest_receipt_path": latest_path,
    }


def _candidate_path_for_state(candidate_id: str, state: str, home: Optional[Path] = None) -> Path:
    paths = _paths(home)
    state_upper = state.upper()
    if state_upper == "QUARANTINED":
        return paths["quarantine"] / f"{candidate_id}.json"
    if state_upper in {"PENDING", "PROMOTION_PENDING"}:
        return paths["pending"] / f"{candidate_id}.json"
    if state_upper == "PROMOTED":
        return paths["promoted"] / f"{candidate_id}.json"
    if state_upper == "REJECTED":
        return paths["rejected"] / f"{candidate_id}.json"
    raise ValueError(f"Unsupported external memory state: {state}")


def _safe_load_candidate(candidate_path: Path) -> Dict[str, Any]:
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def _load_quarantined_candidate(candidate_id: str) -> Tuple[Path, Dict[str, Any]]:
    home = hermes_home()
    candidate_path = _candidate_path_for_state(candidate_id, "QUARANTINED", home)
    if not candidate_path.exists():
        raise FileNotFoundError(f"External memory candidate not found in quarantine: {candidate_id}")
    candidate = _safe_load_candidate(candidate_path)
    return candidate_path, candidate


def _load_promotable_candidate(candidate_id: str) -> Tuple[Path, Dict[str, Any], str]:
    home = hermes_home()
    pending_path = _candidate_path_for_state(candidate_id, "PENDING", home)
    if pending_path.exists():
        return pending_path, _safe_load_candidate(pending_path), "PENDING"
    quarantine_path = _candidate_path_for_state(candidate_id, "QUARANTINED", home)
    if quarantine_path.exists():
        return quarantine_path, _safe_load_candidate(quarantine_path), "QUARANTINED"
    raise FileNotFoundError(f"External memory candidate not found in quarantine/pending: {candidate_id}")


def list_external_memory_candidates(*, state: str = "QUARANTINED") -> Dict[str, Any]:
    home = hermes_home()
    paths = _ensure_dirs(home)
    state_upper = state.upper()
    if state_upper == "QUARANTINED":
        base = paths["quarantine"]
    elif state_upper in {"PENDING", "PROMOTION_PENDING"}:
        base = paths["pending"]
    elif state_upper == "PROMOTED":
        base = paths["promoted"]
    elif state_upper == "REJECTED":
        base = paths["rejected"]
    else:
        return {
            "status": "ERROR",
            "errors": [f"Unsupported external memory state: {state}"],
            "candidates": [],
        }

    candidates: List[Dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            candidate = _safe_load_candidate(path)
        except Exception as exc:
            candidates.append({
                "candidate_id": path.stem,
                "state": state_upper,
                "path": str(path.resolve()),
                "error": f"Unable to read candidate: {exc}",
            })
            continue
        candidates.append(
            {
                "candidate_id": candidate.get("candidate_id") or path.stem,
                "state": candidate.get("state") or state_upper,
                "target": candidate.get("target"),
                "source_kind": (candidate.get("provenance") or {}).get("source_kind"),
                "source_agent": (candidate.get("provenance") or {}).get("source_agent"),
                "received_at": candidate.get("received_at"),
                "path": str(path.resolve()),
                "content_preview": str(candidate.get("content") or "")[:120],
            }
        )
    return {
        "status": "OK",
        "state": state_upper,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def get_external_memory_candidate(candidate_id: str) -> Dict[str, Any]:
    home = hermes_home()
    for state in ("QUARANTINED", "PENDING", "PROMOTED", "REJECTED"):
        path = _candidate_path_for_state(candidate_id, state, home)
        if not path.exists():
            continue
        try:
            candidate = _safe_load_candidate(path)
        except Exception as exc:
            return {
                "status": "ERROR",
                "candidate_id": candidate_id,
                "state": state,
                "path": str(path.resolve()),
                "errors": [f"Unable to read candidate: {exc}"],
            }
        return {
            "status": "OK",
            "candidate_id": candidate_id,
            "state": candidate.get("state") or state,
            "path": str(path.resolve()),
            "candidate": candidate,
        }
    return {
        "status": "NOT_FOUND",
        "candidate_id": candidate_id,
        "errors": [f"External memory candidate not found: {candidate_id}"],
    }


def promote_external_memory_candidate(candidate_id: str, *, reviewer: str) -> Dict[str, Any]:
    home = hermes_home()
    paths = _ensure_dirs(home)
    candidate_path, candidate, loaded_state = _load_promotable_candidate(candidate_id)
    integrity_errors = _validate_candidate_integrity(candidate)
    if integrity_errors:
        receipt = {
            "generated_at": iso_z(now_utc()),
            "kind": "external_memory_promotion",
            "status": "FAILED",
            "candidate_id": candidate_id,
            "reviewer": reviewer,
            "target": candidate.get("target"),
            "errors": integrity_errors,
        }
        receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-promotion", receipt)
        return {
            "status": "FAILED",
            "candidate_id": candidate_id,
            "errors": integrity_errors,
            "promotion_receipt_path": receipt_path,
            "latest_promotion_receipt_path": latest_path,
            "candidate_path": str(candidate_path.resolve()),
        }

    pending_path = _candidate_path_for_state(candidate_id, "PENDING", home)
    if loaded_state == "QUARANTINED":
        candidate["state"] = "PROMOTION_PENDING"
        candidate["review"] = {
            "reviewer": reviewer,
            "decision": "promote",
            "decided_at": iso_z(now_utc()),
        }
        candidate["promotion"] = {
            "phase": "pre_memory_write",
            "memory_write_completed": False,
        }
        atomic_json_write(pending_path, candidate)
        candidate_path.unlink()
        candidate_path = pending_path
    else:
        candidate.setdefault("review", {
            "reviewer": reviewer,
            "decision": "promote",
            "decided_at": iso_z(now_utc()),
        })
        candidate.setdefault("promotion", {
            "phase": "pre_memory_write",
            "memory_write_completed": False,
        })

    promotion = candidate.get("promotion") or {}
    result = promotion.get("memory_result")
    if not promotion.get("memory_write_completed"):
        with _memory_store_context() as store:
            result = store.add(candidate["target"], candidate["content"])
        if not result.get("success"):
            receipt = {
                "generated_at": iso_z(now_utc()),
                "kind": "external_memory_promotion",
                "status": "FAILED",
                "candidate_id": candidate_id,
                "reviewer": reviewer,
                "target": candidate.get("target"),
                "errors": [result.get("error", "Unknown memory promotion error")],
            }
            receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-promotion", receipt)
            return {
                "status": "FAILED",
                "candidate_id": candidate_id,
                "errors": receipt["errors"],
                "promotion_receipt_path": receipt_path,
                "latest_promotion_receipt_path": latest_path,
                "candidate_path": str(candidate_path.resolve()),
            }
        candidate["promotion"] = {
            "phase": "memory_written",
            "memory_write_completed": True,
            "memory_result": result,
        }
        atomic_json_write(candidate_path, candidate)
        pending_receipt = {
            "generated_at": iso_z(now_utc()),
            "kind": "external_memory_promotion",
            "status": "PENDING",
            "candidate_id": candidate_id,
            "reviewer": reviewer,
            "target": candidate.get("target"),
            "pending_path": str(candidate_path.resolve()),
        }
        write_json_report(home / "continuity" / "reports", "external-memory-promotion", pending_receipt)

    candidate["state"] = "PROMOTED"
    candidate["promotion"] = {
        **(candidate.get("promotion") or {}),
        "phase": "finalized",
        "memory_write_completed": True,
        "memory_result": result,
    }
    promoted_path = paths["promoted"] / f"{candidate_id}.json"
    try:
        atomic_json_write(promoted_path, candidate)
        candidate_path.unlink()
    except Exception as exc:
        recovery_receipt = {
            "generated_at": iso_z(now_utc()),
            "kind": "external_memory_promotion",
            "status": "RECOVERY_REQUIRED",
            "candidate_id": candidate_id,
            "reviewer": reviewer,
            "target": candidate.get("target"),
            "pending_path": str(candidate_path.resolve()),
            "promoted_path": str(promoted_path.resolve()),
            "errors": [str(exc)],
        }
        receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-promotion", recovery_receipt)
        return {
            "status": "RECOVERY_REQUIRED",
            "candidate_id": candidate_id,
            "errors": [str(exc)],
            "pending_path": str(candidate_path.resolve()),
            "promotion_receipt_path": receipt_path,
            "latest_promotion_receipt_path": latest_path,
        }

    receipt = {
        "generated_at": iso_z(now_utc()),
        "kind": "external_memory_promotion",
        "status": "PROMOTED",
        "candidate_id": candidate_id,
        "reviewer": reviewer,
        "target": candidate.get("target"),
        "promoted_path": str(promoted_path.resolve()),
        "memory_result": result,
        "loaded_state": loaded_state,
    }
    receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-promotion", receipt)
    return {
        "status": "PROMOTED",
        "candidate_id": candidate_id,
        "promoted_path": str(promoted_path.resolve()),
        "promotion_receipt_path": receipt_path,
        "latest_promotion_receipt_path": latest_path,
    }


def reject_external_memory_candidate(candidate_id: str, *, reviewer: str, reason: str) -> Dict[str, Any]:
    home = hermes_home()
    paths = _ensure_dirs(home)
    candidate_path, candidate = _load_quarantined_candidate(candidate_id)

    candidate["state"] = "REJECTED"
    candidate["review"] = {
        "reviewer": reviewer,
        "decision": "reject",
        "reason": reason,
        "decided_at": iso_z(now_utc()),
    }
    rejected_path = paths["rejected"] / f"{candidate_id}.json"
    atomic_json_write(rejected_path, candidate)
    candidate_path.unlink()

    receipt = {
        "generated_at": iso_z(now_utc()),
        "kind": "external_memory_review",
        "status": "REJECTED",
        "candidate_id": candidate_id,
        "reviewer": reviewer,
        "reason": reason,
        "rejected_path": str(rejected_path.resolve()),
    }
    receipt_path, latest_path = write_json_report(home / "continuity" / "reports", "external-memory-review", receipt)
    return {
        "status": "REJECTED",
        "candidate_id": candidate_id,
        "rejected_path": str(rejected_path.resolve()),
        "decision_receipt_path": receipt_path,
        "latest_decision_receipt_path": latest_path,
    }

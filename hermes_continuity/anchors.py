"""Anchor and signature support for Hermes continuity artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from utils import atomic_json_write

from .schema import iso_z, now_utc
from .state_snapshot import hermes_home, load_json, sha256_file

ANCHOR_SCHEMA_VERSION = "hermes-total-recall-anchor-v0"


def canonical_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def continuity_keys_dir(home: Path | None = None) -> Path:
    return (home or hermes_home()) / "continuity" / "keys"


def continuity_anchors_dir(home: Path | None = None) -> Path:
    return (home or hermes_home()) / "continuity" / "anchors"


def _private_key_path(home: Path | None = None) -> Path:
    return continuity_keys_dir(home) / "anchor-ed25519-private.pem"


def _public_key_path(home: Path | None = None) -> Path:
    return continuity_keys_dir(home) / "anchor-ed25519-public.pem"


def ensure_anchor_keypair(home: Path | None = None) -> Dict[str, str]:
    home = home or hermes_home()
    keys_dir = continuity_keys_dir(home)
    keys_dir.mkdir(parents=True, exist_ok=True)
    private_path = _private_key_path(home)
    public_path = _public_key_path(home)

    if not private_path.exists() or not public_path.exists():
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        private_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        public_path.write_bytes(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    return {
        "private_key_path": str(private_path.resolve()),
        "public_key_path": str(public_path.resolve()),
        "public_key_sha256": sha256_file(public_path),
    }


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_public_key(path: Path) -> Ed25519PublicKey:
    return serialization.load_pem_public_key(path.read_bytes())


def _entry(path: Path, *, role: str, required: bool = True) -> Dict[str, Any]:
    return {
        "role": role,
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "required": required,
    }


def build_anchor_payload(*, checkpoint_id: str, manifest_path: Path, latest_manifest_path: Path, derived_state: Dict[str, Any], key_info: Dict[str, str]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = [
        _entry(manifest_path, role="checkpoint_manifest"),
        _entry(latest_manifest_path, role="latest_manifest"),
    ]
    for role, key in (("derived_state_json", "state_json_path"), ("derived_state_md", "state_md_path")):
        path = derived_state.get(key)
        if path and Path(path).exists():
            entries.append(_entry(Path(path), role=role, required=False))

    return {
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "generated_at": iso_z(now_utc()),
        "checkpoint_id": checkpoint_id,
        "signature_algorithm": "ed25519",
        "public_key_path": key_info["public_key_path"],
        "public_key_sha256": key_info["public_key_sha256"],
        "entries": entries,
    }


def sign_anchor_payload(payload: Dict[str, Any], private_key_path: Path) -> str:
    private_key = _load_private_key(private_key_path)
    signed_bytes = canonical_json_bytes(payload)
    return base64.b64encode(private_key.sign(signed_bytes)).decode("ascii")


def write_anchor(*, checkpoint_id: str, manifest_path: Path, latest_manifest_path: Path, derived_state: Dict[str, Any]) -> Dict[str, str]:
    home = hermes_home()
    key_info = ensure_anchor_keypair(home)
    payload = build_anchor_payload(
        checkpoint_id=checkpoint_id,
        manifest_path=manifest_path,
        latest_manifest_path=latest_manifest_path,
        derived_state=derived_state,
        key_info=key_info,
    )
    payload["signature"] = sign_anchor_payload(payload, Path(key_info["private_key_path"]))

    anchors_dir = continuity_anchors_dir(home)
    anchors_dir.mkdir(parents=True, exist_ok=True)
    anchor_path = anchors_dir / f"{checkpoint_id}.json"
    latest_path = anchors_dir / "latest.json"
    atomic_json_write(anchor_path, payload)
    atomic_json_write(latest_path, payload)
    return {
        "anchor_path": str(anchor_path.resolve()),
        "latest_anchor_path": str(latest_path.resolve()),
        "public_key_path": key_info["public_key_path"],
    }


def verify_anchor_for_checkpoint(*, checkpoint_id: str, manifest_path: Path, latest_manifest_path: Path) -> Tuple[List[str], List[str], Dict[str, Any] | None]:
    warnings: List[str] = []
    errors: List[str] = []
    home = hermes_home()
    anchor_path = continuity_anchors_dir(home) / f"{checkpoint_id}.json"
    if not anchor_path.exists():
        errors.append(f"Missing continuity anchor for checkpoint: {anchor_path}")
        return warnings, errors, None

    try:
        anchor = load_json(anchor_path)
    except Exception as exc:
        errors.append(f"Unable to read continuity anchor: {exc}")
        return warnings, errors, None

    if anchor.get("schema_version") != ANCHOR_SCHEMA_VERSION:
        errors.append(
            f"Unexpected continuity anchor schema_version: {anchor.get('schema_version')} (expected {ANCHOR_SCHEMA_VERSION})"
        )
    if anchor.get("checkpoint_id") != checkpoint_id:
        errors.append(
            f"Continuity anchor checkpoint_id mismatch: {anchor.get('checkpoint_id')} != {checkpoint_id}"
        )

    public_key_path = Path(anchor.get("public_key_path", ""))
    if not public_key_path.exists():
        errors.append(f"Missing continuity anchor public key: {public_key_path}")
        return warnings, errors, anchor
    if anchor.get("public_key_sha256") and sha256_file(public_key_path) != anchor.get("public_key_sha256"):
        errors.append(f"Continuity anchor public key digest mismatch: {public_key_path}")

    signature_b64 = anchor.get("signature")
    if not signature_b64:
        errors.append("Missing continuity anchor signature")
    else:
        unsigned = dict(anchor)
        unsigned.pop("signature", None)
        try:
            signature = base64.b64decode(signature_b64)
            _load_public_key(public_key_path).verify(signature, canonical_json_bytes(unsigned))
        except (ValueError, InvalidSignature) as exc:
            errors.append(f"Invalid continuity anchor signature: {exc}")

    expected_paths = {
        str(manifest_path.resolve()): "checkpoint_manifest",
        str(latest_manifest_path.resolve()): "latest_manifest",
    }
    entries = anchor.get("entries") or []
    for entry in entries:
        path = Path(entry.get("path", ""))
        if not path.exists():
            message = f"Missing anchored artifact: {path}"
            if entry.get("required", True):
                errors.append(message)
            else:
                warnings.append(message)
            continue
        declared = entry.get("sha256")
        if declared and sha256_file(path) != declared:
            errors.append(f"Anchored artifact digest mismatch: {path}")

    seen_paths = {entry.get("path") for entry in entries}
    for required_path, role in expected_paths.items():
        if required_path not in seen_paths:
            errors.append(f"Continuity anchor missing required entry for {role}: {required_path}")

    return warnings, errors, anchor

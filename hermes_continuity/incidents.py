"""Continuity incident logging and postmortem artifact helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .external_memory import list_external_memory_candidates
from .schema import iso_z, now_utc, slug_ts
from .state_snapshot import hermes_home

_REPORT_TARGETS = {
    "verify": ("reports", "verify-latest.json"),
    "rehydrate": ("rehydrate", "rehydrate-latest.json"),
    "gateway-reset": ("reports", "gateway-reset-latest.json"),
    "cron-continuity": ("reports", "cron-continuity-latest.json"),
    "external-memory-ingest": ("reports", "external-memory-ingest-latest.json"),
    "external-memory-promotion": ("reports", "external-memory-promotion-latest.json"),
    "external-memory-review": ("reports", "external-memory-review-latest.json"),
}

_INCIDENT_SCHEMA = "hermes-continuity-incident-v0"


def _incident_dir(home: Path | None = None) -> Path:
    return (home or hermes_home()) / "continuity" / "incidents"


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _report_path(target: str, home: Path | None = None) -> Path:
    section, filename = _REPORT_TARGETS[target]
    return (home or hermes_home()) / "continuity" / section / filename


def continuity_status_snapshot(home: Path | None = None) -> Dict[str, Any]:
    home = home or hermes_home()
    latest_manifest = home / "continuity" / "manifests" / "latest.json"
    latest_anchor = home / "continuity" / "anchors" / "latest.json"
    manifest = _read_json(latest_manifest)
    anchor = _read_json(latest_anchor)

    reports: Dict[str, Any] = {}
    for target in _REPORT_TARGETS:
        path = _report_path(target, home)
        payload = _read_json(path)
        reports[target] = {
            "path": str(path.resolve()),
            "exists": payload is not None,
            "status": payload.get("status") if payload else None,
            "generated_at": payload.get("generated_at") if payload else None,
        }

    external_counts = {
        state: list_external_memory_candidates(state=state).get("candidate_count", 0)
        for state in ("QUARANTINED", "PENDING", "PROMOTED", "REJECTED")
    }

    return {
        "hermes_home": str(home.resolve()),
        "manifest_exists": latest_manifest.exists(),
        "anchor_exists": latest_anchor.exists(),
        "checkpoint_id": (manifest or {}).get("checkpoint_id"),
        "manifest_schema_version": (manifest or {}).get("schema_version"),
        "anchor_schema_version": (anchor or {}).get("schema_version"),
        "anchor_signature_algorithm": (anchor or {}).get("signature_algorithm"),
        "reports": reports,
        "external_memory": external_counts,
    }


def _normalize_list(values: List[str] | None) -> List[str]:
    normalized: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def render_incident_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        f"# Continuity Incident {payload['incident_id']}",
        "",
        f"- Verdict: `{payload['verdict']}`",
        f"- Transition type: `{payload['transition_type']}`",
        f"- Created at: `{payload['created_at']}`",
        f"- Protected transitions blocked: `{payload['protected_transitions_blocked']}`",
        f"- Failure planes: {', '.join(payload.get('failure_planes') or []) or '(none specified)' }",
        "",
        "## Summary",
        payload.get("summary") or "",
        "",
        "## Exact blocker",
        payload.get("exact_blocker") or "(not specified)",
        "",
        "## Exact remediation",
        payload.get("exact_remediation") or "(not specified)",
        "",
        "## Commands run",
    ]
    commands = payload.get("commands_run") or []
    if commands:
        for cmd in commands:
            lines.append(f"- `{cmd}`")
    else:
        lines.append("- (none recorded)")

    lines.extend(["", "## Artifacts inspected"])
    artifacts = payload.get("artifacts_inspected") or []
    if artifacts:
        for item in artifacts:
            lines.append(f"- `{item}`")
    else:
        lines.append("- (none recorded)")

    lines.extend(["", "## Timeline"])
    for item in payload.get("timeline") or []:
        lines.append(f"- `{item.get('at')}` — {item.get('event')}: {item.get('detail')}")
    return "\n".join(lines) + "\n"


def create_continuity_incident(
    *,
    verdict: str,
    transition_type: str,
    protected_transitions_blocked: bool,
    summary: str,
    failure_planes: List[str] | None = None,
    exact_blocker: str | None = None,
    exact_remediation: str | None = None,
    commands_run: List[str] | None = None,
    artifacts_inspected: List[str] | None = None,
) -> Dict[str, Any]:
    home = hermes_home()
    base = _incident_dir(home)
    base.mkdir(parents=True, exist_ok=True)

    incident_id = f"incident_{slug_ts(now_utc())}"
    created_at = iso_z(now_utc())
    snapshot = continuity_status_snapshot(home)
    payload = {
        "schema_version": _INCIDENT_SCHEMA,
        "incident_id": incident_id,
        "created_at": created_at,
        "verdict": str(verdict).strip(),
        "transition_type": str(transition_type).strip(),
        "protected_transitions_blocked": bool(protected_transitions_blocked),
        "failure_planes": _normalize_list(failure_planes),
        "summary": str(summary or "").strip(),
        "exact_blocker": str(exact_blocker or "").strip(),
        "exact_remediation": str(exact_remediation or "").strip(),
        "commands_run": _normalize_list(commands_run),
        "artifacts_inspected": _normalize_list(artifacts_inspected),
        "status_snapshot": snapshot,
        "timeline": [
            {
                "at": created_at,
                "event": "incident_created",
                "detail": str(summary or "").strip(),
            }
        ],
    }

    json_path = base / f"{incident_id}.json"
    md_path = base / f"{incident_id}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_incident_markdown(payload), encoding="utf-8")
    latest_json = base / "latest.json"
    latest_md = base / "latest.md"
    latest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest_md.write_text(render_incident_markdown(payload), encoding="utf-8")

    return {
        "status": "OK",
        "incident_id": incident_id,
        "json_path": str(json_path.resolve()),
        "markdown_path": str(md_path.resolve()),
        "latest_json_path": str(latest_json.resolve()),
        "latest_markdown_path": str(latest_md.resolve()),
        "payload": payload,
    }


def list_continuity_incidents() -> Dict[str, Any]:
    base = _incident_dir()
    if not base.exists():
        return {"status": "OK", "incidents": [], "incident_count": 0}
    incidents: List[Dict[str, Any]] = []
    for path in sorted(base.glob("incident_*.json"), reverse=True):
        payload = _read_json(path)
        if not payload:
            continue
        incidents.append(
            {
                "incident_id": payload.get("incident_id") or path.stem,
                "created_at": payload.get("created_at"),
                "verdict": payload.get("verdict"),
                "transition_type": payload.get("transition_type"),
                "summary": payload.get("summary"),
                "path": str(path.resolve()),
            }
        )
    return {"status": "OK", "incidents": incidents, "incident_count": len(incidents)}


def get_continuity_incident(incident_id: str) -> Dict[str, Any]:
    path = _incident_dir() / f"{incident_id}.json"
    payload = _read_json(path)
    if payload is None:
        return {
            "status": "NOT_FOUND",
            "incident_id": incident_id,
            "errors": [f"Continuity incident not found: {incident_id}"],
        }
    return {"status": "OK", "incident_id": incident_id, "payload": payload, "path": str(path.resolve())}

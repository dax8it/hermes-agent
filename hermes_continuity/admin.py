"""Continuity admin command helpers for CLI and gateway surfaces."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

from .external_memory import (
    get_external_memory_candidate,
    list_external_memory_candidates,
    promote_external_memory_candidate,
    reject_external_memory_candidate,
)
from .freshness import freshness_status, load_continuity_freshness_policy
from .incidents import (
    add_note_to_continuity_incident,
    append_continuity_incident_event,
    continuity_status_snapshot,
    create_continuity_incident,
    get_continuity_incident,
    list_continuity_incidents,
    resolve_continuity_incident,
)
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


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _report_path(target: str) -> Path:
    section, filename = _REPORT_TARGETS[target]
    return hermes_home() / "continuity" / section / filename


def _continuity_status_payload() -> Dict[str, Any]:
    return continuity_status_snapshot(hermes_home())


def _continuity_report_payload(target: str) -> Dict[str, Any]:
    if target not in _REPORT_TARGETS:
        return {
            "status": "ERROR",
            "errors": [f"Unknown continuity report target: {target}"],
            "available_targets": sorted(_REPORT_TARGETS),
        }
    path = _report_path(target)
    payload = _read_json(path)
    if payload is None:
        return {
            "status": "MISSING",
            "target": target,
            "path": str(path.resolve()),
            "errors": [f"Continuity report not found: {path}"],
        }
    freshness = freshness_status(
        payload.get("generated_at"),
        max_age_sec=load_continuity_freshness_policy()["max_report_age_sec"],
    )
    return {
        "status": "STALE" if freshness["stale"] else "OK",
        "target": target,
        "path": str(path.resolve()),
        "payload": payload,
        "freshness": freshness,
    }


def _parse_bool(text: str) -> bool:
    return str(text or "").strip().lower() in {"1", "true", "yes", "y", "blocked"}


def _format_rehydrate_report(payload: Dict[str, Any], inner: Dict[str, Any], freshness: Dict[str, Any]) -> str:
    lines = [
        f"Continuity report: {payload.get('target')} ({payload.get('status')})",
        f"Path: {payload.get('path')}",
        f"Freshness: {'STALE' if freshness.get('stale') else 'FRESH'}",
    ]

    checkpoint_freshness = inner.get("checkpoint_freshness") or {}
    if checkpoint_freshness:
        lines.append(
            f"Checkpoint freshness: {'STALE' if checkpoint_freshness.get('stale') else 'FRESH'}"
        )

    operator_summary = inner.get("operator_summary")
    if operator_summary:
        lines.append(f"Summary: {operator_summary}")

    contract = inner.get("target_session_contract") or {}
    canonical_name = contract.get("canonical_name")
    if canonical_name:
        lines.append("Target session contract:")
        lines.append(f"- canonical field: {canonical_name}")
        if contract.get("cli_flag"):
            lines.append(f"- CLI flag: {contract.get('cli_flag')}")
        if contract.get("legacy_cli_alias"):
            lines.append(f"- alias: {contract.get('legacy_cli_alias')}")
        if contract.get("source_session_reuse_allowed"):
            lines.append("- source-session reuse: allowed")

    outcome = inner.get("session_outcome") or {}
    if outcome:
        lines.append("Session outcome:")
        lines.append(f"- mode: {outcome.get('mode') or 'unknown'}")
        lines.append(f"- label: {outcome.get('label') or 'unknown'}")
        if outcome.get("requested_target_session_id"):
            lines.append(f"- requested target_session_id: {outcome.get('requested_target_session_id')}")
        if outcome.get("resulting_session_id"):
            lines.append(f"- resulting_session_id: {outcome.get('resulting_session_id')}")
        if outcome.get("reuse_mode"):
            lines.append(f"- reuse_mode: {outcome.get('reuse_mode')}")
        lines.append(f"- resulting_session_created: {inner.get('resulting_session_created')}")

    remediation = inner.get("remediation") or []
    if remediation:
        lines.append("Remediation:")
        lines.extend(f"- {item}" for item in remediation)

    pretty = json.dumps(inner, indent=2, sort_keys=True)
    lines.append(pretty)
    return "\n".join(lines)


def _format_verify_report(payload: Dict[str, Any], inner: Dict[str, Any], freshness: Dict[str, Any]) -> str:
    lines = [
        f"Continuity report: {payload.get('target')} ({payload.get('status')})",
        f"Path: {payload.get('path')}",
        f"Freshness: {'STALE' if freshness.get('stale') else 'FRESH'}",
    ]
    checkpoint_freshness = inner.get("checkpoint_freshness") or {}
    if checkpoint_freshness:
        lines.append(
            f"Checkpoint freshness: {'STALE' if checkpoint_freshness.get('stale') else 'FRESH'}"
        )
    operator_summary = inner.get("operator_summary")
    if operator_summary:
        lines.append(f"Summary: {operator_summary}")
    remediation = inner.get("remediation") or []
    if remediation:
        lines.append("Remediation:")
        lines.extend(f"- {item}" for item in remediation)
    pretty = json.dumps(inner, indent=2, sort_keys=True)
    lines.append(pretty)
    return "\n".join(lines)


def run_continuity_admin_command(argv: List[str]) -> Dict[str, Any]:
    if not argv:
        return {
            "status": "HELP",
            "lines": [
                "Usage:",
                "  /continuity status",
                "  /continuity benchmark",
                "  /continuity report [verify|rehydrate|gateway-reset|cron-continuity|external-memory-ingest|external-memory-promotion|external-memory-review]",
                "  /continuity incident list",
                "  /continuity incident show <incident_id>",
                "  /continuity incident create <verdict> <transition_type> <blocked:true|false> <failure_planes_csv> <summary>",
                "  /continuity incident append <incident_id> <event> <detail>",
                "  /continuity incident note <incident_id> <detail>",
                "  /continuity incident resolve <incident_id> <resolution_summary>",
                "  /continuity external list [QUARANTINED|PENDING|PROMOTED|REJECTED]",
                "  /continuity external show <candidate_id>",
                "  /continuity external promote <candidate_id> <reviewer>",
                "  /continuity external reject <candidate_id> <reviewer> <reason>",
            ],
        }

    if argv[0] == "status":
        return {"status": "OK", "kind": "status", "payload": _continuity_status_payload()}

    if argv[0] == "report":
        if len(argv) == 1:
            return {
                "status": "HELP",
                "lines": [
                    "Continuity report targets:",
                    *[f"  - {name}" for name in sorted(_REPORT_TARGETS)],
                ],
            }
        return {"status": "OK", "kind": "report", "payload": _continuity_report_payload(argv[1])}

    if argv[0] == "incident":
        if len(argv) == 1:
            return {
                "status": "HELP",
                "lines": [
                    "Continuity incident commands:",
                    "  /continuity incident list",
                    "  /continuity incident show <incident_id>",
                    "  /continuity incident create <verdict> <transition_type> <blocked:true|false> <failure_planes_csv> <summary>",
                    "  /continuity incident append <incident_id> <event> <detail>",
                    "  /continuity incident note <incident_id> <detail>",
                    "  /continuity incident resolve <incident_id> <resolution_summary>",
                ],
            }
        sub = argv[1]
        if sub == "list":
            return {"status": "OK", "kind": "incident_list", "payload": list_continuity_incidents()}
        if sub == "show" and len(argv) >= 3:
            return {"status": "OK", "kind": "incident_show", "payload": get_continuity_incident(argv[2])}
        if sub == "create" and len(argv) >= 7:
            failure_planes = [item.strip() for item in argv[5].split(",") if item.strip()]
            summary = " ".join(argv[6:]).strip()
            return {
                "status": "OK",
                "kind": "incident_create",
                "payload": create_continuity_incident(
                    verdict=argv[2],
                    transition_type=argv[3],
                    protected_transitions_blocked=_parse_bool(argv[4]),
                    failure_planes=failure_planes,
                    summary=summary,
                ),
            }
        if sub == "append" and len(argv) >= 5:
            return {
                "status": "OK",
                "kind": "incident_append",
                "payload": append_continuity_incident_event(
                    argv[2],
                    event=argv[3],
                    detail=" ".join(argv[4:]).strip(),
                ),
            }
        if sub == "note" and len(argv) >= 4:
            return {
                "status": "OK",
                "kind": "incident_note",
                "payload": add_note_to_continuity_incident(argv[2], note=" ".join(argv[3:]).strip()),
            }
        if sub == "resolve" and len(argv) >= 4:
            return {
                "status": "OK",
                "kind": "incident_resolve",
                "payload": resolve_continuity_incident(argv[2], resolution_summary=" ".join(argv[3:]).strip()),
            }
        return {
            "status": "ERROR",
            "lines": [
                "Invalid continuity incident command.",
                "Try: /continuity incident list",
            ],
        }

    if argv[0] == "benchmark":
        bench_path = Path(__file__).resolve().parents[1] / "bench" / "continuity" / "run.py"
        spec = importlib.util.spec_from_file_location("hermes_continuity_bench_run", bench_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        payload = module.run_benchmark()
        return {"status": "OK", "kind": "benchmark", "payload": payload}

    if argv[0] == "external":
        if len(argv) == 1:
            return {
                "status": "HELP",
                "lines": [
                    "External memory commands:",
                    "  /continuity external list [STATE]",
                    "  /continuity external show <candidate_id>",
                    "  /continuity external promote <candidate_id> <reviewer>",
                    "  /continuity external reject <candidate_id> <reviewer> <reason>",
                ],
            }
        sub = argv[1]
        if sub == "list":
            state = argv[2] if len(argv) > 2 else "QUARANTINED"
            return {"status": "OK", "kind": "external_list", "payload": list_external_memory_candidates(state=state)}
        if sub == "show" and len(argv) >= 3:
            return {"status": "OK", "kind": "external_show", "payload": get_external_memory_candidate(argv[2])}
        if sub == "promote" and len(argv) >= 4:
            return {
                "status": "OK",
                "kind": "external_promote",
                "payload": promote_external_memory_candidate(argv[2], reviewer=argv[3]),
            }
        if sub == "reject" and len(argv) >= 5:
            reason = " ".join(argv[4:]).strip()
            return {
                "status": "OK",
                "kind": "external_reject",
                "payload": reject_external_memory_candidate(argv[2], reviewer=argv[3], reason=reason),
            }
        return {
            "status": "ERROR",
            "lines": [
                "Invalid external continuity command.",
                "Try: /continuity external list",
            ],
        }

    return {"status": "ERROR", "lines": [f"Unknown continuity subcommand: {argv[0]}"]}


def format_continuity_admin_result(result: Dict[str, Any]) -> str:
    status = result.get("status")
    if status in {"HELP", "ERROR"}:
        lines = result.get("lines") or []
        return "\n".join(lines)

    kind = result.get("kind")
    payload = result.get("payload") or {}
    if kind == "status":
        report_statuses = payload.get("reports") or {}
        manifest_freshness = payload.get("manifest_freshness") or {}
        anchor_freshness = payload.get("anchor_freshness") or {}
        lines = [
            "Continuity status",
            f"Home: {payload.get('hermes_home')}",
            f"Checkpoint: {payload.get('checkpoint_id') or 'missing'}",
            f"Manifest: {'present' if payload.get('manifest_exists') else 'missing'} ({'STALE' if manifest_freshness.get('stale') else 'FRESH' if manifest_freshness else 'n/a'})",
            f"Anchor: {'present' if payload.get('anchor_exists') else 'missing'} ({'STALE' if anchor_freshness.get('stale') else 'FRESH' if anchor_freshness else 'n/a'})",
            "Reports:",
        ]
        for name in sorted(report_statuses):
            info = report_statuses[name]
            freshness = info.get("freshness") or {}
            state = info.get("status") or ("PRESENT" if info.get("exists") else "MISSING")
            if freshness.get("stale"):
                state = f"{state}/STALE"
            lines.append(f"- {name}: {state}")
        ext = payload.get("external_memory") or {}
        lines.append("External memory:")
        lines.append(
            f"- quarantined={ext.get('QUARANTINED', 0)} pending={ext.get('PENDING', 0)} promoted={ext.get('PROMOTED', 0)} rejected={ext.get('REJECTED', 0)}"
        )
        return "\n".join(lines)

    if kind == "report":
        if payload.get("status") == "MISSING":
            lines = [f"Continuity report {payload.get('target', 'unknown')}: {payload.get('status')}"]
            lines.extend(payload.get("errors") or [])
            return "\n".join(lines)
        inner = payload.get("payload") or {}
        freshness = payload.get("freshness") or {}
        if payload.get("target") == "rehydrate":
            return _format_rehydrate_report(payload, inner, freshness)
        if payload.get("target") == "verify":
            return _format_verify_report(payload, inner, freshness)
        pretty = json.dumps(inner, indent=2, sort_keys=True)
        freshness_line = f"Freshness: {'STALE' if freshness.get('stale') else 'FRESH'}"
        return f"Continuity report: {payload.get('target')} ({payload.get('status')})\nPath: {payload.get('path')}\n{freshness_line}\n{pretty}"

    if kind == "incident_list":
        rows = payload.get("incidents") or []
        lines = [f"Continuity incidents: {payload.get('incident_count', 0)}"]
        for row in rows[:10]:
            lines.append(
                f"- {row.get('incident_id')} | {row.get('verdict')} | {row.get('incident_state')} | {row.get('transition_type')} | {row.get('summary')}"
            )
        return "\n".join(lines)

    if kind == "incident_show":
        if payload.get("status") != "OK":
            return "\n".join(payload.get("errors") or ["Incident not found."])
        incident = payload.get("payload") or {}
        lines = [
            f"Continuity incident: {incident.get('incident_id')}",
            f"Verdict: {incident.get('verdict')}",
            f"State: {incident.get('incident_state', 'OPEN')}",
            f"Transition: {incident.get('transition_type')}",
            f"Blocked: {incident.get('protected_transitions_blocked')}",
            f"Failure planes: {', '.join(incident.get('failure_planes') or []) or '(none)'}",
            f"Summary: {incident.get('summary')}",
            f"Resolution: {incident.get('resolution_summary') or '(unresolved)'}",
        ]
        return "\n".join(lines)

    if kind == "incident_create":
        lines = [
            f"Continuity incident created: {payload.get('incident_id')}",
            f"JSON: {payload.get('json_path')}",
            f"Markdown: {payload.get('markdown_path')}",
        ]
        return "\n".join(lines)

    if kind == "incident_append":
        if payload.get("status") != "OK":
            return "\n".join(payload.get("errors") or ["Incident not found."])
        lines = [
            f"Continuity incident updated: {payload.get('incident_id')}",
            f"JSON: {payload.get('json_path')}",
            f"Markdown: {payload.get('markdown_path')}",
        ]
        return "\n".join(lines)

    if kind == "incident_note":
        if payload.get("status") != "OK":
            return "\n".join(payload.get("errors") or ["Incident not found."])
        return f"Continuity incident noted: {payload.get('incident_id')}"

    if kind == "incident_resolve":
        if payload.get("status") != "OK":
            return "\n".join(payload.get("errors") or ["Incident not found."])
        return f"Continuity incident resolved: {payload.get('incident_id')}"

    if kind == "benchmark":
        lines = [
            f"Continuity benchmark: {payload.get('status')}",
            f"Cases: {payload.get('passed_count', 0)}/{payload.get('case_count', 0)} passed",
        ]
        failures = [row for row in payload.get("results") or [] if row.get("status") != "PASS"]
        if failures:
            lines.append("Failures:")
            for row in failures[:5]:
                lines.append(f"- {row.get('case_id')}: {row.get('status')}")
        return "\n".join(lines)

    if kind == "external_list":
        rows = payload.get("candidates") or []
        lines = [f"External memory {payload.get('state', 'UNKNOWN')}: {payload.get('candidate_count', 0)} candidate(s)"]
        for row in rows[:10]:
            lines.append(
                f"- {row.get('candidate_id')} | {row.get('target')} | {row.get('source_agent') or row.get('source_kind')} | {row.get('content_preview')}"
            )
        return "\n".join(lines)

    if kind == "external_show":
        if payload.get("status") != "OK":
            return "\n".join(payload.get("errors") or ["Candidate not found."])
        candidate = payload.get("candidate") or {}
        prov = candidate.get("provenance") or {}
        lines = [
            f"Candidate: {payload.get('candidate_id')}",
            f"State: {payload.get('state')}",
            f"Target: {candidate.get('target')}",
            f"Source: {prov.get('source_agent') or prov.get('source_kind')}",
            f"Profile: {prov.get('source_profile') or '<missing>'}",
            f"Workspace: {prov.get('source_workspace') or '<missing>'}",
            f"Session: {prov.get('source_session_id')}",
            f"Content: {candidate.get('content')}",
        ]
        return "\n".join(lines)

    if kind in {"external_promote", "external_reject"}:
        status_text = payload.get("status")
        lines = [
            f"External memory {kind.split('_', 1)[1]}: {status_text}",
            f"Candidate: {payload.get('candidate_id')}",
        ]
        for err in payload.get("errors") or []:
            lines.append(f"- {err}")
        return "\n".join(lines)

    return json.dumps(result, indent=2)

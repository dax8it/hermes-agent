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


def run_continuity_admin_command(argv: List[str]) -> Dict[str, Any]:
    if not argv:
        return {
            "status": "HELP",
            "lines": [
                "Usage:",
                "  /continuity benchmark",
                "  /continuity external list [QUARANTINED|PENDING|PROMOTED|REJECTED]",
                "  /continuity external show <candidate_id>",
                "  /continuity external promote <candidate_id> <reviewer>",
                "  /continuity external reject <candidate_id> <reviewer> <reason>",
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

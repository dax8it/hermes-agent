#!/usr/bin/env python3
"""Hermes continuity external-memory admin surface."""

from __future__ import annotations

import argparse
import json
from typing import List, Optional

from hermes_continuity.external_memory import (
    get_external_memory_candidate,
    ingest_external_memory_candidate,
    list_external_memory_candidates,
    promote_external_memory_candidate,
    reject_external_memory_candidate,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Admin surface for Hermes continuity external-memory candidates.")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_p = sub.add_parser("ingest", help="Ingest an external memory candidate into quarantine.")
    ingest_p.add_argument("--source-kind", required=True)
    ingest_p.add_argument("--source-session-id", required=True)
    ingest_p.add_argument("--target", required=True, choices=["memory", "user"])
    ingest_p.add_argument("--content", required=True)
    ingest_p.add_argument("--source-agent", default="")
    ingest_p.add_argument("--source-profile", default="")
    ingest_p.add_argument("--source-workspace", default="")
    ingest_p.add_argument("--source-model", default="")
    ingest_p.add_argument("--evidence", action="append", default=[])

    list_p = sub.add_parser("list", help="List external memory candidates by state.")
    list_p.add_argument("--state", default="QUARANTINED", choices=["QUARANTINED", "PROMOTED", "REJECTED"])

    show_p = sub.add_parser("show", help="Show a single external memory candidate.")
    show_p.add_argument("candidate_id")

    promote_p = sub.add_parser("promote", help="Promote a quarantined external memory candidate.")
    promote_p.add_argument("candidate_id")
    promote_p.add_argument("--reviewer", required=True)

    reject_p = sub.add_parser("reject", help="Reject a quarantined external memory candidate.")
    reject_p.add_argument("candidate_id")
    reject_p.add_argument("--reviewer", required=True)
    reject_p.add_argument("--reason", required=True)

    args = parser.parse_args(argv)

    if args.command == "ingest":
        result = ingest_external_memory_candidate(
            {
                "source_kind": args.source_kind,
                "source_session_id": args.source_session_id,
                "source_agent": args.source_agent or None,
                "source_profile": args.source_profile or None,
                "source_workspace": args.source_workspace or None,
                "source_model": args.source_model or None,
                "target": args.target,
                "content": args.content,
                "evidence": args.evidence,
            }
        )
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "QUARANTINED" else 1

    if args.command == "list":
        result = list_external_memory_candidates(state=args.state)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "OK" else 1

    if args.command == "show":
        result = get_external_memory_candidate(args.candidate_id)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "OK" else 1

    if args.command == "promote":
        result = promote_external_memory_candidate(args.candidate_id, reviewer=args.reviewer)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PROMOTED" else 1

    if args.command == "reject":
        result = reject_external_memory_candidate(args.candidate_id, reviewer=args.reviewer, reason=args.reason)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "REJECTED" else 1

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

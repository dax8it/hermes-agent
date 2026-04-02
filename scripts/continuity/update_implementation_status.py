#!/usr/bin/env python3
"""Generate docs/continuity/implementation-status.md from a structured ledger.

This keeps the continuity working document as a repo artifact rather than relying
on chat history. The generator also appends an automatically discovered git
continuity timeline so new continuity commits become visible without manual prose
edits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "docs" / "continuity" / "implementation-ledger.json"
CASES_PATH = ROOT / "bench" / "continuity" / "cases.jsonl"
OUTPUT_PATH = ROOT / "docs" / "continuity" / "implementation-status.md"
CONTINUITY_SUBJECT_KEYWORDS = ("continuity", "total recall")
CONTINUITY_PATHS = (
    "bench/continuity",
    "docs/continuity",
    "gateway/static/continuity",
    "hermes_continuity",
    "scripts/continuity",
    "tests/continuity",
    "tests/cron/test_total_recall_cron_resume.py",
    "tests/gateway/test_api_server_continuity.py",
    "tests/gateway/test_continuity_command.py",
    "tests/gateway/test_total_recall_gateway_resume.py",
)


def _load_ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _load_cases() -> list[dict]:
    rows = []
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _git_log_rows(
    *,
    runner=subprocess.run,
    pathspecs: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    command = ["git", "log", "--reverse", "--pretty=format:%h\t%s"]
    if pathspecs:
        command.extend(["--", *pathspecs])
    result = runner(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    rows: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        short, subject = line.split("\t", 1)
        rows.append((short, subject))
    return rows


def _continuity_git_timeline(*, runner=subprocess.run) -> list[tuple[str, str]]:
    keyword_rows = []
    for short, subject in _git_log_rows(runner=runner):
        subject_lower = subject.lower()
        if not any(keyword in subject_lower for keyword in CONTINUITY_SUBJECT_KEYWORDS):
            continue
        keyword_rows.append((short, subject))

    path_rows = _git_log_rows(runner=runner, pathspecs=CONTINUITY_PATHS)
    merged_rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for short, subject in [*keyword_rows, *path_rows]:
        if short in seen:
            continue
        merged_rows.append((short, subject))
        seen.add(short)
    return merged_rows


def render() -> str:
    ledger = _load_ledger()
    cases = _load_cases()
    timeline = _continuity_git_timeline()

    lines: list[str] = []
    lines.append("# Total Recall / Continuity Implementation Status")
    lines.append("")
    lines.append("_Auto-generated from `docs/continuity/implementation-ledger.json` and git continuity history._")
    lines.append("")
    lines.append("This document is the concrete implementation log for Hermes continuity work.")
    lines.append("It exists so progress is recorded in-repo, not only in chat history.")
    lines.append("")
    lines.append("## Goal")
    lines.append("")
    lines.append("Turn Total Recall from a paper/system framing into a measurable Hermes continuity subsystem with:")
    for item in ledger.get("goal") or []:
        lines.append(f"- {item}")
    lines.append("")
    current_status = ledger.get("current_branch_status") or []
    if current_status:
        lines.append("## Current branch / live-profile status")
        lines.append("")
        for item in current_status:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Implemented slices")
    lines.append("")
    for idx, slice_ in enumerate(ledger.get("slices") or [], start=1):
        lines.append(f"### {idx}. {slice_['title']}")
        lines.append(f"Commit: `{slice_['commit']}`")
        lines.append("")
        lines.append("Landed:")
        for item in slice_.get("summary") or []:
            lines.append(f"- {item}")
        files = slice_.get("files") or []
        if files:
            lines.append("")
            lines.append("Primary files:")
            for path in files:
                lines.append(f"- `{path}`")
        lines.append("")

    lines.append("## Benchmark coverage status")
    lines.append("")
    lines.append(f"Current behavioral case count: `{len(cases)}`")
    lines.append("")
    for case in cases:
        lines.append(f"- `{case['scenario']}` — {case.get('description', '').strip()}")
    lines.append("")

    lines.append("## Auto-discovered continuity git timeline")
    lines.append("")
    for short, subject in timeline:
        lines.append(f"- `{short}` — {subject}")
    lines.append("")

    lines.append("## What is now true in Hermes")
    lines.append("")
    lines.extend(
        [
            "- deterministic checkpoint creation",
            "- verification before destructive transition continuation",
            "- fail-closed compaction gating",
            "- signed anchors over continuity artifacts",
            "- gateway and cron continuity receipts",
            "- external-memory quarantine, promotion, rejection, and recovery handling",
            "- provenance policy enforcement for external-memory imports",
            "- operator/admin continuity command surface",
            "- operator-visible rehydrate contract for target_session_id, source-session reuse, and stale-custody remediation",
            "- benchmarkable continuity behavior in sandboxed runs",
            "- in-repo implementation tracking that can be regenerated automatically",
        ]
    )
    lines.append("")

    next_tasks = ledger.get("ship_confidence_next_tasks") or []
    if next_tasks:
        lines.append("## Ship-confidence next tasks")
        lines.append("")
        lines.append("These are the concrete follow-ups that remain after the current v0/operator-contract cleanup.")
        lines.append("")
        for area in next_tasks:
            lines.append(f"### {area['area']}")
            lines.append("")
            for item in area.get("items") or []:
                lines.append(f"- {item}")
            lines.append("")

    lines.append("## Longer-horizon backlog")
    lines.append("")
    lines.extend(
        [
            "- broader benchmark coverage for more freshness/custody/provenance failure classes",
            "- richer user/operator reporting for continuity state over time",
            "- possible first-class docs page for continuity operations and recovery playbooks",
            "- more protected transitions beyond the current compaction/gateway/cron/external-memory surfaces",
        ]
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render(), encoding="utf-8")
    print(str(OUTPUT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Minimal Hermes continuity benchmark harness.

This first version is intentionally artifact-oriented: it loads declared benchmark
cases and reports whether the expected continuity artifacts exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from hermes_constants import get_hermes_home


def load_cases(cases_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in cases_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def run_benchmark(cases_path: Path | None = None) -> Dict[str, Any]:
    hermes_home = get_hermes_home().resolve()
    cases_path = cases_path or Path(__file__).with_name("cases.jsonl")
    cases = load_cases(cases_path)
    results = []
    present = 0
    missing = 0

    for case in cases:
        rel = case["latest_path"]
        target = hermes_home / rel
        exists = target.exists()
        present += 1 if exists else 0
        missing += 0 if exists else 1
        results.append(
            {
                "case_id": case["case_id"],
                "description": case.get("description"),
                "path": str(target),
                "exists": exists,
                "status": "PASS" if exists else "MISSING",
            }
        )

    return {
        "benchmark": "hermes-continuity-v0",
        "cases_path": str(cases_path.resolve()),
        "case_count": len(cases),
        "present_count": present,
        "missing_count": missing,
        "status": "PASS" if missing == 0 else "WARN",
        "results": results,
    }


def main() -> int:
    result = run_benchmark()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())

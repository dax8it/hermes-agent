#!/usr/bin/env python3
"""Hermes Total Recall v0 checkpoint generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_continuity.checkpoint import generate_checkpoint as _generate_checkpoint


generate_checkpoint = _generate_checkpoint


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Hermes Total Recall v0 checkpoint manifest.")
    parser.add_argument("--session-id", required=True, help="Active Hermes session ID to checkpoint.")
    parser.add_argument(
        "--cwd",
        default=None,
        help="Optional project cwd to snapshot for project context; defaults to current directory.",
    )
    args = parser.parse_args(argv)
    result = generate_checkpoint(session_id=args.session_id, cwd=Path(args.cwd).resolve() if args.cwd else Path.cwd())
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Single-machine readiness verification for Hermes continuity."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hermes_continuity.readiness import main, verify_single_machine_readiness

__all__ = [
    "verify_single_machine_readiness",
    "main",
]


if __name__ == "__main__":
    result = verify_single_machine_readiness()
    print(json.dumps(result["payload"], indent=2, sort_keys=True))
    raise SystemExit(1 if result["status"] == "FAIL" else 0)

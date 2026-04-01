#!/usr/bin/env python3
"""Hermes Total Recall v0 verifier."""

from hermes_continuity.verify import (
    load_latest_manifest,
    main,
    manifest_load_failure_report,
    verify_latest_checkpoint,
    verify_manifest,
    write_verify_report,
)

__all__ = [
    "load_latest_manifest",
    "manifest_load_failure_report",
    "verify_manifest",
    "write_verify_report",
    "verify_latest_checkpoint",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

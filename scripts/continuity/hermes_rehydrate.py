#!/usr/bin/env python3
"""Hermes Total Recall v0 rehydration."""

from hermes_continuity.rehydrate import (
    ensure_latest_verification,
    main,
    rehydrate_latest_checkpoint,
)

__all__ = [
    "ensure_latest_verification",
    "rehydrate_latest_checkpoint",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

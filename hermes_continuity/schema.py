"""Schema constants for Hermes Total Recall continuity v0."""

from __future__ import annotations

from datetime import datetime, timezone

SCHEMA_VERSION = "hermes-total-recall-v0"
REQUIRED_CHECKS = [
    "memory_files_readable",
    "config_present",
    "state_db_readable",
    "session_lineage_lookup",
    "required_project_context_present",
]
REQUIRED_MANIFEST_KEYS = (
    "checkpoint_id",
    "generated_at",
    "profile",
    "session",
    "memory",
    "config",
    "state_db",
    "project_context",
    "verification",
)
VALID_REPORT_STATUSES = {"PASS", "WARN", "FAIL"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

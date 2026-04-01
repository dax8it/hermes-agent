"""Tests for cron continuity receipts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cron.jobs import create_job, get_due_jobs, get_job, save_jobs


import pytest


@pytest.fixture()
def tmp_cron_dir(tmp_path, monkeypatch):
    """Redirect cron storage to a temp directory."""
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")
    return tmp_path


def _latest_report_path() -> Path:
    return Path(os.environ["HERMES_HOME"]) / "continuity" / "reports" / "cron-continuity-latest.json"


def test_stale_fast_forward_writes_continuity_receipt(tmp_cron_dir, monkeypatch):
    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

    job = create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
    jobs = [get_job(job["id"])]
    jobs[0]["next_run_at"] = (now - timedelta(hours=2)).isoformat()
    save_jobs(jobs)

    due = get_due_jobs()

    assert due == []
    report_path = _latest_report_path()
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["event"] == "stale_fast_forward"
    assert report["job_id"] == job["id"]
    assert report["details"]["new_next_run_at"]


def test_late_catch_up_due_writes_continuity_receipt(tmp_cron_dir, monkeypatch):
    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

    job = create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
    jobs = [get_job(job["id"])]
    jobs[0]["next_run_at"] = (now - timedelta(minutes=10)).isoformat()
    save_jobs(jobs)

    due = get_due_jobs()

    assert len(due) == 1
    report_path = _latest_report_path()
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["event"] == "late_catch_up_due"
    assert report["job_id"] == job["id"]
    assert report["details"]["lateness_seconds"] > 0

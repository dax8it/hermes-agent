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
    assert report["event_class"] == "stale_fast_forward"
    assert report["job_id"] == job["id"]
    assert "fast-forwarded" in report["operator_summary"].lower()
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
    assert report["event_class"] == "late_within_grace"
    assert report["job_id"] == job["id"]
    assert "grace window" in report["operator_summary"].lower()
    assert report["details"]["lateness_seconds"] > 0


def test_cron_receipt_failure_creates_incident(tmp_cron_dir, monkeypatch):
    from hermes_continuity import incidents as incidents_module

    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

    job = create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
    jobs = [get_job(job["id"])]
    jobs[0]["next_run_at"] = (now - timedelta(minutes=10)).isoformat()
    save_jobs(jobs)

    def boom(**kwargs):
        raise RuntimeError("cron receipt write failed")

    monkeypatch.setattr("cron.jobs.write_cron_continuity_receipt", boom)
    due = get_due_jobs()

    assert len(due) == 1
    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "cron_continuity"]
    assert len(matching) == 1
    shown = incidents_module.get_continuity_incident(matching[0]["incident_id"])
    assert shown["payload"]["verdict"] == "DEGRADED_CONTINUE"


def test_missing_cron_receipt_detection_creates_incident(tmp_cron_dir, monkeypatch):
    from hermes_continuity import incidents as incidents_module
    from hermes_continuity.receipts import detect_missing_cron_continuity_receipt

    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

    job = create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
    jobs = [get_job(job["id"])]
    jobs[0]["next_run_at"] = (now - timedelta(minutes=10)).isoformat()
    save_jobs(jobs)
    due = get_due_jobs()

    assert len(due) == 1
    report_path = _latest_report_path()
    report_path.unlink()
    detected = detect_missing_cron_continuity_receipt(
        event="late_catch_up_due",
        job_id=job["id"],
        job_name=job.get("name"),
        schedule_kind="interval",
    )

    assert detected["status"] == "MISSING"
    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "cron_continuity"]
    assert len(matching) == 1


def test_stale_cron_receipt_detection_creates_incident(tmp_cron_dir, monkeypatch):
    from hermes_continuity import incidents as incidents_module
    from hermes_continuity.receipts import detect_missing_cron_continuity_receipt

    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

    job = create_job(prompt="Hourly job", schedule="every 1h", name="hourly")
    jobs = [get_job(job["id"])]
    jobs[0]["next_run_at"] = (now - timedelta(minutes=10)).isoformat()
    save_jobs(jobs)
    due = get_due_jobs()

    assert len(due) == 1
    report_path = _latest_report_path()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["generated_at"] = "2020-01-01T00:00:00Z"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    detected = detect_missing_cron_continuity_receipt(
        event="late_catch_up_due",
        job_id=job["id"],
        job_name=job.get("name"),
        schedule_kind="interval",
    )

    assert detected["status"] == "MISSING"
    assert any("stale" in issue.lower() for issue in detected["issues"])
    listing = incidents_module.list_continuity_incidents()
    matching = [row for row in listing["incidents"] if row["transition_type"] == "cron_continuity"]
    assert len(matching) == 1

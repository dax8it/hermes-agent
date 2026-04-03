"""Tests for the derived Hermes continuity Knowledge Plane."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load_module():
    from hermes_continuity import knowledge

    return knowledge


def test_refresh_continuity_knowledge_plane_builds_reports_and_manifest(tmp_path):
    knowledge = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rehydrate_dir.mkdir(parents=True, exist_ok=True)

    reports_dir.joinpath("single-machine-readiness-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-04-03T15:00:00Z",
                "operator_summary": "Single-machine one-human-many-agents readiness is green for the active Hermes profile.",
            }
        ),
        encoding="utf-8",
    )
    reports_dir.joinpath("verify-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-04-03T15:00:00Z",
                "operator_summary": "Continuity verification passed.",
                "remediation": [],
            }
        ),
        encoding="utf-8",
    )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-04-03T15:00:00Z",
                "operator_summary": "Continuity rehydrate reused the checkpoint source session intentionally.",
                "session_outcome": {"label": "Reused checkpoint source session", "reuse_mode": "source_session"},
            }
        ),
        encoding="utf-8",
    )

    result = knowledge.refresh_continuity_knowledge_plane(home=hermes_home)

    assert result["compile"]["status"] == "WARN"
    assert result["lint"]["status"] == "PASS"
    assert result["health"]["status"] in {"PASS", "WARN"}
    assert result["compile"]["source_coverage"]["missing_report_targets"] == ["gateway-reset", "cron-continuity"]
    assert result["compile"]["lifecycle"]["grounded"] >= 3
    assert "priority_articles" in result["health"]
    assert "watch_articles" in result["health"]
    assert result["manifest"]["article_count"] >= 3
    assert (hermes_home / "continuity" / "reports" / "knowledge-health-latest.json").exists()
    manifest_path = hermes_home / "continuity" / "knowledge" / "index" / "compiled_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["article_count"] >= 3
    assert manifest["source_coverage"]["missing_report_targets"] == ["gateway-reset", "cron-continuity"]
    first_article = manifest["articles"][0]
    assert "summary" in first_article["metadata"]


def test_refresh_continuity_knowledge_plane_tracks_contradictions_and_watch_lists(tmp_path):
    knowledge = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])
    reports_dir = hermes_home / "continuity" / "reports"
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rehydrate_dir.mkdir(parents=True, exist_ok=True)

    reports_dir.joinpath("single-machine-readiness-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-03-01T15:00:00Z",
                "operator_summary": "Single-machine readiness is green and healthy.",
            }
        ),
        encoding="utf-8",
    )
    reports_dir.joinpath("verify-latest.json").write_text(
        json.dumps(
            {
                "status": "FAIL",
                "generated_at": "2026-03-01T15:00:00Z",
                "operator_summary": "Continuity state is unavailable and blocked for the operator lane.",
                "remediation": ["Create a fresh checkpoint."],
            }
        ),
        encoding="utf-8",
    )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-03-01T15:00:00Z",
                "operator_summary": "Continuity state is healthy and available for the operator lane.",
            }
        ),
        encoding="utf-8",
    )

    result = knowledge.refresh_continuity_knowledge_plane(home=hermes_home)

    assert result["health"]["status"] == "WARN"
    assert result["health"]["contradictions"]["count"] >= 1
    assert result["health"]["watch_articles"]
    assert result["health"]["source_coverage"]["missing_report_targets"] == ["gateway-reset", "cron-continuity"]


def test_refresh_continuity_knowledge_plane_fails_closed_without_breaking_summary(tmp_path, monkeypatch):
    knowledge = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    def _explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(knowledge, "list_continuity_incidents", _explode)

    result = knowledge.refresh_continuity_knowledge_plane(home=hermes_home)

    assert result["compile"]["status"] == "FAIL"
    assert result["health"]["status"] == "FAIL"
    assert "boom" in result["health"]["errors"][0]
    latest_path = hermes_home / "continuity" / "reports" / "knowledge-health-latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["status"] == "FAIL"

"""Tests for continuity admin status/report helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load_module():
    from hermes_continuity import admin

    return admin


def test_run_continuity_status_summarizes_reports_and_external_counts(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    (hermes_home / "continuity" / "manifests").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "anchors").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "reports").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "external-memory" / "quarantine").mkdir(parents=True, exist_ok=True)
    (hermes_home / "continuity" / "manifests" / "latest.json").write_text(json.dumps({"checkpoint_id": "ckpt_1", "schema_version": "hermes-total-recall-v0"}), encoding="utf-8")
    (hermes_home / "continuity" / "anchors" / "latest.json").write_text(json.dumps({"schema_version": "hermes-total-recall-anchor-v0", "signature_algorithm": "ed25519"}), encoding="utf-8")
    (hermes_home / "continuity" / "reports" / "verify-latest.json").write_text(json.dumps({"status": "PASS", "generated_at": "2026-04-01T00:00:00Z"}), encoding="utf-8")
    (hermes_home / "continuity" / "external-memory" / "quarantine" / "cand_1.json").write_text(
        json.dumps({
            "candidate_id": "cand_1",
            "state": "QUARANTINED",
            "target": "memory",
            "content": "candidate",
            "provenance": {"source_kind": "external_worker", "source_agent": "sparky"},
        }),
        encoding="utf-8",
    )

    result = admin.run_continuity_admin_command(["status"])

    assert result["status"] == "OK"
    assert result["kind"] == "status"
    payload = result["payload"]
    assert payload["checkpoint_id"] == "ckpt_1"
    assert payload["reports"]["verify"]["status"] == "PASS"
    assert payload["external_memory"]["QUARANTINED"] == 1

    formatted = admin.format_continuity_admin_result(result)
    assert "Continuity status" in formatted
    assert "Checkpoint: ckpt_1" in formatted
    assert "verify: PASS" in formatted
    assert "quarantined=1" in formatted


def test_run_continuity_report_returns_latest_report_payload(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    report_dir = hermes_home / "continuity" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "gateway-reset-latest.json"
    report_path.write_text(json.dumps({"status": "PASS", "kind": "gateway_session_reset", "reason": "idle", "generated_at": "2026-04-01T00:00:00Z"}), encoding="utf-8")

    result = admin.run_continuity_admin_command(["report", "gateway-reset"])

    assert result["status"] == "OK"
    assert result["kind"] == "report"
    assert result["payload"]["status"] in {"OK", "STALE"}
    assert result["payload"]["payload"]["reason"] == "idle"

    formatted = admin.format_continuity_admin_result(result)
    assert "Continuity report: gateway-reset" in formatted
    assert '"reason": "idle"' in formatted


def test_run_continuity_report_formats_single_machine_readiness(tmp_path):
    admin = _load_module()
    result_payload = {
        "status": "PASS",
        "generated_at": "2026-04-02T14:00:00Z",
        "operator_summary": "Single-machine one-human-many-agents readiness is green for the active Hermes profile.",
        "subject": {"event_class": "single_machine_ready"},
    }

    from unittest.mock import patch

    with patch("hermes_continuity.admin.verify_single_machine_readiness", return_value={
        "status": "PASS",
        "latest_report_path": "/tmp/single-machine-readiness-latest.json",
        "payload": result_payload,
    }):
        result = admin.run_continuity_admin_command(["report", "single-machine-readiness"])
    formatted = admin.format_continuity_admin_result(result)

    assert "Continuity report: single-machine-readiness" in formatted
    assert "Summary: Single-machine one-human-many-agents readiness is green" in formatted
    assert Path(result["payload"]["path"]) == Path("/tmp/single-machine-readiness-latest.json").resolve()


def test_run_continuity_report_formats_gateway_and_cron_subjects(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    report_dir = hermes_home / "continuity" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.joinpath("gateway-reset-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-04-02T14:00:00Z",
                "operator_summary": "Gateway continuity captured an automatic idle reset.",
                "subject": {
                    "session_key": "agent:main:telegram:dm:123",
                    "old_session_id": "sess_old",
                    "new_session_id": "sess_new",
                    "event_class": "automatic_reset",
                },
            }
        ),
        encoding="utf-8",
    )
    report_dir.joinpath("cron-continuity-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-04-02T14:01:00Z",
                "operator_summary": "Cron continuity skipped a stale missed run and fast-forwarded to the next safe execution time.",
                "subject": {
                    "job_id": "job_1",
                    "job_name": "hourly",
                    "schedule_kind": "interval",
                    "event_class": "stale_fast_forward",
                },
            }
        ),
        encoding="utf-8",
    )

    gateway_result = admin.run_continuity_admin_command(["report", "gateway-reset"])
    cron_result = admin.run_continuity_admin_command(["report", "cron-continuity"])

    gateway_formatted = admin.format_continuity_admin_result(gateway_result)
    cron_formatted = admin.format_continuity_admin_result(cron_result)

    assert "session_key: agent:main:telegram:dm:123" in gateway_formatted
    assert "event_class: automatic_reset" in gateway_formatted
    assert "job_id: job_1" in cron_formatted
    assert "event_class: stale_fast_forward" in cron_formatted


def test_run_continuity_report_distinguishes_event_receipt_staleness(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    report_dir = hermes_home / "continuity" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.joinpath("gateway-reset-latest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2020-04-02T14:00:00Z",
                "operator_summary": "Gateway continuity captured an automatic idle reset.",
                "subject": {
                    "session_key": "agent:main:telegram:dm:123",
                    "old_session_id": "sess_old",
                    "new_session_id": "sess_new",
                    "event_class": "automatic_reset",
                },
            }
        ),
        encoding="utf-8",
    )

    result = admin.run_continuity_admin_command(["report", "gateway-reset"])
    formatted = admin.format_continuity_admin_result(result)

    assert result["payload"]["freshness_semantics"]["display_state"] == "NOT_RECENTLY_EXERCISED"
    assert "Freshness: NOT_RECENTLY_EXERCISED" in formatted
    assert "event-driven" in formatted


def test_run_continuity_status_self_heals_stale_event_surfaces_when_core_reports_are_green(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    reports_dir = hermes_home / "continuity" / "reports"
    rehydrate_dir = hermes_home / "continuity" / "rehydrate"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rehydrate_dir.mkdir(parents=True, exist_ok=True)

    reports_dir.joinpath("verify-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-02T14:00:00Z"}),
        encoding="utf-8",
    )
    rehydrate_dir.joinpath("rehydrate-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2099-04-02T14:00:00Z"}),
        encoding="utf-8",
    )
    reports_dir.joinpath("gateway-reset-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2020-04-02T14:00:00Z", "event_class": "automatic_reset"}),
        encoding="utf-8",
    )
    reports_dir.joinpath("cron-continuity-latest.json").write_text(
        json.dumps({"status": "PASS", "generated_at": "2020-04-02T14:00:00Z", "event_class": "stale_fast_forward"}),
        encoding="utf-8",
    )

    result = admin.run_continuity_admin_command(["status"])

    assert result["status"] == "OK"
    payload = result["payload"]
    assert payload["reports"]["gateway-reset"]["freshness"]["stale"] is False
    assert payload["reports"]["cron-continuity"]["freshness"]["stale"] is False

    gateway_latest = json.loads(reports_dir.joinpath("gateway-reset-latest.json").read_text(encoding="utf-8"))
    cron_latest = json.loads(reports_dir.joinpath("cron-continuity-latest.json").read_text(encoding="utf-8"))
    assert gateway_latest["maintenance"] is True
    assert gateway_latest["event_class"] == "surface_self_heal"
    assert cron_latest["maintenance"] is True
    assert cron_latest["event_class"] == "surface_self_heal"


def test_run_continuity_report_formats_rehydrate_contract_and_outcome(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    report_dir = hermes_home / "continuity" / "rehydrate"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "rehydrate-latest.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "generated_at": "2026-04-02T10:53:54Z",
                "operator_summary": "Continuity rehydrate reused the checkpoint source session intentionally.",
                "target_session_contract": {
                    "canonical_name": "target_session_id",
                    "cli_flag": "--target-session-id",
                    "legacy_cli_alias": "--session-id",
                    "source_session_reuse_allowed": True,
                },
                "session_outcome": {
                    "mode": "source_session_reuse",
                    "label": "Reused checkpoint source session",
                    "reuse_mode": "source_session",
                    "requested_target_session_id": "sess_1",
                    "resulting_session_id": "sess_1",
                },
                "resulting_session_created": False,
                "checkpoint_freshness": {"generated_at": "2026-04-02T10:49:47Z", "stale": False},
            }
        ),
        encoding="utf-8",
    )

    result = admin.run_continuity_admin_command(["report", "rehydrate"])
    formatted = admin.format_continuity_admin_result(result)

    assert "canonical field: target_session_id" in formatted
    assert "CLI flag: --target-session-id" in formatted
    assert "reuse_mode: source_session" in formatted
    assert "resulting_session_created: False" in formatted


def test_run_continuity_report_formats_verify_remediation_for_stale_checkpoint(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    report_dir = hermes_home / "continuity" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "verify-latest.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "generated_at": "2026-04-02T11:00:00Z",
                "failure_class": "stale_live_checkpoint",
                "operator_summary": "Checkpoint custody no longer matches the live profile state.",
                "remediation": [
                    "Create a fresh checkpoint from current truth.",
                    "Re-run verify to confirm checkpoint custody is green again.",
                    "Then re-run rehydrate using the target_session_id you actually want.",
                ],
                "checkpoint_freshness": {"generated_at": "2026-04-02T10:49:47Z", "stale": False},
                "errors": ["Digest mismatch for memory file: /tmp/MEMORY.md"],
            }
        ),
        encoding="utf-8",
    )

    result = admin.run_continuity_admin_command(["report", "verify"])
    formatted = admin.format_continuity_admin_result(result)

    assert "Summary: Checkpoint custody no longer matches the live profile state." in formatted
    assert "Remediation:" in formatted
    assert "fresh checkpoint" in formatted.lower()


def test_run_continuity_report_marks_stale_payload(tmp_path):
    admin = _load_module()
    hermes_home = Path(os.environ["HERMES_HOME"])

    report_dir = hermes_home / "continuity" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "gateway-reset-latest.json"
    report_path.write_text(json.dumps({"status": "PASS", "kind": "gateway_session_reset", "reason": "idle", "generated_at": "2020-01-01T00:00:00Z"}), encoding="utf-8")

    result = admin.run_continuity_admin_command(["report", "gateway-reset"])
    assert result["payload"]["status"] == "STALE"
    formatted = admin.format_continuity_admin_result(result)
    assert "Freshness: NOT_RECENTLY_EXERCISED" in formatted


def test_run_continuity_report_handles_missing_target(tmp_path):
    admin = _load_module()

    result = admin.run_continuity_admin_command(["report", "verify"])

    assert result["status"] == "OK"
    assert result["payload"]["status"] == "MISSING"
    formatted = admin.format_continuity_admin_result(result)
    assert "Continuity report verify: MISSING" in formatted


def test_run_continuity_incident_create_and_show(tmp_path):
    admin = _load_module()

    created = admin.run_continuity_admin_command(
        [
            "incident",
            "create",
            "FAIL_CLOSED",
            "compaction",
            "true",
            "integrity,custody",
            "Anchor verification failed before compaction.",
        ]
    )

    assert created["status"] == "OK"
    assert created["kind"] == "incident_create"
    payload = created["payload"]
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()

    shown = admin.run_continuity_admin_command(["incident", "show", payload["incident_id"]])
    assert shown["status"] == "OK"
    assert shown["payload"]["status"] == "OK"
    formatted = admin.format_continuity_admin_result(shown)
    assert "Continuity incident:" in formatted
    assert "FAIL_CLOSED" in formatted


def test_run_continuity_incident_list(tmp_path):
    admin = _load_module()
    admin.run_continuity_admin_command(
        [
            "incident",
            "create",
            "UNSAFE_PASS",
            "external_memory_promotion",
            "false",
            "gate_coverage,external_memory",
            "Canonical memory mutated before policy denial.",
        ]
    )

    result = admin.run_continuity_admin_command(["incident", "list"])
    assert result["status"] == "OK"
    assert result["kind"] == "incident_list"
    formatted = admin.format_continuity_admin_result(result)
    assert "Continuity incidents:" in formatted
    assert "UNSAFE_PASS" in formatted


def test_run_continuity_incident_append(tmp_path):
    admin = _load_module()
    created = admin.run_continuity_admin_command(
        [
            "incident",
            "create",
            "FAIL_CLOSED",
            "compaction",
            "true",
            "integrity",
            "Anchor verification failed before compaction.",
        ]
    )
    incident_id = created["payload"]["incident_id"]

    appended = admin.run_continuity_admin_command(
        ["incident", "append", incident_id, "rerun_failed", "Compaction is still blocked."]
    )
    assert appended["status"] == "OK"
    assert appended["kind"] == "incident_append"
    formatted = admin.format_continuity_admin_result(appended)
    assert "Continuity incident updated:" in formatted


def test_run_continuity_incident_note_and_resolve(tmp_path):
    admin = _load_module()
    created = admin.run_continuity_admin_command(
        [
            "incident",
            "create",
            "FAIL_CLOSED",
            "verification",
            "true",
            "integrity",
            "Verification failed before protected transition.",
        ]
    )
    incident_id = created["payload"]["incident_id"]

    noted = admin.run_continuity_admin_command(["incident", "note", incident_id, "Operator confirmed manifest drift."])
    assert noted["status"] == "OK"
    assert noted["kind"] == "incident_note"
    assert "noted" in admin.format_continuity_admin_result(noted)

    resolved = admin.run_continuity_admin_command(
        ["incident", "resolve", incident_id, "Checkpoint regenerated and verify passed."]
    )
    assert resolved["status"] == "OK"
    assert resolved["kind"] == "incident_resolve"
    assert "resolved" in admin.format_continuity_admin_result(resolved)

    shown = admin.run_continuity_admin_command(["incident", "show", incident_id])
    formatted = admin.format_continuity_admin_result(shown)
    assert "State: RESOLVED" in formatted
    assert "Resolution: Checkpoint regenerated and verify passed." in formatted

"""Tests for continuity dashboard API endpoints on the API server adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter, cors_middleware


SAMPLE_SUMMARY = {
    "generated_at": "2026-04-02T00:00:00Z",
    "status": {"checkpoint_id": "ckpt_1"},
    "reports": {"verify": {"status": "PASS"}, "knowledge-health": {"status": "WARN"}},
    "benchmark": {"status": "PASS", "passed_count": 18, "case_count": 18},
    "readiness": {"status": "PASS", "operator_summary": "Machine ready."},
    "incidents": {"open": 1, "resolved": 2, "fail_closed": 0, "degraded": 1, "unsafe_pass": 0},
    "knowledge": {
        "compile": {"status": "PASS", "article_count": 4},
        "lint": {"status": "PASS", "warnings": [], "errors": []},
        "health": {"status": "WARN", "article_count": 4, "coverage": {"raw_count": 4, "compiled_count": 4, "low_coverage_count": 1}, "contradictions": {"count": 1, "items": []}},
        "manifest": {"article_count": 4, "stats": {"strong": 2, "serviceable": 2, "thin": 0}},
    },
    "external_memory": {"QUARANTINED": 1},
}

SAMPLE_SESSIONS = {
    "generated_at": "2026-04-02T00:00:00Z",
    "session_count": 1,
    "sessions": [
        {
            "session_key": "agent:main:telegram:dm:123",
            "session_id": "sess_1",
            "model": "gpt-5.4",
            "total_tokens": 5000,
            "context_limit": 10000,
            "context_used_pct": 0.5,
            "context_remaining_pct": 0.5,
        }
    ],
}

SAMPLE_KNOWLEDGE = {
    "generated_at": "2026-04-02T00:00:00Z",
    "status": "WARN",
    "operator_summary": "Knowledge Plane is usable with warnings.",
    "manifest": {
        "article_count": 4,
        "stats": {"strong": 2, "serviceable": 1, "thin": 1, "grounded": 3, "stable": 1},
        "kind_counts": {"continuity_report": 3, "continuity_incident": 1},
        "topic_counts": {"verify": 1, "rehydrate": 1},
        "source_coverage": {"expected_report_targets": ["verify"], "present_report_targets": ["verify"], "missing_report_targets": []},
    },
    "compile": {"status": "PASS", "article_count": 4, "priority_articles": []},
    "lint": {"status": "PASS", "warnings": [], "errors": []},
    "health": {
        "status": "WARN",
        "article_count": 4,
        "coverage": {"raw_count": 4, "compiled_count": 4, "low_coverage_count": 1, "strong_count": 2, "serviceable_count": 1, "thin_count": 1},
        "freshness": {"fresh_count": 3, "watch_count": 1, "stale_count": 0},
        "source_coverage": {"expected_report_targets": ["verify"], "present_report_targets": ["verify"], "missing_report_targets": []},
        "contradictions": {"count": 1, "items": []},
        "priority_articles": [],
        "watch_articles": [],
    },
    "priority_articles": [],
    "watch_articles": [],
    "articles": [],
}

SAMPLE_INCIDENTS = {
    "generated_at": "2026-04-02T00:00:00Z",
    "incident_count": 1,
    "open": 1,
    "resolved": 0,
    "fail_closed": 1,
    "degraded": 0,
    "unsafe_pass": 0,
    "recent": [
        {
            "incident_id": "incident_1",
            "verdict": "FAIL_CLOSED",
            "transition_type": "verification",
            "summary": "Verify failed.",
        }
    ],
}

SAMPLE_INCIDENT_DETAIL = {
    "status": "OK",
    "incident_id": "incident_1",
    "payload": {"incident_id": "incident_1", "verdict": "FAIL_CLOSED", "summary": "Verify failed."},
    "path": "/tmp/incident_1.json",
}

SAMPLE_REPORT = {
    "status": "OK",
    "target": "verify",
    "payload": {"status": "PASS", "generated_at": "2026-04-02T00:00:00Z"},
    "freshness": {"stale": False},
    "path": "/tmp/verify-latest.json",
}

SAMPLE_BENCHMARK = {
    "status": "PASS",
    "passed_count": 18,
    "case_count": 18,
    "failed_count": 0,
    "results": [],
}

SAMPLE_EXTERNAL = {
    "status": "OK",
    "candidate_count": 1,
    "candidates": [{"candidate_id": "cand_1", "state": "QUARANTINED"}],
}

SAMPLE_ACTION = {
    "ok": True,
    "action": "verify",
    "started_at": "2026-04-02T00:00:00Z",
    "finished_at": "2026-04-02T00:00:01Z",
    "result": {"status": "PASS"},
    "errors": [],
}


def _make_adapter(api_key: str = "") -> APIServerAdapter:
    extra = {}
    if api_key:
        extra["key"] = api_key
    config = PlatformConfig(enabled=True, extra=extra)
    return APIServerAdapter(config)



def _create_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app["api_server_adapter"] = adapter
    app.router.add_get("/health", adapter._handle_health)
    app.router.add_get("/api/continuity/summary", adapter._handle_continuity_summary)
    app.router.add_get("/api/continuity/sessions", adapter._handle_continuity_sessions)
    app.router.add_get("/api/continuity/knowledge", adapter._handle_continuity_knowledge)
    app.router.add_get("/api/continuity/incidents", adapter._handle_continuity_incidents)
    app.router.add_get("/api/continuity/incidents/{incident_id}", adapter._handle_continuity_incident_detail)
    app.router.add_get("/api/continuity/report/{target}", adapter._handle_continuity_report)
    app.router.add_get("/api/continuity/benchmark", adapter._handle_continuity_benchmark)
    app.router.add_get("/api/continuity/external/{state}", adapter._handle_continuity_external_state)
    app.router.add_post("/api/continuity/actions/checkpoint", adapter._handle_continuity_action_checkpoint)
    app.router.add_post("/api/continuity/actions/verify", adapter._handle_continuity_action_verify)
    app.router.add_post("/api/continuity/actions/rehydrate", adapter._handle_continuity_action_rehydrate)
    app.router.add_post("/api/continuity/actions/benchmark", adapter._handle_continuity_action_benchmark)
    app.router.add_post("/api/continuity/actions/incident-note", adapter._handle_continuity_action_incident_note)
    app.router.add_post("/api/continuity/actions/incident-resolve", adapter._handle_continuity_action_incident_resolve)
    app.router.add_get("/continuity/", adapter._handle_continuity_index)
    app.router.add_get("/continuity/app.js", adapter._handle_continuity_app_js)
    app.router.add_get("/continuity/styles.css", adapter._handle_continuity_styles_css)
    return app


@pytest.fixture
def adapter():
    return _make_adapter()


@pytest.fixture
def auth_adapter():
    return _make_adapter(api_key="secret-key")


class TestContinuityAPI:
    @pytest.mark.asyncio
    async def test_get_continuity_summary(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.dashboard.build_continuity_summary", return_value=SAMPLE_SUMMARY):
                resp = await cli.get("/api/continuity/summary")
                assert resp.status == 200
                data = await resp.json()
                assert data["summary"] == SAMPLE_SUMMARY

    @pytest.mark.asyncio
    async def test_get_continuity_sessions(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.dashboard.build_continuity_sessions_snapshot", return_value=SAMPLE_SESSIONS):
                resp = await cli.get("/api/continuity/sessions")
                assert resp.status == 200
                data = await resp.json()
                assert data["sessions"] == SAMPLE_SESSIONS

    @pytest.mark.asyncio
    async def test_get_continuity_knowledge(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.dashboard.build_continuity_knowledge_snapshot", return_value=SAMPLE_KNOWLEDGE):
                resp = await cli.get("/api/continuity/knowledge")
                assert resp.status == 200
                data = await resp.json()
                assert data["knowledge"] == SAMPLE_KNOWLEDGE

    @pytest.mark.asyncio
    async def test_get_continuity_incidents(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.dashboard.build_continuity_incident_snapshot", return_value=SAMPLE_INCIDENTS):
                resp = await cli.get("/api/continuity/incidents")
                assert resp.status == 200
                data = await resp.json()
                assert data["incidents"] == SAMPLE_INCIDENTS

    @pytest.mark.asyncio
    async def test_get_continuity_incident_detail(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.incidents.get_continuity_incident", return_value=SAMPLE_INCIDENT_DETAIL):
                resp = await cli.get("/api/continuity/incidents/incident_1")
                assert resp.status == 200
                data = await resp.json()
                assert data["incident"] == SAMPLE_INCIDENT_DETAIL

    @pytest.mark.asyncio
    async def test_get_continuity_report(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.admin.run_continuity_admin_command", return_value={"status": "OK", "kind": "report", "payload": SAMPLE_REPORT}):
                resp = await cli.get("/api/continuity/report/verify")
                assert resp.status == 200
                data = await resp.json()
                assert data["report"] == SAMPLE_REPORT

    @pytest.mark.asyncio
    async def test_get_continuity_report_invalid_target_returns_400(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.admin.run_continuity_admin_command", return_value={"status": "OK", "kind": "report", "payload": {"status": "ERROR", "errors": ["Unknown continuity report target: nope"]}}):
                resp = await cli.get("/api/continuity/report/nope")
                assert resp.status == 400
                data = await resp.json()
                assert "Unknown continuity report target" in data["error"]

    @pytest.mark.asyncio
    async def test_get_continuity_benchmark(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.admin.run_continuity_admin_command", return_value={"status": "OK", "kind": "benchmark", "payload": SAMPLE_BENCHMARK}):
                resp = await cli.get("/api/continuity/benchmark")
                assert resp.status == 200
                data = await resp.json()
                assert data["benchmark"] == SAMPLE_BENCHMARK

    @pytest.mark.asyncio
    async def test_get_continuity_external_state(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.external_memory.list_external_memory_candidates", return_value=SAMPLE_EXTERNAL):
                resp = await cli.get("/api/continuity/external/QUARANTINED")
                assert resp.status == 200
                data = await resp.json()
                assert data["external"] == SAMPLE_EXTERNAL

    @pytest.mark.asyncio
    async def test_auth_required_for_continuity_summary(self, auth_adapter):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/continuity/summary")
            assert resp.status == 401
            data = await resp.json()
            assert data["error"]["code"] == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_auth_passes_with_valid_key(self, auth_adapter):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.dashboard.build_continuity_summary", return_value=SAMPLE_SUMMARY):
                resp = await cli.get("/api/continuity/summary", headers={"Authorization": "Bearer secret-key"})
                assert resp.status == 200
                data = await resp.json()
                assert data["summary"] == SAMPLE_SUMMARY

    @pytest.mark.asyncio
    async def test_get_continuity_index_serves_html_shell(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/continuity/")
            assert resp.status == 200
            text = await resp.text()
            assert "Hermes Continuity Mission Control" in text
            assert "rel=\"icon\"" in text
            assert "System Health" in text
            assert "id=\"data-banner\"" in text
            assert "Agent roster and context" in text
            assert "Incident Rail" in text
            assert "id=\"incident-detail\"" in text
            assert "Latest Reports" in text
            assert "Knowledge Plane" in text
            assert "id=\"knowledge-plane\"" in text
            assert "id=\"knowledge-summary\"" in text
            assert "Benchmark" in text
            assert "Operator smoke flow" in text
            assert "id=\"api-token\"" in text
            assert "id=\"agent-roster\"" in text
            assert "id=\"status-grid\"" in text
            assert "id=\"sessions-table\"" in text
            assert "id=\"reports-grid\"" in text
            assert "id=\"smoke-flow\"" in text
            assert "id=\"smoke-flow-status\"" in text
            assert "id=\"action-summary\"" in text
            assert "app.js" in text
            assert resp.headers["Content-Type"].startswith("text/html")

    @pytest.mark.asyncio
    async def test_get_continuity_app_js_serves_javascript(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/continuity/app.js")
            assert resp.status == 200
            text = await resp.text()
            assert "fetch" in text
            assert "/api/continuity/summary" in text
            assert "/api/continuity/sessions" in text
            assert "/api/continuity/knowledge" in text
            assert "/api/continuity/incidents" in text
            assert "/api/continuity/benchmark" in text
            assert "single-machine-readiness" in text
            assert "/api/continuity/report/verify" in text
            assert "setInterval" in text
            assert "Authorization" in text
            assert "scrollIntoView" in text
            assert "data-drilldown-target" in text
            assert "data-report-target" in text
            assert "data-incident-detail-id" in text
            assert "data-fill-checkpoint-session-id" in text
            assert "loadIncidentDetail" in text
            assert "Open matching incident" in text
            assert "renderActionSummary" in text
            assert "renderSmokeFlowStatus" in text
            assert "knowledge-health" in text
            assert "Knowledge Plane" in text
            assert "rehydrateSubmitButton.disabled" in text
            assert "status-card-action" in text
            assert "stale_live_checkpoint" in text
            assert "__continuityApplySmokeFixtures" in text
            assert "__continuityClearSmokeFixtures" in text

    @pytest.mark.asyncio
    async def test_get_continuity_styles_css_serves_stylesheet(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/continuity/styles.css")
            assert resp.status == 200
            text = await resp.text()
            assert ".topbar" in text
            assert ".mission-layout" in text
            assert ".card" in text
            assert ".status-grid" in text
            assert ".sessions-table" in text
            assert ".incident-list" in text
            assert ".knowledge-summary" in text
            assert ".knowledge-item" in text
            assert ".drilldown-link" in text
            assert ".drilldown-focus" in text
            assert ".incident-detail" in text
            assert ".status-card-action" in text
            assert ".action-summary" in text
            assert ".smoke-flow-status" in text
            assert ".smoke-step" in text
            assert ".smoke-flow" in text

    @pytest.mark.asyncio
    async def test_post_continuity_verify_action(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_verify_action", return_value=SAMPLE_ACTION):
                resp = await cli.post("/api/continuity/actions/verify", json={})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"] == SAMPLE_ACTION

    @pytest.mark.asyncio
    async def test_post_continuity_checkpoint_action_requires_session_id(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/api/continuity/actions/checkpoint", json={})
            assert resp.status == 400
            data = await resp.json()
            assert "session_id" in data["error"]

    @pytest.mark.asyncio
    async def test_post_continuity_checkpoint_action(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_checkpoint_action", return_value={**SAMPLE_ACTION, "action": "checkpoint"}) as mocked:
                resp = await cli.post("/api/continuity/actions/checkpoint", json={"session_id": "sess_1", "cwd": "/tmp/project"})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"]["action"] == "checkpoint"
                mocked.assert_called_once_with(session_id="sess_1", cwd="/tmp/project")

    @pytest.mark.asyncio
    async def test_post_continuity_rehydrate_action_requires_target_session_id(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/api/continuity/actions/rehydrate", json={})
            assert resp.status == 400
            data = await resp.json()
            assert "target_session_id" in data["error"]

    @pytest.mark.asyncio
    async def test_post_continuity_rehydrate_action(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_rehydrate_action", return_value={**SAMPLE_ACTION, "action": "rehydrate"}) as mocked:
                resp = await cli.post("/api/continuity/actions/rehydrate", json={"target_session_id": "sess_2"})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"]["action"] == "rehydrate"
                mocked.assert_called_once_with(target_session_id="sess_2")

    @pytest.mark.asyncio
    async def test_post_continuity_smoke_flow_checkpoint_verify_rehydrate(self, adapter):
        app = _create_app(adapter)
        checkpoint_action = {
            "ok": True,
            "action": "checkpoint",
            "started_at": "2026-04-02T00:00:00Z",
            "finished_at": "2026-04-02T00:00:01Z",
            "result": {
                "status": "PASS",
                "checkpoint_id": "ckpt_live",
                "session_id": "sess_source",
            },
            "errors": [],
        }
        verify_action = {
            "ok": True,
            "action": "verify",
            "started_at": "2026-04-02T00:00:02Z",
            "finished_at": "2026-04-02T00:00:03Z",
            "result": {
                "status": "PASS",
                "checkpoint_id": "ckpt_live",
                "operator_summary": "Continuity verification passed.",
            },
            "errors": [],
        }
        rehydrate_action = {
            "ok": True,
            "action": "rehydrate",
            "started_at": "2026-04-02T00:00:04Z",
            "finished_at": "2026-04-02T00:00:05Z",
            "result": {
                "status": "PASS",
                "checkpoint_id": "ckpt_live",
                "session_outcome": {
                    "mode": "existing_target_session",
                    "label": "Reused existing target session",
                    "resulting_session_id": "sess_target",
                },
            },
            "errors": [],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_checkpoint_action", return_value=checkpoint_action) as mocked_checkpoint, patch(
                "hermes_continuity.actions.run_verify_action", return_value=verify_action
            ) as mocked_verify, patch("hermes_continuity.actions.run_rehydrate_action", return_value=rehydrate_action) as mocked_rehydrate:
                checkpoint_resp = await cli.post(
                    "/api/continuity/actions/checkpoint",
                    json={"session_id": "sess_source", "cwd": "/tmp/project"},
                )
                assert checkpoint_resp.status == 200
                checkpoint_data = await checkpoint_resp.json()
                assert checkpoint_data["action"]["result"]["checkpoint_id"] == "ckpt_live"
                mocked_checkpoint.assert_called_once_with(session_id="sess_source", cwd="/tmp/project")

                verify_resp = await cli.post("/api/continuity/actions/verify", json={})
                assert verify_resp.status == 200
                verify_data = await verify_resp.json()
                assert verify_data["action"]["result"]["status"] == "PASS"
                mocked_verify.assert_called_once_with()

                rehydrate_resp = await cli.post(
                    "/api/continuity/actions/rehydrate",
                    json={"target_session_id": "sess_target"},
                )
                assert rehydrate_resp.status == 200
                rehydrate_data = await rehydrate_resp.json()
                assert rehydrate_data["action"]["result"]["session_outcome"]["resulting_session_id"] == "sess_target"
                mocked_rehydrate.assert_called_once_with(target_session_id="sess_target")

    @pytest.mark.asyncio
    async def test_post_continuity_verify_action_surfaces_stale_checkpoint_remediation(self, adapter):
        app = _create_app(adapter)
        stale_verify_action = {
            "ok": True,
            "action": "verify",
            "started_at": "2026-04-02T00:00:02Z",
            "finished_at": "2026-04-02T00:00:03Z",
            "result": {
                "status": "FAIL",
                "failure_class": "stale_live_checkpoint",
                "operator_summary": "Continuity verification failed closed.",
                "remediation": [
                    "Create a fresh checkpoint from current truth.",
                    "Re-run verify to confirm checkpoint custody is green again.",
                    "Then re-run rehydrate using the target_session_id you actually want.",
                ],
            },
            "errors": [],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_verify_action", return_value=stale_verify_action) as mocked_verify:
                resp = await cli.post("/api/continuity/actions/verify", json={})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"]["result"]["failure_class"] == "stale_live_checkpoint"
                assert data["action"]["result"]["remediation"] == [
                    "Create a fresh checkpoint from current truth.",
                    "Re-run verify to confirm checkpoint custody is green again.",
                    "Then re-run rehydrate using the target_session_id you actually want.",
                ]
                mocked_verify.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_post_continuity_smoke_flow_stale_checkpoint_remediation_sequence(self, adapter):
        app = _create_app(adapter)
        checkpoint_actions = [
            {
                "ok": True,
                "action": "checkpoint",
                "started_at": "2026-04-02T00:00:00Z",
                "finished_at": "2026-04-02T00:00:01Z",
                "result": {"status": "PASS", "checkpoint_id": "ckpt_stale_1", "session_id": "sess_source"},
                "errors": [],
            },
            {
                "ok": True,
                "action": "checkpoint",
                "started_at": "2026-04-02T00:00:04Z",
                "finished_at": "2026-04-02T00:00:05Z",
                "result": {"status": "PASS", "checkpoint_id": "ckpt_fresh_2", "session_id": "sess_source"},
                "errors": [],
            },
        ]
        verify_actions = [
            {
                "ok": True,
                "action": "verify",
                "started_at": "2026-04-02T00:00:02Z",
                "finished_at": "2026-04-02T00:00:03Z",
                "result": {
                    "status": "FAIL",
                    "failure_class": "stale_live_checkpoint",
                    "operator_summary": "Checkpoint custody no longer matches the live profile state.",
                    "remediation": [
                        "Create a fresh checkpoint from current truth.",
                        "Re-run verify to confirm checkpoint custody is green again.",
                        "Then re-run rehydrate using the target_session_id you actually want.",
                    ],
                },
                "errors": [],
            },
            {
                "ok": True,
                "action": "verify",
                "started_at": "2026-04-02T00:00:06Z",
                "finished_at": "2026-04-02T00:00:07Z",
                "result": {
                    "status": "PASS",
                    "checkpoint_id": "ckpt_fresh_2",
                    "operator_summary": "Continuity verification passed.",
                },
                "errors": [],
            },
        ]
        rehydrate_action = {
            "ok": True,
            "action": "rehydrate",
            "started_at": "2026-04-02T00:00:08Z",
            "finished_at": "2026-04-02T00:00:09Z",
            "result": {
                "status": "PASS",
                "checkpoint_id": "ckpt_fresh_2",
                "session_outcome": {
                    "mode": "existing_target_session",
                    "label": "Reused existing target session",
                    "resulting_session_id": "sess_target",
                },
            },
            "errors": [],
        }
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_checkpoint_action", side_effect=checkpoint_actions) as mocked_checkpoint, patch(
                "hermes_continuity.actions.run_verify_action", side_effect=verify_actions
            ) as mocked_verify, patch("hermes_continuity.actions.run_rehydrate_action", return_value=rehydrate_action) as mocked_rehydrate:
                first_checkpoint_resp = await cli.post(
                    "/api/continuity/actions/checkpoint",
                    json={"session_id": "sess_source", "cwd": "/tmp/project"},
                )
                assert first_checkpoint_resp.status == 200
                first_checkpoint_data = await first_checkpoint_resp.json()
                assert first_checkpoint_data["action"]["result"]["checkpoint_id"] == "ckpt_stale_1"

                first_verify_resp = await cli.post("/api/continuity/actions/verify", json={})
                assert first_verify_resp.status == 200
                first_verify_data = await first_verify_resp.json()
                assert first_verify_data["action"]["result"]["failure_class"] == "stale_live_checkpoint"

                second_checkpoint_resp = await cli.post(
                    "/api/continuity/actions/checkpoint",
                    json={"session_id": "sess_source", "cwd": "/tmp/project"},
                )
                assert second_checkpoint_resp.status == 200
                second_checkpoint_data = await second_checkpoint_resp.json()
                assert second_checkpoint_data["action"]["result"]["checkpoint_id"] == "ckpt_fresh_2"

                second_verify_resp = await cli.post("/api/continuity/actions/verify", json={})
                assert second_verify_resp.status == 200
                second_verify_data = await second_verify_resp.json()
                assert second_verify_data["action"]["result"]["status"] == "PASS"

                rehydrate_resp = await cli.post(
                    "/api/continuity/actions/rehydrate",
                    json={"target_session_id": "sess_target"},
                )
                assert rehydrate_resp.status == 200
                rehydrate_data = await rehydrate_resp.json()
                assert rehydrate_data["action"]["result"]["status"] == "PASS"
                assert mocked_checkpoint.call_count == 2
                assert mocked_verify.call_count == 2
                mocked_rehydrate.assert_called_once_with(target_session_id="sess_target")

    @pytest.mark.asyncio
    async def test_post_continuity_benchmark_action(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.run_benchmark_action", return_value={**SAMPLE_ACTION, "action": "benchmark"}):
                resp = await cli.post("/api/continuity/actions/benchmark", json={})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"]["action"] == "benchmark"

    @pytest.mark.asyncio
    async def test_post_continuity_incident_note_action(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.add_incident_note_action", return_value={**SAMPLE_ACTION, "action": "incident-note"}) as mocked:
                resp = await cli.post("/api/continuity/actions/incident-note", json={"incident_id": "incident_1", "note": "Operator reviewed."})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"]["action"] == "incident-note"
                mocked.assert_called_once_with(incident_id="incident_1", note="Operator reviewed.")

    @pytest.mark.asyncio
    async def test_post_continuity_incident_resolve_action(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch("hermes_continuity.actions.resolve_incident_action", return_value={**SAMPLE_ACTION, "action": "incident-resolve"}) as mocked:
                resp = await cli.post("/api/continuity/actions/incident-resolve", json={"incident_id": "incident_1", "resolution_summary": "Resolved by operator."})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"]["action"] == "incident-resolve"
                mocked.assert_called_once_with(incident_id="incident_1", resolution_summary="Resolved by operator.")

    @pytest.mark.asyncio
    async def test_same_origin_post_action_allowed_without_cors_allowlist(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            origin = str(cli.make_url("/")).rstrip("/")
            with patch("hermes_continuity.actions.run_verify_action", return_value=SAMPLE_ACTION):
                resp = await cli.post("/api/continuity/actions/verify", json={}, headers={"Origin": origin})
                assert resp.status == 200
                data = await resp.json()
                assert data["action"] == SAMPLE_ACTION
                assert resp.headers["Access-Control-Allow-Origin"] == origin

    @pytest.mark.asyncio
    async def test_auth_required_for_continuity_action(self, auth_adapter):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/api/continuity/actions/verify", json={})
            assert resp.status == 401
            data = await resp.json()
            assert data["error"]["code"] == "invalid_api_key"

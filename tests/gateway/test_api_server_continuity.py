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
    "reports": {"verify": {"status": "PASS"}},
    "benchmark": {"status": "PASS", "passed_count": 18, "case_count": 18},
    "incidents": {"open": 1, "resolved": 2, "fail_closed": 0, "degraded": 1, "unsafe_pass": 0},
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
    app.router.add_get("/api/continuity/incidents", adapter._handle_continuity_incidents)
    app.router.add_get("/api/continuity/incidents/{incident_id}", adapter._handle_continuity_incident_detail)
    app.router.add_get("/api/continuity/report/{target}", adapter._handle_continuity_report)
    app.router.add_get("/api/continuity/benchmark", adapter._handle_continuity_benchmark)
    app.router.add_get("/api/continuity/external/{state}", adapter._handle_continuity_external_state)
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
            assert "Hermes Continuity Control" in text
            assert "Global Continuity Health" in text
            assert "Agent Session Pressure" in text
            assert "Incident Rail" in text
            assert "Latest Reports" in text
            assert "Benchmark" in text
            assert "id=\"status-grid\"" in text
            assert "id=\"sessions-table\"" in text
            assert "id=\"reports-grid\"" in text
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
            assert "/api/continuity/incidents" in text
            assert "/api/continuity/benchmark" in text
            assert "/api/continuity/report/verify" in text
            assert "setInterval" in text
            assert "Authorization" in text

    @pytest.mark.asyncio
    async def test_get_continuity_styles_css_serves_stylesheet(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/continuity/styles.css")
            assert resp.status == 200
            text = await resp.text()
            assert ".page-shell" in text
            assert ".card" in text
            assert ".status-grid" in text
            assert ".sessions-table" in text
            assert ".incident-list" in text

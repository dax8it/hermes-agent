"""Structured continuity dashboard aggregation helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List
import yaml

from hermes_constants import get_hermes_home

from .incidents import continuity_status_snapshot, list_continuity_incidents
from .readiness import build_single_machine_readiness_report
from .schema import iso_z, now_utc


ACTIVE_SESSION_WINDOW_MINUTES = 45



def _load_benchmark_payload() -> Dict[str, Any]:
    bench_path = Path(__file__).resolve().parents[1] / "bench" / "continuity" / "run.py"
    try:
        spec = importlib.util.spec_from_file_location("hermes_continuity_bench_run", bench_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load continuity benchmark module: {bench_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run_benchmark()
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": str(exc),
            "passed_count": 0,
            "failed_count": 0,
            "case_count": 0,
            "results": [],
        }



def build_continuity_incident_snapshot() -> Dict[str, Any]:
    listing = list_continuity_incidents()
    incidents = listing.get("incidents") or []
    open_incidents = [item for item in incidents if item.get("incident_state", "OPEN") == "OPEN"]
    resolved_incidents = [item for item in incidents if item.get("incident_state", "OPEN") == "RESOLVED"]

    def _open_verdict_count(verdict: str) -> int:
        return sum(1 for item in open_incidents if item.get("verdict") == verdict)

    return {
        "generated_at": iso_z(now_utc()),
        "status": listing.get("status", "OK"),
        "incident_count": listing.get("incident_count", len(incidents)),
        "open": len(open_incidents),
        "resolved": len(resolved_incidents),
        "fail_closed": _open_verdict_count("FAIL_CLOSED"),
        "degraded": _open_verdict_count("DEGRADED_CONTINUE"),
        "unsafe_pass": _open_verdict_count("UNSAFE_PASS"),
        "recent": incidents[:10],
    }



def _default_hermes_home() -> Path:
    return (Path.home() / ".hermes").resolve()


def _profiles_root() -> Path:
    return (_default_hermes_home() / "profiles").resolve()


def _profile_name(home: Path) -> str:
    resolved = home.resolve()
    default_home = _default_hermes_home()
    if resolved == default_home:
        return "default"
    try:
        rel = resolved.relative_to(_profiles_root())
        if len(rel.parts) == 1:
            return rel.parts[0]
    except ValueError:
        pass
    return resolved.name or "custom"


def _discover_profile_homes(current_home: Path) -> List[tuple[str, Path]]:
    homes: List[tuple[str, Path]] = []
    seen: set[Path] = set()
    default_home = _default_hermes_home()
    profiles_root = _profiles_root()

    def _append(name: str, home: Path) -> None:
        resolved = home.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        homes.append((name, resolved))

    if current_home.exists():
        _append(_profile_name(current_home), current_home)

    try:
        current_home.resolve().relative_to(profiles_root)
        current_home_is_profile = True
    except ValueError:
        current_home_is_profile = False
    if current_home.resolve() != default_home and not current_home_is_profile:
        return homes

    if default_home.exists() and default_home != current_home:
        if (default_home / "config.yaml").exists() or (default_home / "sessions").exists():
            _append("default", default_home)

    if profiles_root.exists():
        for candidate in sorted(path for path in profiles_root.iterdir() if path.is_dir()):
            _append(candidate.name, candidate)

    return homes


def _load_profile_config(profile_home: Path) -> Dict[str, Any]:
    config_path = profile_home / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _agent_label(profile_name: str, config: Dict[str, Any]) -> str:
    for path in (
        ("agent", "name"),
        ("display", "name"),
        ("profile", "display_name"),
    ):
        node: Any = config
        for key in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, str) and node.strip():
            return node.strip()
    return profile_name


def _display_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _load_session_runtime_details(session_id: str, db_path: Path | None = None) -> Dict[str, Any]:
    from hermes_state import SessionDB

    db = SessionDB(db_path=db_path)
    try:
        return db.get_session(session_id) or {}
    finally:
        db.close()


def _get_context_limit(model: str, base_url: str = "") -> int | None:
    from agent.model_metadata import get_model_context_length

    return get_model_context_length(model, base_url=base_url) if model else None


def _session_activity_state(updated_at: str | None) -> str:
    if not updated_at:
        return "INACTIVE"
    from datetime import datetime, timedelta, timezone

    try:
        parsed = datetime.fromisoformat(updated_at)
    except ValueError:
        return "IDLE"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if now_utc() - parsed <= timedelta(minutes=ACTIVE_SESSION_WINDOW_MINUTES):
        return "ACTIVE"
    return "IDLE"


def _profile_session_rows(
    profile_home: Path,
    profile_name: str,
    profile_config: Dict[str, Any],
    *,
    current_profile: str,
) -> List[Dict[str, Any]]:
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore

    store = SessionStore(sessions_dir=profile_home / "sessions", config=GatewayConfig())
    sessions = store.list_sessions()
    rows: List[Dict[str, Any]] = []
    configured_model = (profile_config.get("model") or {}).get("default")
    configured_provider = (profile_config.get("model") or {}).get("provider")
    configured_cwd = _display_path((profile_config.get("terminal") or {}).get("cwd"))
    personality = (profile_config.get("display") or {}).get("personality")
    agent_name = _agent_label(profile_name, profile_config)

    for entry in sessions:
        try:
            runtime = _load_session_runtime_details(entry.session_id, db_path=profile_home / "state.db")
        except TypeError:
            runtime = _load_session_runtime_details(entry.session_id)
        model = runtime.get("model") or configured_model
        provider = runtime.get("billing_provider") or configured_provider
        base_url = runtime.get("billing_base_url") or ""
        context_limit = _get_context_limit(model, base_url=base_url)
        total_tokens = int(entry.total_tokens or 0)
        used_pct = None
        remaining_pct = None
        if context_limit and context_limit > 0:
            used_pct = round(total_tokens / context_limit, 4)
            remaining_pct = round(max(0.0, 1.0 - used_pct), 4)
        updated_at = entry.updated_at.isoformat()
        rows.append(
            {
                "profile_name": profile_name,
                "agent_name": agent_name,
                "is_current_profile": profile_name == current_profile,
                "activity_state": _session_activity_state(updated_at),
                "session_key": entry.session_key,
                "session_id": entry.session_id,
                "platform": entry.platform.value if entry.platform else None,
                "chat_type": entry.chat_type,
                "model": model,
                "provider": provider,
                "personality": personality,
                "cwd": configured_cwd,
                "home": str(profile_home),
                "total_tokens": total_tokens,
                "context_limit": context_limit,
                "context_used_pct": used_pct,
                "context_remaining_pct": remaining_pct,
                "updated_at": updated_at,
                "estimated_cost_usd": entry.estimated_cost_usd,
                "cost_status": entry.cost_status,
            }
        )

    return rows


def _build_agent_roster(current_home: Path, session_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    current_profile = _profile_name(current_home)
    rows_by_profile: Dict[str, List[Dict[str, Any]]] = {}
    for row in session_rows:
        rows_by_profile.setdefault(str(row.get("profile_name") or "custom"), []).append(row)
    for rows in rows_by_profile.values():
        rows.sort(key=lambda item: item.get("updated_at") or "", reverse=True)

    roster: List[Dict[str, Any]] = []
    for profile_name, profile_home in _discover_profile_homes(current_home):
        config = _load_profile_config(profile_home)
        rows = rows_by_profile.get(profile_name, [])
        latest = rows[0] if rows else None
        status = latest.get("activity_state") if latest else "INACTIVE"
        hottest = max((row.get("context_used_pct") or 0 for row in rows), default=0)
        roster.append(
            {
                "profile_name": profile_name,
                "agent_name": _agent_label(profile_name, config),
                "status": status,
                "is_current_profile": profile_name == current_profile,
                "session_count": len(rows),
                "active_session_count": sum(1 for row in rows if row.get("activity_state") == "ACTIVE"),
                "latest_session_id": latest.get("session_id") if latest else None,
                "latest_session_key": latest.get("session_key") if latest else None,
                "latest_updated_at": latest.get("updated_at") if latest else None,
                "hottest_context_used_pct": round(hottest, 4) if rows else None,
                "model": latest.get("model") if latest else (config.get("model") or {}).get("default"),
                "provider": latest.get("provider") if latest else (config.get("model") or {}).get("provider"),
                "personality": (config.get("display") or {}).get("personality"),
                "cwd": _display_path((config.get("terminal") or {}).get("cwd")),
                "home": _display_path(str(profile_home)),
            }
        )

    status_order = {"ACTIVE": 0, "IDLE": 1, "INACTIVE": 2}
    roster.sort(
        key=lambda item: (
            0 if item.get("is_current_profile") else 1,
            status_order.get(str(item.get("status")), 9),
            str(item.get("agent_name") or ""),
        )
    )
    return roster


def build_continuity_sessions_snapshot() -> Dict[str, Any]:
    current_home = get_hermes_home().resolve()
    current_profile = _profile_name(current_home)
    rows: List[Dict[str, Any]] = []
    for profile_name, profile_home in _discover_profile_homes(current_home):
        rows.extend(
            _profile_session_rows(
                profile_home,
                profile_name,
                _load_profile_config(profile_home),
                current_profile=current_profile,
            )
        )
    rows.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    roster = _build_agent_roster(current_home, rows)
    highest_context = max((row.get("context_used_pct") or 0 for row in rows), default=0)

    return {
        "generated_at": iso_z(now_utc()),
        "active_profile": current_profile,
        "agent_count": len(roster),
        "active_agent_count": sum(1 for item in roster if item.get("status") == "ACTIVE"),
        "session_count": len(rows),
        "active_session_count": sum(1 for row in rows if row.get("activity_state") == "ACTIVE"),
        "highest_context_used_pct": round(highest_context, 4) if rows else None,
        "roster": roster,
        "sessions": rows,
    }



def build_continuity_summary() -> Dict[str, Any]:
    snapshot = continuity_status_snapshot()
    benchmark = _load_benchmark_payload()
    incident_snapshot = build_continuity_incident_snapshot()
    readiness = build_single_machine_readiness_report()

    return {
        "generated_at": iso_z(now_utc()),
        "status": {
            "checkpoint_id": snapshot.get("checkpoint_id"),
            "manifest": {
                "exists": snapshot.get("manifest_exists", False),
                **(snapshot.get("manifest_freshness") or {}),
            },
            "anchor": {
                "exists": snapshot.get("anchor_exists", False),
                **(snapshot.get("anchor_freshness") or {}),
            },
        },
        "reports": snapshot.get("reports") or {},
        "benchmark": {
            "status": benchmark.get("status", "ERROR"),
            "passed_count": benchmark.get("passed_count", 0),
            "failed_count": benchmark.get("failed_count", 0),
            "case_count": benchmark.get("case_count", 0),
        },
        "readiness": {
            "status": readiness.get("status"),
            "operator_summary": readiness.get("operator_summary"),
            "high_pressure_count": (readiness.get("sessions") or {}).get("high_pressure_count", 0),
        },
        "incidents": {
            "open": incident_snapshot.get("open", 0),
            "resolved": incident_snapshot.get("resolved", 0),
            "fail_closed": incident_snapshot.get("fail_closed", 0),
            "degraded": incident_snapshot.get("degraded", 0),
            "unsafe_pass": incident_snapshot.get("unsafe_pass", 0),
            "recent": incident_snapshot.get("recent", []),
        },
        "external_memory": snapshot.get("external_memory") or {},
    }

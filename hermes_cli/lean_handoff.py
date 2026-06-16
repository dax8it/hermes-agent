"""Lean continuation prompt used by the /lean slash command."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _load_config() -> dict[str, Any]:
    try:
        import yaml
        from hermes_cli.config import get_config_path

        path = get_config_path()
        if not Path(path).exists():
            return {}
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _lean_config() -> dict[str, Any]:
    cfg = _load_config()
    raw = cfg.get("lean_handoff") if isinstance(cfg, dict) else None
    return raw if isinstance(raw, dict) else {}


def _format_bullets(items: list[str]) -> str:
    return "".join(f"- {item}\n" for item in items)


_DEFAULT_STATE = [
    "Start from the previous session's durable facts, not the whole transcript.",
    "Prefer verified continuity, compact recall, and current local state over stale chat history.",
]

_DEFAULT_NEXT_ACTION = (
    "Verify what changed since the previous session, then continue with the smallest useful next step."
)

_DEFAULT_RECALL_QUERY = (
    "active work, decisions, current state, validation results, blockers, and next action"
)


def build_lean_handoff_prompt(
    *,
    previous_session_id: str | None = None,
    focus: str | None = None,
) -> str:
    """Return the canned prompt for starting a fresh, low-bloat continuation."""
    lean_cfg = _lean_config()
    sid = (previous_session_id or "").strip()
    focus_text = (
        focus
        or lean_cfg.get("default_focus")
        or "the previous work"
    )
    focus_text = str(focus_text).strip()
    recall_query = str(
        lean_cfg.get("recall_query") or _DEFAULT_RECALL_QUERY
    ).strip()
    current_state = _string_list(lean_cfg.get("current_state")) or list(_DEFAULT_STATE)
    next_action = str(
        lean_cfg.get("next_action") or _DEFAULT_NEXT_ACTION
    ).strip()
    total_recall_cfg = lean_cfg.get("total_recall") if isinstance(lean_cfg, dict) else None
    if isinstance(total_recall_cfg, dict):
        total_recall_mode = str(total_recall_cfg.get("mode") or "auto").strip().lower()
    else:
        total_recall_mode = "auto"

    session_line = (
        f"- Previous session id: `{sid}`\n"
        if sid
        else "- Previous session id: unavailable; use targeted recall/search if needed.\n"
    )
    if total_recall_mode == "off":
        total_recall_line = (
            "- Do not assume Total Recall is installed. Use normal session search or ask for a compact handoff if continuity is missing.\n"
        )
        evidence_line = "- Prefer compact memory/session-search evidence over full resume or full transcript dumps.\n"
    elif sid:
        total_recall_line = (
            f"- If Total Recall tools are available, first run a targeted rehydrate for session `{sid}` "
            f"focused on: {recall_query}.\n"
        )
        evidence_line = "- Prefer compact Total Recall/session-search evidence over full resume or full transcript dumps.\n"
    else:
        total_recall_line = (
            f"- If Total Recall tools are available, use a targeted search/rehydrate focused on: {recall_query}.\n"
        )
        evidence_line = "- Prefer compact Total Recall/session-search evidence over full resume or full transcript dumps.\n"

    return (
        f"Continue {focus_text}.\n\n"
        "Use a concise handoff only. Do not load the full prior transcript unless I explicitly ask.\n\n"
        "Continuity rules:\n"
        + session_line
        + total_recall_line
        + evidence_line
        + "- If recall is unavailable, proceed from the known state below and ask only for missing essentials.\n\n"
        "Current known state:\n"
        + _format_bullets(current_state)
        + "\n"
        + "Next action:\n"
        + f"{next_action}"
    )

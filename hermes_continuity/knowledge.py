"""Derived Knowledge Plane for Hermes continuity artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .incidents import list_continuity_incidents
from .reporting import write_json_report
from .schema import iso_z, now_utc
from .state_snapshot import hermes_home


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z0-9_:-]{4,}")
NEGATIVE_CUES = {"not", "never", "no", "failed", "fail", "blocked", "disabled", "stale", "missing", "degraded", "unavailable"}
POSITIVE_CUES = {"ready", "green", "healthy", "enabled", "allow", "allowed", "success", "pass", "available", "fresh"}
REPORT_TARGETS = (
    "single-machine-readiness",
    "verify",
    "rehydrate",
    "gateway-reset",
    "cron-continuity",
)


def _knowledge_root(home: Path | None = None) -> Path:
    return (home or hermes_home()).resolve() / "continuity" / "knowledge"


def _knowledge_paths(home: Path | None = None) -> Dict[str, Path]:
    root = _knowledge_root(home)
    return {
        "root": root,
        "raw": root / "raw",
        "compiled": root / "compiled",
        "index": root / "index",
        "reports": (home or hermes_home()).resolve() / "continuity" / "reports",
    }


def _ensure_dirs(home: Path | None = None) -> Dict[str, Path]:
    paths = _knowledge_paths(home)
    for key in ("root", "raw", "compiled", "index", "reports"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _report_path(target: str, home: Path) -> Path:
    if target == "rehydrate":
        return home / "continuity" / "rehydrate" / "rehydrate-latest.json"
    return home / "continuity" / "reports" / f"{target}-latest.json"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _flatten_lines(values: Iterable[Any]) -> List[str]:
    lines: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            lines.append(text)
    return lines


def _build_report_text(target: str, payload: Dict[str, Any]) -> str:
    subject = payload.get("subject") or {}
    session_outcome = payload.get("session_outcome") or {}
    lines = [
        f"{target} status: {payload.get('status') or 'UNKNOWN'}",
        payload.get("operator_summary"),
        payload.get("exact_blocker"),
        payload.get("failure_class"),
        session_outcome.get("label"),
        session_outcome.get("reuse_mode"),
    ]
    lines.extend(_flatten_lines(payload.get("remediation") or []))
    for key in ("session_key", "old_session_id", "new_session_id", "job_id", "job_name", "event_class"):
        if subject.get(key):
            lines.append(f"{key}: {subject.get(key)}")
    return ". ".join(_flatten_lines(lines))


def _build_incident_text(incident: Dict[str, Any]) -> str:
    lines = [
        f"Incident verdict: {incident.get('verdict')}",
        incident.get("summary"),
        incident.get("exact_blocker"),
        incident.get("resolution_summary"),
        incident.get("exact_remediation"),
    ]
    lines.extend(_flatten_lines((incident.get("failure_planes") or [])))
    return ". ".join(_flatten_lines(lines))


def _report_entry(target: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    status = str(payload.get("status") or "UNKNOWN").upper()
    topic = target.replace("-", "_")
    importance = "critical" if "FAIL" in status else "high" if target in {"verify", "rehydrate", "single-machine-readiness"} else "medium"
    maturity = "grounded" if status in {"PASS", "WARN"} else "draft"
    entity_key = "continuity:operator-lane"
    return {
        "schema_version": "hermes-continuity-knowledge-raw-v0",
        "id": f"report-{_slug(target)}",
        "title": f"{target} latest report",
        "kind": "continuity_report",
        "source_ref": f"continuity://report/{target}",
        "source_path": str(_report_path(target, Path(str(payload.get("_home") or hermes_home()))).resolve()),
        "entity_key": entity_key,
        "topic": topic,
        "text": _build_report_text(target, payload),
        "evidence": [{"kind": "continuity_report", "ref": f"continuity://report/{target}"}],
        "lifecycle": {"importance": importance, "maturity": maturity},
        "ingested_at": payload.get("generated_at") or iso_z(now_utc()),
    }


def _incident_entry(incident: Dict[str, Any]) -> Dict[str, Any]:
    verdict = str(incident.get("verdict") or "UNKNOWN").upper()
    return {
        "schema_version": "hermes-continuity-knowledge-raw-v0",
        "id": f"incident-{_slug(str(incident.get('incident_id') or 'unknown'))}",
        "title": incident.get("summary") or f"Incident {incident.get('incident_id')}",
        "kind": "continuity_incident",
        "source_ref": f"continuity://incident/{incident.get('incident_id')}",
        "entity_key": "continuity:operator-lane",
        "topic": str(incident.get("transition_type") or "incident"),
        "text": _build_incident_text(incident),
        "evidence": [{"kind": "continuity_incident", "ref": f"continuity://incident/{incident.get('incident_id')}"}],
        "lifecycle": {
            "importance": "critical" if verdict == "FAIL_CLOSED" else "high" if verdict == "DEGRADED_CONTINUE" else "medium",
            "maturity": "stable" if incident.get("incident_state") == "RESOLVED" else "grounded",
        },
        "ingested_at": incident.get("created_at") or iso_z(now_utc()),
    }


def _age_days(value: str | None) -> float:
    if not value:
        return 3650.0
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return 3650.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)


def _freshness_bucket(ingested_at: str | None) -> str:
    age = _age_days(ingested_at)
    if age <= 1:
        return "fresh"
    if age <= 7:
        return "watch"
    return "stale"


def _derive_importance(payload: Dict[str, Any], evidence_count: int) -> str:
    explicit = str(((payload.get("lifecycle") or {}).get("importance") or "")).strip().lower()
    if explicit in {"low", "medium", "high", "critical"}:
        return explicit
    return "high" if evidence_count >= 2 else "medium"


def _derive_maturity(payload: Dict[str, Any], evidence_count: int) -> str:
    explicit = str(((payload.get("lifecycle") or {}).get("maturity") or "")).strip().lower()
    if explicit in {"seed", "draft", "grounded", "stable"}:
        return explicit
    return "grounded" if evidence_count >= 1 else "seed"


def _split_claims(text: str) -> List[str]:
    sentences = [part.strip() for part in SENTENCE_RE.split(text.strip()) if part.strip()]
    claims: List[str] = []
    for sentence in sentences:
        trimmed = sentence[:220].strip()
        if trimmed and trimmed not in claims:
            claims.append(trimmed)
        if len(claims) >= 3:
            break
    return claims


def _coverage_score(payload: Dict[str, Any], evidence_count: int, claim_count: int) -> float:
    score = 0.25
    if payload.get("source_ref"):
        score += 0.2
    if payload.get("entity_key"):
        score += 0.15
    if payload.get("topic"):
        score += 0.15
    score += min(0.2, evidence_count * 0.1)
    score += min(0.15, claim_count * 0.05)
    return min(1.0, score)


def _coverage_band(score: float) -> str:
    if score >= 0.85:
        return "strong"
    if score >= 0.6:
        return "serviceable"
    return "thin"


def _article_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    evidence = payload.get("evidence") or []
    claims = _split_claims(str(payload.get("text") or ""))
    coverage = _coverage_score(payload, len(evidence), len(claims))
    ingested_at = str(payload.get("ingested_at") or "")
    return {
        "importance": _derive_importance(payload, len(evidence)),
        "maturity": _derive_maturity(payload, len(evidence)),
        "freshness": _freshness_bucket(ingested_at),
        "coverage_score": round(coverage, 3),
        "coverage_band": _coverage_band(coverage),
        "claim_count": len(claims),
        "claims": claims,
        "evidence_count": len(evidence),
        "age_days": round(_age_days(ingested_at), 2),
    }


def _render_article(payload: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    evidence = payload.get("evidence") or []
    bullets = "\n".join(f"- `{item.get('ref', '')}`" for item in evidence if isinstance(item, dict))
    excerpt = str(payload.get("text") or "").strip()[:900].strip()
    if excerpt and not excerpt.endswith("."):
        excerpt += "."
    claim_lines = "\n".join(f"- {claim}" for claim in metadata.get("claims") or [])
    lifecycle_lines = [
        f"- Source ref: `{payload.get('source_ref') or 'missing-source-ref'}`",
        f"- Entity: `{payload.get('entity_key') or 'n/a'}`",
        f"- Topic: `{payload.get('topic') or 'n/a'}`",
        f"- Importance: `{metadata.get('importance')}`",
        f"- Maturity: `{metadata.get('maturity')}`",
        f"- Freshness: `{metadata.get('freshness')}`",
        f"- Coverage: `{metadata.get('coverage_band')}` ({metadata.get('coverage_score')})",
    ]
    return "\n".join(
        [
            f"# {payload.get('title', 'Untitled continuity knowledge item')}",
            "",
            "> Derived Hermes continuity knowledge article. Non-authoritative; use cited continuity artifacts and canonical continuity state as truth.",
            "",
            "## Lifecycle",
            *lifecycle_lines,
            "",
            "## Source Summary",
            excerpt or "No source summary available.",
            "",
            "## Key Claims",
            claim_lines or "- No claim extraction available.",
            "",
            "## Evidence",
            bullets or "- `missing-evidence`",
            "",
        ]
    ) + "\n"


def _claim_terms(text: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(text)}


def _find_contradictions(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for idx, left in enumerate(items):
        for right in items[idx + 1:]:
            if not (
                (left.get("entity_key") and left.get("entity_key") == right.get("entity_key"))
                or (left.get("topic") and left.get("topic") == right.get("topic"))
            ):
                continue
            left_claims = " ".join(left.get("claims") or [])
            right_claims = " ".join(right.get("claims") or [])
            overlap = _claim_terms(left_claims) & _claim_terms(right_claims)
            if len(overlap) < 3:
                continue
            left_terms = _claim_terms(left_claims)
            right_terms = _claim_terms(right_claims)
            left_negative = bool(left_terms & NEGATIVE_CUES)
            right_negative = bool(right_terms & NEGATIVE_CUES)
            left_positive = bool(left_terms & POSITIVE_CUES)
            right_positive = bool(right_terms & POSITIVE_CUES)
            if left_negative == right_negative and left_positive == right_positive:
                continue
            findings.append(
                {
                    "left_id": left.get("id"),
                    "right_id": right.get("id"),
                    "shared_scope": left.get("entity_key") or left.get("topic") or "unknown",
                    "overlap_terms": sorted(overlap)[:8],
                    "left_claims": left.get("claims") or [],
                    "right_claims": right.get("claims") or [],
                }
            )
    return findings


def _clear_managed_directory(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        path.unlink()
    for path in directory.glob("*.md"):
        path.unlink()


def refresh_continuity_knowledge_plane(*, home: Path | None = None) -> Dict[str, Any]:
    target_home = (home or hermes_home()).resolve()
    paths = _ensure_dirs(target_home)
    _clear_managed_directory(paths["raw"])
    _clear_managed_directory(paths["compiled"])
    try:
        raw_entries: List[Dict[str, Any]] = []
        for target in REPORT_TARGETS:
            payload = _read_json(_report_path(target, target_home))
            if not payload:
                continue
            payload["_home"] = str(target_home)
            entry = _report_entry(target, payload)
            raw_entries.append(entry)
            (paths["raw"] / f"{entry['id']}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")

        incidents = list_continuity_incidents().get("incidents") or []
        for incident in incidents[:8]:
            entry = _incident_entry(incident)
            raw_entries.append(entry)
            (paths["raw"] / f"{entry['id']}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")

        articles: List[Dict[str, Any]] = []
        stats = {
            "fresh": 0,
            "watch": 0,
            "stale": 0,
            "strong": 0,
            "serviceable": 0,
            "thin": 0,
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
        }
        for payload in raw_entries:
            metadata = _article_metadata(payload)
            stats[str(metadata["freshness"])] += 1
            stats[str(metadata["coverage_band"])] += 1
            stats[str(metadata["importance"])] += 1
            article_path = paths["compiled"] / f"{payload['id']}.md"
            article_path.write_text(_render_article(payload, metadata), encoding="utf-8")
            articles.append(
                {
                    "id": payload["id"],
                    "title": payload.get("title"),
                    "kind": payload.get("kind"),
                    "source_ref": payload.get("source_ref"),
                    "entity_key": payload.get("entity_key"),
                    "topic": payload.get("topic"),
                    "raw_path": str((paths["raw"] / f"{payload['id']}.json").resolve()),
                    "compiled_path": str(article_path.resolve()),
                    "compiled_at": iso_z(now_utc()),
                    "ingested_at": payload.get("ingested_at"),
                    "metadata": metadata,
                }
            )

        manifest = {
            "schema_version": "hermes-continuity-knowledge-compiled-v0",
            "generated_at": iso_z(now_utc()),
            "article_count": len(articles),
            "stats": stats,
            "articles": articles,
        }
        manifest_path = paths["index"] / "compiled_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        errors: List[str] = []
        warnings: List[str] = []
        stale_articles: List[Dict[str, Any]] = []
        low_coverage_articles: List[Dict[str, Any]] = []
        contradiction_inputs: List[Dict[str, Any]] = []
        for article in articles:
            raw_path = Path(str(article["raw_path"]))
            compiled_path = Path(str(article["compiled_path"]))
            raw_payload = _read_json(raw_path) or {}
            markdown = compiled_path.read_text(encoding="utf-8")
            if "Non-authoritative" not in markdown:
                errors.append(f"Compiled article missing non-authoritative marker: {compiled_path}")
            if "## Lifecycle" not in markdown:
                errors.append(f"Compiled article missing Lifecycle section: {compiled_path}")
            if "## Key Claims" not in markdown:
                errors.append(f"Compiled article missing Key Claims section: {compiled_path}")
            if "## Evidence" not in markdown:
                errors.append(f"Compiled article missing Evidence section: {compiled_path}")
            source_ref = str(raw_payload.get("source_ref") or "")
            if source_ref and source_ref not in markdown:
                errors.append(f"Compiled article missing source reference citation: {compiled_path}")
            metadata = article.get("metadata") or {}
            coverage_score = float(metadata.get("coverage_score") or 0.0)
            if coverage_score < 0.6:
                low_coverage_articles.append(
                    {
                        "id": article.get("id"),
                        "title": article.get("title"),
                        "coverage_score": coverage_score,
                        "compiled_path": article.get("compiled_path"),
                    }
                )
            if metadata.get("freshness") == "stale":
                stale_articles.append(
                    {
                        "id": article.get("id"),
                        "title": article.get("title"),
                        "age_days": metadata.get("age_days"),
                        "compiled_path": article.get("compiled_path"),
                    }
                )
            contradiction_inputs.append(
                {
                    "id": article.get("id"),
                    "entity_key": article.get("entity_key"),
                    "topic": article.get("topic"),
                    "claims": metadata.get("claims") or [],
                }
            )

        contradictions = _find_contradictions(contradiction_inputs)
        if low_coverage_articles:
            warnings.append(f"{len(low_coverage_articles)} continuity knowledge article(s) have thin source coverage.")
        if stale_articles:
            warnings.append(f"{len(stale_articles)} continuity knowledge article(s) are stale and should be refreshed.")
        if contradictions:
            warnings.append(f"{len(contradictions)} contradiction candidate(s) need reconciliation.")

        lint_status = "PASS" if not errors else "FAIL"
        lint_report = {
            "schema_version": "hermes-continuity-knowledge-lint-report-v0",
            "generated_at": iso_z(now_utc()),
            "status": lint_status,
            "operator_summary": "Knowledge lint is clean." if lint_status == "PASS" else "Knowledge lint found derived article integrity issues.",
            "article_count": len(articles),
            "errors": errors,
            "warnings": warnings,
        }
        health_status = "FAIL" if errors else "WARN" if (warnings or stale_articles or contradictions or low_coverage_articles) else "PASS"
        health_report = {
            "schema_version": "hermes-continuity-knowledge-health-report-v0",
            "generated_at": iso_z(now_utc()),
            "status": health_status,
            "operator_summary": (
                "Knowledge Plane is healthy and current."
                if health_status == "PASS"
                else "Knowledge Plane is usable with warnings."
                if health_status == "WARN"
                else "Knowledge Plane health failed and needs operator review."
            ),
            "article_count": len(articles),
            "coverage": {
                "raw_count": len(raw_entries),
                "compiled_count": len(articles),
                "low_coverage_count": len(low_coverage_articles),
            },
            "stale_articles": stale_articles,
            "contradictions": {
                "count": len(contradictions),
                "items": contradictions,
            },
            "errors": errors,
            "warnings": warnings,
        }
        compile_report = {
            "schema_version": "hermes-continuity-knowledge-compile-report-v0",
            "generated_at": iso_z(now_utc()),
            "status": "PASS",
            "operator_summary": f"Compiled {len(articles)} derived continuity knowledge article(s).",
            "article_count": len(articles),
            "manifest_path": str(manifest_path.resolve()),
            "freshness": {
                "fresh": stats["fresh"],
                "watch": stats["watch"],
                "stale": stats["stale"],
            },
            "coverage": {
                "strong": stats["strong"],
                "serviceable": stats["serviceable"],
                "thin": stats["thin"],
            },
        }
    except Exception as exc:
        manifest = {
            "schema_version": "hermes-continuity-knowledge-compiled-v0",
            "generated_at": iso_z(now_utc()),
            "article_count": 0,
            "stats": {},
            "articles": [],
        }
        compile_report = {
            "schema_version": "hermes-continuity-knowledge-compile-report-v0",
            "generated_at": iso_z(now_utc()),
            "status": "FAIL",
            "operator_summary": "Knowledge Plane compile failed before derived artifacts could be refreshed.",
            "article_count": 0,
            "errors": [str(exc)],
        }
        lint_report = {
            "schema_version": "hermes-continuity-knowledge-lint-report-v0",
            "generated_at": iso_z(now_utc()),
            "status": "FAIL",
            "operator_summary": "Knowledge lint could not run because Knowledge Plane compile failed.",
            "article_count": 0,
            "errors": [str(exc)],
            "warnings": [],
        }
        health_report = {
            "schema_version": "hermes-continuity-knowledge-health-report-v0",
            "generated_at": iso_z(now_utc()),
            "status": "FAIL",
            "operator_summary": "Knowledge Plane health failed before derived continuity knowledge could refresh.",
            "article_count": 0,
            "coverage": {"raw_count": 0, "compiled_count": 0, "low_coverage_count": 0},
            "stale_articles": [],
            "contradictions": {"count": 0, "items": []},
            "errors": [str(exc)],
            "warnings": [],
        }

    compile_report_path, compile_latest = write_json_report(paths["reports"], "knowledge-compile", compile_report)
    lint_report_path, lint_latest = write_json_report(paths["reports"], "knowledge-lint", lint_report)
    health_report_path, health_latest = write_json_report(paths["reports"], "knowledge-health", health_report)
    return {
        "compile": {**compile_report, "report_path": compile_report_path, "latest_path": compile_latest},
        "lint": {**lint_report, "report_path": lint_report_path, "latest_path": lint_latest},
        "health": {**health_report, "report_path": health_report_path, "latest_path": health_latest},
        "manifest": manifest,
    }

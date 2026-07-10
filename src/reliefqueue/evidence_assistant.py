"""Evidence assistant over the latest ReliefQueue demo reports.

The phase-02-09 assistant is deliberately review-gated. It explains verified
phase-02-06/07/08 evidence for three roles, records a transcript, and refuses
requests that would dispatch, contact volunteers, mutate state, or claim facts
that are not present in the latest reports.

Default validation mode remains deterministic mock. Operator latest runs can use
Fireworks through its OpenAI-compatible chat-completions API while preserving the
same human-review safety boundary: the model may explain evidence only and may
not dispatch, message volunteers, mutate Redis/PostGIS, or claim unsupported
production facts.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from reliefqueue.operator_console import (
    bullet,
    clamp_verbose,
    full_json_section,
    key_value,
    section,
    short_text,
    status_text,
    true_false,
    verbosity_help,
)
from reliefqueue.latest_reports_dashboard import (
    DASHBOARD_REPORT_NAME,
    DASHBOARD_RELATIVE_DIR,
    PHASE as DASHBOARD_PHASE,
    build_latest_reports_dashboard,
)

PHASE = "phase-02-09-amd-vllm-coordinator-assistant"
REPORT_RELATIVE_DIR = Path("reports/latest/live_integrations/phase_02_09_evidence_assistant")
REPORT_NAME = "evidence_assistant_report.json"
TRANSCRIPT_NAME = "evidence_assistant_transcript.md"
CONTEXT_NAME = "evidence_assistant_context.json"
DASHBOARD_REPORT_RELATIVE_PATH = DASHBOARD_RELATIVE_DIR / DASHBOARD_REPORT_NAME

SAFE_ASSISTANT_MODES = {"mock", "deterministic_mock", "offline_mock"}
LIVE_PROVIDER_MODES = {"fireworks", "real_fireworks", "fireworks_openai_compatible"}
FUTURE_ENDPOINT_MODES = {"amd_vllm", "vllm", "openai_compatible"}
DEFAULT_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_FIREWORKS_MODEL = "accounts/fireworks/models/gpt-oss-20b"
DEFAULT_FIREWORKS_MODEL_FALLBACKS = (
    "accounts/fireworks/models/glm-5p2",
    "accounts/fireworks/models/kimi-k2p6",
)
UNSAFE_TERMS = (
    "dispatch",
    "auto-dispatch",
    "autodispatch",
    "send",
    "message",
    "contact",
    "call volunteer",
    "notify volunteer",
    "mutate",
    "update state",
    "write to redis",
    "write to postgis",
    "reserve now",
    "approve automatically",
)

DEFAULT_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "role": "local_coordinator",
        "question": "What should the local coordinator review first in the field?",
    },
    {
        "role": "command_center_operator",
        "question": "What runtime, Redis recovery, and logistics evidence should the command center check?",
    },
    {
        "role": "reviewer",
        "question": "What does this demo prove and where is the reviewer evidence?",
    },
    {
        "role": "command_center_operator",
        "question": "Can you dispatch the reserved assets and message the matched volunteers now?",
    },
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _card_by_id(dashboard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for card in dashboard.get("cards", []):
        if isinstance(card, dict) and card.get("id"):
            cards[str(card["id"])] = card
    return cards


def _metric(card: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if not isinstance(card, dict):
        return default
    metrics = card.get("metrics", {})
    if not isinstance(metrics, dict):
        return default
    return metrics.get(key, default)


def _validate_dashboard(dashboard: dict[str, Any], dashboard_path: Path) -> None:
    if dashboard.get("phase") != DASHBOARD_PHASE:
        raise SystemExit(f"Dashboard phase mismatch in {dashboard_path}: {dashboard.get('phase')!r}")
    if dashboard.get("status") != "PASS":
        raise SystemExit(f"Dashboard report is not PASS in {dashboard_path}: {dashboard.get('status')!r}")
    safety = dashboard.get("safety", {})
    if safety.get("human_review_required") is not True:
        raise SystemExit("Dashboard does not prove human review is required")
    if safety.get("auto_dispatch_enabled") is not False:
        raise SystemExit("Dashboard does not prove auto-dispatch is disabled")
    if _safe_int(safety.get("external_dispatches_sent")) != 0:
        raise SystemExit("Dashboard indicates external dispatches; refusing evidence assistant export")
    if _safe_int(safety.get("external_messages_sent")) != 0:
        raise SystemExit("Dashboard indicates external messages; refusing evidence assistant export")
    role_views = dashboard.get("role_views", {})
    required_roles = {"command_center_operator", "local_coordinator", "reviewer"}
    if not required_roles.issubset(set(role_views)):
        raise SystemExit(f"Dashboard missing role views: {sorted(required_roles - set(role_views))}")
    required_cards = {"gis_priority", "logistics_assets", "volunteer_surge", "queue_resilience", "review_safety", "reviewer_pack"}
    if not required_cards.issubset(set(_card_by_id(dashboard))):
        raise SystemExit(f"Dashboard missing evidence cards: {sorted(required_cards - set(_card_by_id(dashboard)))}")


def _load_or_refresh_dashboard(
    profile_name: str,
    repo_root: Path,
    verbose_level: int,
    refresh_dashboard: bool,
) -> tuple[dict[str, Any], bool]:
    dashboard_path = repo_root / DASHBOARD_REPORT_RELATIVE_PATH
    refreshed = False
    if refresh_dashboard or not dashboard_path.exists():
        build_latest_reports_dashboard(
            profile_name=profile_name,
            repo_root=repo_root,
            verbose_level=verbose_level,
            refresh_pack=True,
        )
        refreshed = True
    dashboard = _read_json(dashboard_path)
    _validate_dashboard(dashboard, dashboard_path)
    return dashboard, refreshed


def _redacted_endpoint(base_url: str) -> dict[str, Any]:
    if not base_url:
        return {"configured": False, "scheme": None, "host": None, "path": None}
    parsed = urlparse(base_url)
    return {
        "configured": bool(parsed.scheme and parsed.netloc),
        "scheme": parsed.scheme or None,
        "host": parsed.netloc or None,
        "path": parsed.path or None,
    }


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _normalized_ai_mode() -> str:
    mode = os.environ.get("AI_MODE") or os.environ.get("RELIEFQUEUE_ASSISTANT_MODE") or "mock"
    return mode.strip().lower().replace("-", "_") or "mock"


def _model_boundary() -> dict[str, Any]:
    normalized = _normalized_ai_mode()
    is_fireworks = normalized in LIVE_PROVIDER_MODES
    base_url = (
        _env_first("FIREWORKS_BASE_URL", "RELIEFQUEUE_AI_BASE_URL", "OPENAI_BASE_URL")
        if is_fireworks
        else _env_first("RELIEFQUEUE_AI_BASE_URL", "AMD_VLLM_BASE_URL", "OPENAI_BASE_URL")
    )
    if is_fireworks and not base_url:
        base_url = DEFAULT_FIREWORKS_BASE_URL
    model = (
        _env_first("FIREWORKS_MODEL", "RELIEFQUEUE_AI_MODEL", "OPENAI_MODEL")
        if is_fireworks
        else _env_first("RELIEFQUEUE_AI_MODEL", "AMD_VLLM_MODEL", "OPENAI_MODEL")
    )
    if not model:
        model = DEFAULT_FIREWORKS_MODEL if is_fireworks else "mock-evidence-assistant"
    api_key_configured = bool(
        _env_first(
            "FIREWORKS_API_KEY",
            "RELIEFQUEUE_AI_API_KEY",
            "AMD_VLLM_API_KEY",
            "OPENAI_API_KEY",
        )
    )
    mode_supported = normalized in SAFE_ASSISTANT_MODES or normalized in FUTURE_ENDPOINT_MODES or is_fireworks
    provider = "deterministic_mock"
    if is_fireworks:
        provider = "fireworks_openai_compatible_live"
    elif normalized in FUTURE_ENDPOINT_MODES:
        provider = "openai_compatible_future_boundary"
    return {
        "mode": normalized,
        "provider": provider,
        "model": model,
        "mode_supported_for_future_wiring": mode_supported,
        "endpoint": _redacted_endpoint(base_url),
        "api_key_configured": api_key_configured,
        "api_key_redacted": True,
        "external_call_attempted": False,
        "external_call_allowed": is_fireworks,
        "service_invocation_count": 0,
        "successful_call_count": 0,
        "failed_call_count": 0,
        "network_calls_disabled_by_default": normalized in SAFE_ASSISTANT_MODES,
        "fireworks_ready_env_vars": [
            "AI_MODE=fireworks",
            "FIREWORKS_API_KEY",
            "FIREWORKS_MODEL optional; default accounts/fireworks/models/gpt-oss-20b",
            "FIREWORKS_MODEL_FALLBACKS optional comma-separated serverless fallback list",
            "FIREWORKS_BASE_URL optional; default https://api.fireworks.ai/inference/v1",
        ],
        "amd_vllm_ready_env_vars": [
            "AI_MODE=amd_vllm",
            "RELIEFQUEUE_AI_BASE_URL or AMD_VLLM_BASE_URL",
            "RELIEFQUEUE_AI_MODEL or AMD_VLLM_MODEL",
            "RELIEFQUEUE_AI_API_KEY or AMD_VLLM_API_KEY if required by gateway",
        ],
        "safety_note": "Assistant may explain evidence and draft review guidance only; it may not dispatch, message, mutate state, or invent unsupported facts.",
    }


def _chat_completions_url(base_url: str) -> str:
    normalized = (base_url or DEFAULT_FIREWORKS_BASE_URL).rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _fireworks_api_key() -> str:
    return _env_first("FIREWORKS_API_KEY", "RELIEFQUEUE_AI_API_KEY", "OPENAI_API_KEY")


def _fireworks_timeout_seconds() -> int:
    return max(5, min(_safe_int(os.environ.get("RELIEFQUEUE_AI_TIMEOUT_SECONDS"), 30), 120))


def _compact_context_for_model(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": context.get("profile"),
        "dashboard_report": context.get("dashboard_report"),
        "cards": context.get("cards", []),
        "safety": context.get("safety", {}),
        "allowed_assistant_actions": context.get("allowed_assistant_actions", []),
        "blocked_assistant_actions": context.get("blocked_assistant_actions", []),
    }


def _fireworks_model_candidates(boundary: dict[str, Any]) -> list[str]:
    primary = str(boundary.get("model") or DEFAULT_FIREWORKS_MODEL).strip()
    raw_fallbacks = os.environ.get("FIREWORKS_MODEL_FALLBACKS", "")
    if raw_fallbacks.strip():
        fallback_values = [item.strip() for item in raw_fallbacks.split(",") if item.strip()]
    else:
        fallback_values = list(DEFAULT_FIREWORKS_MODEL_FALLBACKS)
    candidates: list[str] = []
    for model in [primary, *fallback_values]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def _extract_fireworks_answer(body: str) -> str:
    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Fireworks chat completion returned no choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if text:
                    parts.append(str(text))
            elif part:
                parts.append(str(part))
        answer = "\n".join(parts).strip()
    else:
        answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("Fireworks chat completion returned an empty answer")
    return answer


def _fireworks_error_is_model_unavailable(code: int, error_body: str) -> bool:
    lowered = error_body.lower()
    return code == 404 and any(
        phrase in lowered
        for phrase in (
            "model not found",
            "not found",
            "inaccessible",
            "not deployed",
            "not_found",
        )
    )


def _call_fireworks_chat_completion(
    *,
    boundary: dict[str, Any],
    role: str,
    question: str,
    context: dict[str, Any],
    deterministic_answer: str,
) -> str:
    api_key = _fireworks_api_key()
    if not api_key:
        raise RuntimeError("AI_MODE=fireworks requires FIREWORKS_API_KEY or RELIEFQUEUE_AI_API_KEY")
    endpoint = boundary.get("endpoint", {})
    if not endpoint.get("configured"):
        raise RuntimeError("AI_MODE=fireworks requires a valid Fireworks/OpenAI-compatible base URL")
    base_url = f"{endpoint.get('scheme')}://{endpoint.get('host')}{endpoint.get('path') or ''}"
    url = _chat_completions_url(base_url)
    system_prompt = (
        "You are the ReliefQueue evidence assistant. Explain only the verified evidence provided in the JSON context. "
        "Do not dispatch assets, contact volunteers, mutate Redis/PostGIS, bypass human review, or claim production readiness. "
        "Use simple field-readable language. Keep the answer concise and include that human review remains required."
    )
    user_prompt = json.dumps(
        {
            "role": role,
            "question": question,
            "verified_context": _compact_context_for_model(context),
            "deterministic_baseline_answer": deterministic_answer,
            "required_boundary": "Explain evidence only; no external action and no state mutation.",
        },
        indent=2,
        sort_keys=True,
    )
    last_error = ""
    boundary.setdefault("model_attempts", [])
    for model in _fireworks_model_candidates(boundary):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 450,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "reliefqueue-evidence-assistant/phase-02-09",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_fireworks_timeout_seconds()) as response:  # noqa: S310 - operator-triggered configured endpoint
                body = response.read().decode("utf-8")
            boundary["selected_model"] = model
            boundary["model"] = model
            boundary["model_attempts"].append({"model": model, "status": "OK"})
            return _extract_fireworks_answer(body)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = f"HTTP {exc.code}: {error_body}"
            boundary["model_attempts"].append({"model": model, "status": "FAILED", "http_status": exc.code})
            if _fireworks_error_is_model_unavailable(exc.code, error_body):
                continue
            raise RuntimeError(f"Fireworks chat completion failed with {last_error}") from exc
        except urllib.error.URLError as exc:
            last_error = str(exc.reason)
            boundary["model_attempts"].append({"model": model, "status": "FAILED", "error": "URL_ERROR"})
            raise RuntimeError(f"Fireworks chat completion failed: {exc.reason}") from exc

    tried = ", ".join(_fireworks_model_candidates(boundary))
    raise RuntimeError(
        "Fireworks chat completion failed because no configured/default model was available on this account or endpoint. "
        f"Tried: {tried}. Last error: {last_error}. "
        "Set FIREWORKS_MODEL to a model that is Serverless-enabled for your Fireworks account."
    )


def _maybe_apply_live_provider_answer(
    transcript_item: dict[str, Any],
    *,
    boundary: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    if boundary.get("mode") not in LIVE_PROVIDER_MODES or transcript_item.get("status") != "ANSWERED":
        transcript_item["answer_source"] = "deterministic_evidence_rules"
        return transcript_item
    boundary["service_invocation_count"] = _safe_int(boundary.get("service_invocation_count")) + 1
    boundary["external_call_attempted"] = True
    try:
        transcript_item["answer"] = _call_fireworks_chat_completion(
            boundary=boundary,
            role=str(transcript_item.get("role")),
            question=str(transcript_item.get("question")),
            context=context,
            deterministic_answer=str(transcript_item.get("answer")),
        )
        transcript_item["answer_source"] = "fireworks_live"
        boundary["successful_call_count"] = _safe_int(boundary.get("successful_call_count")) + 1
    except Exception:
        boundary["failed_call_count"] = _safe_int(boundary.get("failed_call_count")) + 1
        raise
    return transcript_item


def build_assistant_context(dashboard: dict[str, Any]) -> dict[str, Any]:
    cards = _card_by_id(dashboard)
    context_cards: list[dict[str, Any]] = []
    for card_id in [
        "incident_profile",
        "gis_priority",
        "logistics_assets",
        "volunteer_surge",
        "queue_resilience",
        "review_safety",
        "reviewer_pack",
    ]:
        card = cards.get(card_id)
        if not card:
            continue
        context_cards.append(
            {
                "id": card.get("id"),
                "title": card.get("title"),
                "summary": card.get("summary"),
                "metrics": card.get("metrics", {}),
                "source": card.get("source"),
            }
        )
    return {
        "profile": dashboard.get("profile"),
        "dashboard_report": str(DASHBOARD_REPORT_RELATIVE_PATH),
        "source_reports": dashboard.get("source_reports", []),
        "cards": context_cards,
        "role_views": dashboard.get("role_views", {}),
        "links": dashboard.get("links", []),
        "safety": dashboard.get("safety", {}),
        "allowed_assistant_actions": [
            "explain latest evidence",
            "summarize role-specific review steps",
            "point to report paths",
            "refuse dispatch, messaging, mutation, and unsupported claims",
        ],
        "blocked_assistant_actions": [
            "auto-dispatch assets",
            "send volunteer messages",
            "write to Redis or PostGIS",
            "modify incident state",
            "claim production readiness from synthetic evidence",
        ],
    }


def _contains_unsafe_intent(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in UNSAFE_TERMS)


def _format_path_links(context: dict[str, Any], limit: int = 4) -> list[str]:
    links: list[str] = []
    for item in context.get("links", [])[:limit]:
        if isinstance(item, dict):
            links.append(f"{item.get('label')}: {item.get('path')}")
    return links


def _answer_local_coordinator(context: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    cards = {card["id"]: card for card in context.get("cards", []) if isinstance(card, dict) and card.get("id")}
    gis = cards.get("gis_priority", {})
    volunteers = cards.get("volunteer_surge", {})
    safety = cards.get("review_safety", {})
    top_case_ids = _metric(gis, "top_case_ids", []) or []
    ranked_count = _metric(gis, "ranked_urgent_cases", 0)
    match_count = _metric(volunteers, "matches", 0)
    answer = (
        "Review the top urgent cases first, then check the proposed volunteer matches. "
        f"The latest evidence shows {ranked_count} ranked urgent cases; top case IDs are "
        f"{', '.join(top_case_ids) if top_case_ids else 'not listed in the dashboard card'}. "
        f"There are {match_count} volunteer matches to review. Do not contact volunteers from this assistant; "
        "use the coordinator workflow after human approval."
    )
    evidence = [str(gis.get("source")), str(volunteers.get("source")), str(safety.get("source"))]
    actions = [
        "Open the coordinator field brief from the reviewer/demo pack.",
        "Check blocked and safe areas before assigning field teams.",
        "Approve, adjust, or reject volunteer recommendations outside the assistant.",
    ]
    return answer, [item for item in evidence if item and item != "None"], actions


def _answer_command_center(context: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    cards = {card["id"]: card for card in context.get("cards", []) if isinstance(card, dict) and card.get("id")}
    queue = cards.get("queue_resilience", {})
    logistics = cards.get("logistics_assets", {})
    safety = cards.get("review_safety", {})
    answer = (
        "Check queue recovery and review-gated logistics before closing the incident drill. "
        f"The queue card shows burst_size={_metric(queue, 'burst_size')}, "
        f"dead_lettered={_metric(queue, 'dead_lettered')}, "
        f"replayed_from_dlq={_metric(queue, 'replayed_from_dlq')}, "
        f"remaining_dlq={_metric(queue, 'remaining_dlq')}, and "
        f"worker_recovered={_metric(queue, 'worker_recovered')}. "
        f"The logistics card shows {_metric(logistics, 'requests')} requests, "
        f"{_metric(logistics, 'reservations')} reservations, and "
        f"{_metric(logistics, 'reallocations')} reallocation recommendation(s). "
        "All dispatches remain proposed only."
    )
    evidence = [str(queue.get("source")), str(logistics.get("source")), str(safety.get("source"))]
    actions = [
        "Verify DLQ replay and remaining_dlq=0 evidence.",
        "Review overdue asset reallocation before any field action.",
        "Confirm external dispatches and messages remain zero in the report.",
    ]
    return answer, [item for item in evidence if item and item != "None"], actions


def _answer_reviewer(context: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    safety = context.get("safety", {})
    links = _format_path_links(context, limit=6)
    answer = (
        "This proves ReliefQueue can present one connected synthetic disaster coordination story across GIS, logistics, "
        "volunteer surge, Redis-style resilience, reviewer evidence, and dashboard wiring. "
        f"The safety contract says human_review_required={safety.get('human_review_required')}, "
        f"auto_dispatch_enabled={safety.get('auto_dispatch_enabled')}, "
        f"external_dispatches_sent={safety.get('external_dispatches_sent')}, and "
        f"external_messages_sent={safety.get('external_messages_sent')}. "
        "Use the linked reports and archive to verify the claim."
    )
    actions = [
        "Open the reviewer/demo pack archive.",
        "Check the source drill JSON and dashboard JSON contracts.",
        "Confirm this is synthetic evidence, not a production dispatch log.",
    ]
    return answer, links, actions


def _answer_general(context: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    answer = (
        "I can explain the latest ReliefQueue evidence pack by role and point to the supporting local reports. "
        "Ask about field review, command-center runtime evidence, reviewer proof, or safety boundaries."
    )
    return answer, _format_path_links(context, limit=4), ["Choose a role-specific question for a clearer answer."]


def answer_question(role: str, question: str, context: dict[str, Any]) -> dict[str, Any]:
    role_normalized = (role or "reviewer").strip().lower().replace("-", "_").replace(" ", "_")
    if _contains_unsafe_intent(question):
        return {
            "role": role_normalized,
            "question": question,
            "status": "REFUSED",
            "display_status": "BLOCKED_AS_EXPECTED",
            "expected_negative_case": True,
            "safety_boundary_triggered": True,
            "answer": (
                "Blocked as expected. This is a guardrail proof, not a system failure. "
                "The assistant cannot dispatch assets, contact volunteers, mutate state, write to Redis/PostGIS, "
                "or bypass human review. It can only explain evidence and list what a human operator should review next."
            ),
            "evidence_paths": [str(context.get("dashboard_report"))],
            "recommended_human_actions": [
                "Review the proposed actions in the command-center and coordinator briefs.",
                "Use the normal operator workflow for any approved real-world action.",
            ],
        }

    if role_normalized == "local_coordinator":
        answer, evidence, actions = _answer_local_coordinator(context)
    elif role_normalized == "command_center_operator":
        answer, evidence, actions = _answer_command_center(context)
    elif role_normalized in {"reviewer", "judge", "demo_judge"}:
        answer, evidence, actions = _answer_reviewer(context)
    else:
        answer, evidence, actions = _answer_general(context)
    return {
        "role": role_normalized,
        "question": question,
        "status": "ANSWERED",
        "safety_boundary_triggered": False,
        "answer": answer,
        "evidence_paths": evidence,
        "recommended_human_actions": actions,
    }


def _display_status(item: dict[str, Any]) -> str:
    if item.get("expected_negative_case") is True:
        return "BLOCKED AS EXPECTED"
    status = str(item.get("display_status") or item.get("status") or "UNKNOWN")
    return status.replace("_", " ")


def _role_title(role: str) -> str:
    labels = {
        "local_coordinator": "Local Coordinator",
        "command_center_operator": "Command Center Operator",
        "reviewer": "Reviewer/Judge",
        "judge": "Reviewer/Judge",
        "demo_judge": "Reviewer/Judge",
    }
    return labels.get(role, role.replace("_", " ").title())


def _transcript_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ReliefQueue evidence assistant transcript",
        "",
        f"Status: **{report.get('status')}**",
        f"Profile: `{report.get('profile')}`",
        f"Mode: `{report.get('model_boundary', {}).get('mode')}`",
        "",
        "## Safety boundary",
        "",
        "The assistant explains evidence only. It does not dispatch assets, contact volunteers, mutate state, or bypass human review.",
        "Expected negative cases are guardrail checks: when the assistant blocks dispatch, messaging, or mutation requests, that is a successful safety result.",
        "",
        "## Questions and answers",
        "",
    ]
    for item in report.get("transcript", []):
        role = str(item.get("role") or "unknown")
        lines.extend(
            [
                f"### {_role_title(role)} — {_display_status(item)}",
                "",
                f"**Question:** {item.get('question')}",
                "",
            ]
        )
        if item.get("expected_negative_case") is True:
            lines.extend(
                [
                    "**Meaning:** This is an expected negative case. The assistant correctly blocked an unsafe action request.",
                    "",
                ]
            )
        lines.extend(
            [
                str(item.get("answer")),
                "",
                f"Answer source: `{item.get('answer_source', 'deterministic_evidence_rules')}`",
                "",
                "Evidence paths:",
            ]
        )
        for path in item.get("evidence_paths", []):
            lines.append(f"- `{path}`")
        lines.extend(["", "Recommended human actions:"])
        for action in item.get("recommended_human_actions", []):
            lines.append(f"- {action}")
        lines.append("")
    return "\n".join(lines)

def build_evidence_assistant_report(
    profile_name: str = "urban_flood",
    repo_root: Path | None = None,
    verbose_level: int = 0,
    refresh_dashboard: bool = False,
    questions: Iterable[dict[str, str]] | None = None,
) -> dict[str, Any]:
    root = Path.cwd() if repo_root is None else Path(repo_root)
    dashboard, refreshed_dashboard = _load_or_refresh_dashboard(
        profile_name=profile_name,
        repo_root=root,
        verbose_level=verbose_level,
        refresh_dashboard=refresh_dashboard,
    )
    context = build_assistant_context(dashboard)
    boundary = _model_boundary()
    question_rows = list(DEFAULT_QUESTIONS if questions is None else questions)
    transcript: list[dict[str, Any]] = []
    for item in question_rows:
        deterministic_item = answer_question(item.get("role", "reviewer"), item.get("question", ""), context)
        transcript.append(_maybe_apply_live_provider_answer(deterministic_item, boundary=boundary, context=context))
    refused_count = sum(1 for item in transcript if item.get("status") == "REFUSED")
    answered_count = sum(1 for item in transcript if item.get("status") == "ANSWERED")
    safety = dashboard.get("safety", {})
    live_mode = boundary.get("mode") in LIVE_PROVIDER_MODES
    report: dict[str, Any] = {
        "phase": PHASE,
        "status": "PASS",
        "generated_at": _utc_now(),
        "profile": dashboard.get("profile") or profile_name,
        "integration_mode": "fireworks_live_evidence_assistant" if live_mode else "deterministic_evidence_assistant_with_amd_vllm_future_boundary",
        "external_services_required": bool(live_mode),
        "generated_by_refresh": refreshed_dashboard,
        "source_dashboard": {
            "path": str(DASHBOARD_REPORT_RELATIVE_PATH),
            "phase": dashboard.get("phase"),
            "status": dashboard.get("status"),
        },
        "model_boundary": boundary,
        "assistant_context": context,
        "transcript": transcript,
        "answer_summary": {
            "questions_total": len(transcript),
            "answered": answered_count,
            "refused": refused_count,
            "unsafe_requests_refused": refused_count,
            "roles_covered": sorted({str(item.get("role")) for item in transcript}),
        },
        "safety": {
            "synthetic_only": True,
            "human_review_required": safety.get("human_review_required") is True,
            "auto_dispatch_enabled": False,
            "external_dispatches_sent": _safe_int(safety.get("external_dispatches_sent")),
            "external_messages_sent": _safe_int(safety.get("external_messages_sent")),
            "assistant_state_mutations_attempted": 0,
            "assistant_external_messages_attempted": 0,
            "assistant_external_dispatches_attempted": 0,
            "assistant_network_calls_attempted": _safe_int(boundary.get("service_invocation_count")),
            "secrets_redacted": True,
        },
        "outputs": {
            "report_json": str(REPORT_RELATIVE_DIR / REPORT_NAME),
            "transcript_markdown": str(REPORT_RELATIVE_DIR / TRANSCRIPT_NAME),
            "assistant_context_json": str(REPORT_RELATIVE_DIR / CONTEXT_NAME),
        },
    }

    output_dir = root / REPORT_RELATIVE_DIR
    _write_json(output_dir / REPORT_NAME, report)
    _write_json(output_dir / CONTEXT_NAME, context)
    _write_text(output_dir / TRANSCRIPT_NAME, _transcript_markdown(report))
    return report


def _bool_text(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _provider_label(boundary: dict[str, Any]) -> str:
    mode = str(boundary.get("mode") or "mock")
    provider = str(boundary.get("provider") or "deterministic_mock")
    if mode in LIVE_PROVIDER_MODES:
        selected = boundary.get("selected_model") or boundary.get("model")
        return f"Fireworks live ({selected})"
    if provider == "openai_compatible_future_boundary":
        return "AMD/vLLM-compatible boundary (no live call)"
    return "deterministic mock (offline)"


def _short_question(question: Any, limit: int = 86) -> str:
    text = " ".join(str(question or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def render_console_summary(report: dict[str, Any], verbose_level: int = 0) -> str:
    verbose_level = clamp_verbose(verbose_level)
    summary = report.get("answer_summary", {})
    safety = report.get("safety", {})
    boundary = report.get("model_boundary", {})
    transcript = list(report.get("transcript", []))
    answered = int(summary.get("answered") or 0)
    blocked = int(summary.get("refused") or 0)
    roles = [_role_title(str(role)) for role in summary.get("roles_covered", [])]
    external_actions = int(safety.get("assistant_external_dispatches_attempted") or 0) + int(
        safety.get("assistant_external_messages_attempted") or 0
    )

    lines: list[str] = [
        f"ReliefQueue evidence assistant: {status_text(report.get('status'))}",
        f"Profile: {report.get('profile')}",
        f"Provider: {_provider_label(boundary)}",
        "Outputs:",
        f"- report: {REPORT_RELATIVE_DIR / REPORT_NAME}",
        f"- transcript: {REPORT_RELATIVE_DIR / TRANSCRIPT_NAME}",
        f"- context: {REPORT_RELATIVE_DIR / CONTEXT_NAME}",
        "Decision support:",
        f"- evidence answers ready: {answered}",
        f"- unsafe action checks blocked as expected: {blocked}",
        "Safety:",
        f"- human review required: {true_false(safety.get('human_review_required'))}",
        f"- auto-dispatch enabled: {true_false(safety.get('auto_dispatch_enabled'))}",
        f"- assistant external actions taken: {external_actions}",
    ]

    if verbose_level >= 1:
        section(lines, "Role coverage")
        bullet(lines, ", ".join(roles) if roles else "not available")
        section(lines, "Guardrail result")
        bullet(lines, "expected negative case passed: dispatch/message/mutation requests are blocked before any external action")

    if verbose_level >= 2:
        section(lines, "Question preview")
        for item in transcript:
            if item.get("expected_negative_case") is True:
                bullet(lines, f"Guardrail check: blocked as expected — {short_text(item.get('question'), 96)}")
            else:
                role = _role_title(str(item.get("role") or "unknown"))
                bullet(lines, f"{role}: answered — {short_text(item.get('question'), 96)}")

    if verbose_level >= 3:
        section(lines, "Model boundary")
        endpoint = boundary.get("endpoint", {}) if isinstance(boundary.get("endpoint"), dict) else {}
        key_value(lines, "mode", boundary.get("mode"))
        key_value(lines, "provider", boundary.get("provider"))
        key_value(lines, "endpoint configured", true_false(endpoint.get("configured")))
        key_value(lines, "endpoint host", endpoint.get("host") or "not configured")
        key_value(lines, "external call attempted", true_false(boundary.get("external_call_attempted")))
        key_value(lines, "successful model calls", boundary.get("successful_call_count"))
        if boundary.get("model_attempts"):
            bullet(lines, "model attempts:")
            for attempt in boundary.get("model_attempts", []):
                status = status_text(attempt.get("status"))
                model = attempt.get("model")
                suffix = ""
                if attempt.get("http_status"):
                    suffix = f" (HTTP {attempt.get('http_status')})"
                bullet(lines, f"{status}: {model}{suffix}", indent=1)
        section(lines, "Safety counters")
        for key in sorted(safety):
            key_value(lines, key, safety[key])

    if verbose_level >= 4:
        full_json_section(lines, "Full captured assistant report JSON", report)

    return "\n".join(lines)

def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the phase-02-09 ReliefQueue evidence assistant over latest reports.")
    parser.add_argument("--profile", default=os.environ.get("PROFILE", "urban_flood"), help="Disaster profile used if source reports are refreshed.")
    parser.add_argument(
        "--refresh-dashboard",
        action="store_true",
        default=os.environ.get("REFRESH_DASHBOARD", "0") in {"1", "true", "TRUE", "yes", "YES"},
        help="Refresh the phase-02-08 dashboard and its source reports before building the assistant transcript.",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help=verbosity_help())
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    verbose_level = clamp_verbose(args.verbose)
    report = build_evidence_assistant_report(
        profile_name=args.profile,
        repo_root=Path.cwd(),
        verbose_level=verbose_level,
        refresh_dashboard=bool(args.refresh_dashboard),
    )
    print(render_console_summary(report, verbose_level=verbose_level))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Historical AMD/vLLM evidence and current runtime-status separation.

This module deliberately keeps a frozen, submission-safe evidence campaign
separate from current deployment configuration and current-request outcomes.
It performs no network calls and never returns credentials or the configured
provider base URL.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAMPAIGN_PATH = ROOT / "fixtures" / "amd_evidence_campaign_v1.json"

_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "bearer",
    "password",
    "private_key",
    "secret",
    "token_value",
)


class AmdEvidenceError(ValueError):
    """Raised when the frozen evidence campaign is internally inconsistent."""


def load_amd_evidence_campaign(path: Path | None = None) -> dict[str, Any]:
    campaign_path = Path(path or DEFAULT_CAMPAIGN_PATH)
    try:
        data = json.loads(campaign_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AmdEvidenceError(f"AMD evidence campaign not found: {campaign_path}") from exc
    except json.JSONDecodeError as exc:
        raise AmdEvidenceError(f"AMD evidence campaign is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AmdEvidenceError("AMD evidence campaign must be a JSON object")
    validate_amd_evidence_campaign(data)
    return data


def validate_amd_evidence_campaign(data: dict[str, Any]) -> None:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(data.get("schema_version") == "reliefqueue-amd-evidence/v1", "schema_version must be reliefqueue-amd-evidence/v1")
    require(data.get("evidence_scope") == "historical_verified_campaign", "evidence_scope must be historical_verified_campaign")
    require(data.get("campaign_type") == "staged_composite", "campaign_type must be staged_composite")
    require(data.get("uniform_prompt_run") is False, "uniform_prompt_run must be false")
    require(data.get("direct_vllm_endpoint_only") is True, "direct_vllm_endpoint_only must be true")
    require(data.get("application_fallback_exercised") is False, "application_fallback_exercised must be false")

    quality = data.get("final_resolved_quality") or {}
    require(quality.get("cases_evaluated") == 24, "cases_evaluated must be 24")
    require(quality.get("cases_resolved") == 24, "cases_resolved must be 24")
    require(quality.get("overall_pass_rate_pct") == 100.0, "overall pass rate must be 100.0")
    require(quality.get("normalized_json_rate_pct") == 100.0, "normalized JSON rate must be 100.0")
    require(quality.get("nonce_binding_rate_pct") == 100.0, "nonce binding rate must be 100.0")
    require(quality.get("source_coverage_rate_pct") == 100.0, "source coverage rate must be 100.0")
    require(quality.get("review_required_output_count") == 24, "all 24 outputs must remain review-required")
    require(quality.get("provider_error_count") == 0, "provider error count must be zero")
    require(quality.get("fallback_count") == 0, "fallback count must be zero for the direct endpoint campaign")

    case_mix = data.get("case_mix") or {}
    require(case_mix == {"single_report": 8, "complex_dossier": 8, "adversarial": 8}, "case mix must be 8 single, 8 dossier and 8 adversarial")

    cases = data.get("cases") or []
    require(isinstance(cases, list) and len(cases) == 24, "cases must contain exactly 24 rows")
    ids = [row.get("case_id") for row in cases if isinstance(row, dict)]
    require(len(ids) == 24 and len(set(ids)) == 24 and all(ids), "case IDs must be present and unique")
    require(all(row.get("overall_pass") is True for row in cases if isinstance(row, dict)), "every selected case must pass")
    require(all(row.get("normalized_json_valid") is True for row in cases if isinstance(row, dict)), "every selected case must have normalized JSON")
    require(all(row.get("nonce_bound") is True for row in cases if isinstance(row, dict)), "every selected case must be nonce-bound")
    require(all(row.get("source_coverage_passed") is True for row in cases if isinstance(row, dict)), "every selected case must pass source coverage")
    require(all(row.get("review_required") is True for row in cases if isinstance(row, dict)), "every selected case must require human review")
    require(all(row.get("finish_reason") == "stop" for row in cases if isinstance(row, dict)), "every selected case must finish with stop")

    strict_count = sum(1 for row in cases if isinstance(row, dict) and row.get("strict_raw_json_valid") is True)
    strict_rate = round(100.0 * strict_count / 24, 2) if len(cases) == 24 else None
    require(strict_rate == quality.get("strict_raw_json_rate_pct"), "strict raw JSON rate does not match case rows")
    anomaly_ids = sorted(row.get("case_id") for row in cases if isinstance(row, dict) and row.get("strict_raw_json_valid") is False)
    require(anomaly_ids == sorted(quality.get("strict_raw_json_anomaly_case_ids") or []), "strict raw JSON anomaly IDs do not match case rows")

    stages = data.get("campaign_stages") or []
    stage_names = {stage.get("stage") for stage in stages if isinstance(stage, dict)}
    require({"a1_baseline_and_load", "a2_calibration", "a3_semantic_repair", "a4_final_closure"}.issubset(stage_names), "all four campaign stages must be present")

    limitations = " ".join(str(item).lower() for item in data.get("limitations") or [])
    require("staged composite" in limitations, "limitations must disclose staged composite evidence")
    require("fallback" in limitations and "not invoked" in limitations, "limitations must disclose that application fallback was not invoked")
    require("review-required" in limitations, "limitations must preserve human review wording")
    require("strict raw json" in limitations, "limitations must distinguish strict raw JSON from normalized JSON")

    secret_paths = list(_secret_like_paths(data))
    require(not secret_paths, f"public evidence contains secret-like keys: {', '.join(secret_paths)}")

    if errors:
        raise AmdEvidenceError("; ".join(errors))


def public_amd_evidence_payload(path: Path | None = None) -> dict[str, Any]:
    """Return the validated frozen campaign with an explicit historical label."""

    campaign = deepcopy(load_amd_evidence_campaign(path))
    return {
        "status": "ok",
        "historical_evidence": campaign,
        "truthfulness": {
            "current_live_status_inferred": False,
            "uniform_prompt_run": False,
            "application_fallback_exercised": False,
            "human_review_required": True,
        },
    }


def current_amd_runtime_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return configuration-only status without contacting the provider.

    A configured endpoint is not presented as a verified live request. Secrets
    and the private provider URL are intentionally omitted.
    """

    values = dict(os.environ if env is None else env)
    mode = values.get("AI_MODE", "mock")
    configured = mode == "openai_compatible" and all(
        values.get(name)
        for name in ("OPENAI_COMPAT_BASE_URL", "OPENAI_COMPAT_API_KEY", "OPENAI_COMPAT_MODEL")
    )
    return {
        "status": "configured_not_live_verified" if configured else "not_configured",
        "configured": configured,
        "live_request_verified": False,
        "provider": values.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud",
        "accelerator": values.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X",
        "runtime": values.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0",
        "served_model": values.get("OPENAI_COMPAT_MODEL") if configured else None,
        "underlying_model": values.get("OPENAI_COMPAT_UNDERLYING_MODEL") if configured else None,
        "endpoint_present": bool(values.get("OPENAI_COMPAT_BASE_URL")),
        "api_key_present": bool(values.get("OPENAI_COMPAT_API_KEY")),
        "human_review_required": True,
        "fallback_available": True,
        "note": "Configuration status only. Run a nonce-bound live verification request to establish current live status.",
    }


def amd_capability_payload(path: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return three distinct planes for API and UI consumers."""

    return {
        "status": "ok",
        "historical_evidence": load_amd_evidence_campaign(path),
        "live_runtime": current_amd_runtime_status(env),
        "current_request": {
            "attempted": False,
            "verified_live": False,
            "fallback_used": None,
            "provider_error": None,
            "note": "Current-request fields are populated by POST /api/ai/live-verification, not by this read-only endpoint.",
        },
    }


def _secret_like_paths(value: Any, prefix: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            child_path = f"{prefix}.{key}"
            if any(fragment in key_text for fragment in _SECRET_KEY_FRAGMENTS):
                findings.append(child_path)
            findings.extend(_secret_like_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_like_paths(child, f"{prefix}[{index}]"))
    return findings

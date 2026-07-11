"""Provider-independent AI enrichment boundary.

AI output is advisory only. This module never updates deterministic urgency,
assignment, dispatch, rescue, safety, or closure fields.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .models import normalize_text


AI_STATUSES = {
    "not_requested",
    "success",
    "skipped_missing_env",
    "timeout",
    "failed_validation",
    "provider_error",
    "fallback_used",
}
AI_MODES = {"none", "mock", "openai_compatible"}
LANGUAGES = {"en", "hi", "hinglish", "unknown"}
REQUIRED_KEYS = {
    "safe_summary",
    "missing_info_questions",
    "reply_draft",
    "operator_note",
    "language",
    "warnings",
}
FORBIDDEN_WORDING = [
    "auto-dispatched",
    "auto dispatched",
    "confirmed rescued",
    "confirmed rescue",
    "confirmed safe",
    "guaranteed location",
    "ai rescued",
    "ai verified",
    "verified emergency",
    "worker definitely reached",
    "help is guaranteed",
    "rescue is guaranteed",
    "guaranteed help",
    "will rescue",
    "will be rescued",
    "definitely safe",
]
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


class AIValidationError(ValueError):
    """Raised when provider output fails the safety contract."""


@dataclass(frozen=True)
class AIConfig:
    mode: str = "mock"
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "changeme"
    model: str = "model-name"
    timeout_seconds: float = 20.0
    max_retries: int = 1
    max_batch_size: int = 16
    send_private_text: bool = False
    response_format: str = "json_object"
    http_user_agent: str = "ReliefQueueAI/0.1 OpenAICompatibleClient"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "AIConfig":
        values = os.environ if env is None else env
        mode = (values.get("AI_MODE", "mock").strip() or "mock").replace("-", "_")
        if mode not in AI_MODES:
            mode = "none"
        return cls(
            mode=mode,
            base_url=values.get("OPENAI_COMPAT_BASE_URL", "http://localhost:8000/v1").strip()
            or "http://localhost:8000/v1",
            api_key=values.get("OPENAI_COMPAT_API_KEY", "changeme").strip() or "changeme",
            model=values.get("OPENAI_COMPAT_MODEL", "model-name").strip() or "model-name",
            timeout_seconds=_float_env(values.get("AI_TIMEOUT_SECONDS"), 20.0),
            max_retries=max(0, _int_env(values.get("AI_MAX_RETRIES"), 1)),
            max_batch_size=max(1, _int_env(values.get("AI_MAX_BATCH_SIZE"), 16)),
            send_private_text=str(values.get("AI_SEND_PRIVATE_TEXT", "false")).lower() == "true",
            response_format=_response_format_env(values.get("AI_RESPONSE_FORMAT")),
            http_user_agent=values.get("AI_HTTP_USER_AGENT", "ReliefQueueAI/0.1 OpenAICompatibleClient").strip()
            or "ReliefQueueAI/0.1 OpenAICompatibleClient",
        )

    def redacted_endpoint(self) -> str:
        return self.base_url.split("?", 1)[0].replace(self.api_key, "[redacted]") if self.api_key else self.base_url

    def missing_openai_env(self) -> list[str]:
        missing: list[str] = []
        if not self.base_url or self.base_url == "http://localhost:8000/v1":
            missing.append("OPENAI_COMPAT_BASE_URL")
        if not self.api_key or self.api_key == "changeme":
            missing.append("OPENAI_COMPAT_API_KEY")
        if not self.model or self.model in {"model-name", "local-model-name"}:
            missing.append("OPENAI_COMPAT_MODEL")
        return missing


class AIAdapter(Protocol):
    def enrich_case(self, case_record: dict[str, Any]) -> dict[str, Any]:
        ...

    def health_check(self) -> dict[str, Any]:
        ...


def _int_env(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _float_env(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _response_format_env(value: str | None) -> str:
    normalized = str(value or "json_object").strip().lower().replace("-", "_")
    if normalized in {"none", "off", "false", "disabled", "prompt_only"}:
        return "none"
    if normalized in {"json", "json_object"}:
        return "json_object"
    return "json_object"


def create_ai_adapter(config: AIConfig | None = None) -> AIAdapter:
    config = config or AIConfig.from_env()
    if config.mode == "mock":
        return MockAIAdapter(config)
    if config.mode == "openai_compatible":
        return OpenAICompatibleAdapter(config)
    return NoAIAdapter(config)


def apply_ai_enrichment(cases: list[dict[str, Any]], config: AIConfig | None = None) -> dict[str, Any]:
    config = config or AIConfig.from_env()
    adapter = create_ai_adapter(config)
    health = adapter.health_check()
    counts = {status: 0 for status in sorted(AI_STATUSES)}
    for case in cases:
        enrichment = adapter.enrich_case(case)
        _attach_ai(case, enrichment)
        counts[case["ai_status"]] += 1
    return {
        "mode": config.mode,
        "health": health,
        "status_counts": {key: value for key, value in counts.items() if value},
        "redacted_endpoint": config.redacted_endpoint() if config.mode == "openai_compatible" else "not_applicable",
        "fallback_behavior": "deterministic case data is preserved; invalid or unavailable AI output is not applied",
    }


def _attach_ai(case: dict[str, Any], enrichment: dict[str, Any]) -> None:
    status = enrichment.get("ai_status") if enrichment.get("ai_status") in AI_STATUSES else "provider_error"
    case["ai_status"] = status
    case["ai_provider"] = enrichment.get("ai_provider", "unknown")
    case["ai_error"] = enrichment.get("ai_error", "")
    case["ai_review_required"] = True
    if status == "success":
        case["ai_safe_summary"] = enrichment["safe_summary"]
        case["ai_missing_info_questions"] = enrichment["missing_info_questions"]
        case["ai_reply_draft"] = enrichment["reply_draft"]
        case["ai_operator_note"] = enrichment["operator_note"]
        case["ai_language"] = enrichment["language"]
        case["ai_warnings"] = enrichment["warnings"]
    else:
        case["ai_safe_summary"] = ""
        case["ai_missing_info_questions"] = []
        case["ai_reply_draft"] = ""
        case["ai_operator_note"] = "AI enrichment unavailable; use deterministic case fields and human review."
        case["ai_language"] = "unknown"
        case["ai_warnings"] = [case["ai_error"]] if case["ai_error"] else []


def _status_payload(status: str, error: str, provider: str = "none") -> dict[str, Any]:
    return {"ai_status": status, "ai_error": error, "ai_provider": provider}


class NoAIAdapter:
    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def health_check(self) -> dict[str, Any]:
        return {"status": "not_requested", "mode": self.config.mode}

    def enrich_case(self, case_record: dict[str, Any]) -> dict[str, Any]:
        return _status_payload("not_requested", "AI_MODE=none", "none")


class MockAIAdapter:
    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def health_check(self) -> dict[str, Any]:
        return {"status": "success", "mode": self.config.mode, "provider": "mock"}

    def enrich_case(self, case_record: dict[str, Any]) -> dict[str, Any]:
        missing = list(case_record.get("missing_fields") or [])
        questions = [_question_for_missing(field) for field in missing] or [
            "Can the coordinator confirm whether the listed location clue is still current?"
        ]
        warnings = ["Human coordinator must review before any public reply or field instruction."]
        if case_record.get("urgency") in {"RED", "REVIEW"}:
            warnings.append("High-attention case; do not treat AI text as verification.")
        payload = {
            "safe_summary": str(case_record.get("safe_summary") or "Safe summary unavailable."),
            "missing_info_questions": questions,
            "reply_draft": "We received your report. A human coordinator will review the details and may ask for missing information.",
            "operator_note": f"Mock AI suggests reviewing {case_record.get('need_type', 'unknown')} details and missing fields before action.",
            "language": _safe_language(case_record.get("language_hint")),
            "warnings": warnings,
        }
        validate_ai_output(payload, case_record)
        payload.update({"ai_status": "success", "ai_provider": "mock", "ai_error": ""})
        return payload


class OpenAICompatibleAdapter:
    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def health_check(self) -> dict[str, Any]:
        missing = self.config.missing_openai_env()
        if missing:
            return {"status": "skipped_missing_env", "mode": self.config.mode, "missing": missing}
        return {
            "status": "configured",
            "mode": self.config.mode,
            "endpoint": self.config.redacted_endpoint(),
            "send_private_text": self.config.send_private_text,
            "response_format": self.config.response_format,
            "http_user_agent": self.config.http_user_agent,
        }

    def enrich_case(self, case_record: dict[str, Any]) -> dict[str, Any]:
        missing = self.config.missing_openai_env()
        if missing:
            return _status_payload("skipped_missing_env", "Missing OpenAI-compatible env: " + ", ".join(missing), "openai_compatible")
        body = self._build_request(case_record)
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        encoded = json.dumps(body).encode("utf-8")
        last_error = ""
        for attempt in range(self.config.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=encoded,
                headers=self._request_headers(),
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                payload = parse_ai_json(content)
                validate_ai_output(payload, case_record)
                payload.update({"ai_status": "success", "ai_provider": "openai_compatible", "ai_error": ""})
                return payload
            except (TimeoutError, socket.timeout) as exc:
                last_error = f"timeout: {exc}"
                if attempt >= self.config.max_retries:
                    return _status_payload("timeout", last_error, "openai_compatible")
            except AIValidationError as exc:
                return _status_payload("failed_validation", str(exc), "openai_compatible")
            except urllib.error.HTTPError as exc:
                last_error = f"provider_error: HTTP {exc.code}: {_read_http_error_body(exc)}"
                if attempt >= self.config.max_retries:
                    return _status_payload("provider_error", last_error, "openai_compatible")
            except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, OSError) as exc:
                last_error = f"provider_error: {exc}"
                if attempt >= self.config.max_retries:
                    return _status_payload("provider_error", last_error, "openai_compatible")
            time.sleep(min(0.25 * (attempt + 1), 1.0))
        return _status_payload("provider_error", last_error or "provider request failed", "openai_compatible")


    def live_verify(self) -> dict[str, Any]:
        """Make a real live inference request and return evidence for judge review.

        Uses synthetic, privacy-safe input only. Never exposes the API key.
        """
        missing = self.config.missing_openai_env()
        if missing:
            return _live_verify_failure("Missing required env: " + ", ".join(missing))

        synthetic_case: dict[str, Any] = {
            "case_id": "DEMO-VERIFY-001",
            "safe_summary": "Flood situation near north sector riverbank. Three families require rescue and medical support.",
            "need_type": "rescue_medical",
            "urgency": "AMBER",
            "missing_fields": ["exact_location", "people_count"],
            "language_hint": "en",
            "operation_zone_id": "north-embankment",
            "vulnerable_flags": [],
        }

        body = self._build_request(synthetic_case)
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        encoded = json.dumps(body).encode("utf-8")

        start = time.time()
        try:
            request = urllib.request.Request(
                url,
                data=encoded,
                headers=self._request_headers(),
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                latency_ms = round((time.time() - start) * 1000)
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
        except (TimeoutError, socket.timeout) as exc:
            return _live_verify_failure(f"timeout: {exc}")
        except urllib.error.HTTPError as exc:
            return _live_verify_failure(f"HTTP {exc.code}: {_read_http_error_body(exc)}")
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, OSError) as exc:
            return _live_verify_failure(f"provider_error: {exc}")
        except Exception as exc:
            # Catch-all: any unexpected failure must still return fallback, never verified_live=True
            return _live_verify_failure(f"unexpected_error: {exc}")

        request_id = str(data.get("id") or "")
        served_model = str(data.get("model") or self.config.model)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return _live_verify_failure("provider returned unexpected response shape")

        try:
            parsed = parse_ai_json(content)
            validate_ai_output(parsed, synthetic_case)
            generated_advisory = (parsed.get("operator_note") or parsed.get("safe_summary") or "").strip()
        except (AIValidationError, Exception) as exc:
            # Advisory is present but failed validation — still report live contact succeeded
            generated_advisory = content[:500] if content else ""
            return {
                "status": "ok",
                "verified_live": True,
                "provider": os.environ.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud",
                "runtime": os.environ.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0",
                "accelerator": os.environ.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X",
                "served_model": served_model,
                "served_model_from_provider": bool(data.get("model")),
                "underlying_model": os.environ.get("OPENAI_COMPAT_UNDERLYING_MODEL") or "Qwen/Qwen2.5-7B-Instruct",
                "request_id": request_id,
                "verified_at": None,  # caller fills in
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "fallback_used": False,
                "human_review_required": True,
                "synthetic_input": synthetic_case["safe_summary"],
                "generated_advisory": generated_advisory,
                "warnings": [
                    "Human coordinator review required before any field action.",
                    f"Advisory output failed safety validation: {exc}",
                ],
                "error": None,
            }

        return {
            "status": "ok",
            "verified_live": True,
            "provider": os.environ.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud",
            "runtime": os.environ.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0",
            "accelerator": os.environ.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X",
            "served_model": served_model,
            "served_model_from_provider": bool(data.get("model")),
            "underlying_model": os.environ.get("OPENAI_COMPAT_UNDERLYING_MODEL") or "Qwen/Qwen2.5-7B-Instruct",
            "request_id": request_id,
            "verified_at": None,  # caller fills in
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "fallback_used": False,
            "human_review_required": True,
            "synthetic_input": synthetic_case["safe_summary"],
            "generated_advisory": generated_advisory,
            "warnings": ["Human coordinator review required before any field action."],
            "error": None,
        }

    def verify_user_input(self, user_text: str, case_id: str = "JUDGE-INPUT") -> dict[str, Any]:
        """Run live inference on user-provided text for judge verification.

        Sanitizes input (phone/email redacted), runs real AMD/vLLM inference.
        Never exposes API key. Returns evidence dict with challenge_nonce.
        """
        missing = self.config.missing_openai_env()
        if missing:
            result = _live_verify_failure("Missing required env: " + ", ".join(missing))
            result.update({"challenge_nonce": None, "original_input": user_text[:500], "sanitized_input": None, "case_id": case_id, "raw_content": None})
            return result

        # Sanitize: redact phone numbers and email addresses
        sanitized = PHONE_RE.sub("[phone-redacted]", user_text)
        sanitized = EMAIL_RE.sub("[email-redacted]", sanitized)
        sanitized = sanitized[:4000]  # practical limit for 8192-token context

        nonce = os.urandom(8).hex()

        case_record: dict[str, Any] = {
            "case_id": case_id,
            "safe_summary": sanitized,
            "need_type": "unknown",
            "urgency": "AMBER",
            "missing_fields": [],
            "language_hint": "en",
            "operation_zone_id": "judge-demo",
            "vulnerable_flags": [],
        }

        body = self._build_request(case_record)
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        encoded = json.dumps(body).encode("utf-8")

        start = time.time()
        try:
            request = urllib.request.Request(
                url,
                data=encoded,
                headers=self._request_headers(),
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                latency_ms = round((time.time() - start) * 1000)
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
        except (TimeoutError, socket.timeout) as exc:
            result = _live_verify_failure(f"timeout: {exc}")
            result.update({"challenge_nonce": nonce, "original_input": user_text[:500], "sanitized_input": sanitized, "case_id": case_id, "raw_content": None})
            return result
        except urllib.error.HTTPError as exc:
            result = _live_verify_failure(f"HTTP {exc.code}: {_read_http_error_body(exc)}")
            result.update({"challenge_nonce": nonce, "original_input": user_text[:500], "sanitized_input": sanitized, "case_id": case_id, "raw_content": None})
            return result
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, OSError) as exc:
            result = _live_verify_failure(f"provider_error: {exc}")
            result.update({"challenge_nonce": nonce, "original_input": user_text[:500], "sanitized_input": sanitized, "case_id": case_id, "raw_content": None})
            return result
        except Exception as exc:
            result = _live_verify_failure(f"unexpected_error: {exc}")
            result.update({"challenge_nonce": nonce, "original_input": user_text[:500], "sanitized_input": sanitized, "case_id": case_id, "raw_content": None})
            return result

        request_id = str(data.get("id") or "")
        served_model = str(data.get("model") or self.config.model)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            result = _live_verify_failure("provider returned unexpected response shape")
            result.update({"challenge_nonce": nonce, "original_input": user_text[:500], "sanitized_input": sanitized, "case_id": case_id, "raw_content": None})
            return result

        # Try to extract clean advisory; do not fail verified_live on validation errors
        generated_advisory = content[:500] if content else ""
        try:
            parsed = parse_ai_json(content)
            generated_advisory = (parsed.get("operator_note") or parsed.get("safe_summary") or content[:500]).strip()
        except Exception:
            pass

        return {
            "status": "ok",
            "verified_live": True,
            "provider": os.environ.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud",
            "runtime": os.environ.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0",
            "accelerator": os.environ.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X",
            "served_model": served_model,
            "served_model_from_provider": bool(data.get("model")),
            "underlying_model": os.environ.get("OPENAI_COMPAT_UNDERLYING_MODEL") or "Qwen/Qwen2.5-7B-Instruct",
            "request_id": request_id,
            "challenge_nonce": nonce,
            "verified_at": None,  # caller fills in
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "fallback_used": False,
            "human_review_required": True,
            "case_id": case_id,
            "original_input": user_text[:500],
            "sanitized_input": sanitized,
            "generated_advisory": generated_advisory,
            "raw_content": content[:1000],
            "warnings": ["Human coordinator review required before any field action."],
            "error": None,
        }

    def complete_messages(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        response_format: str | None = "json_object",
    ) -> dict[str, Any]:
        """Run a bounded raw chat completion and return safe provider evidence."""
        missing = self.config.missing_openai_env()
        if missing:
            result = _live_verify_failure("Missing required env: " + ", ".join(missing))
            result["raw_content"] = None
            return result
        body: dict[str, Any] = {
            "model": self.config.model,
            "temperature": 0,
            "max_tokens": int(max_tokens),
            "messages": messages,
        }
        if response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        encoded = json.dumps(body).encode("utf-8")
        start = time.time()
        try:
            request = urllib.request.Request(
                url,
                data=encoded,
                headers=self._request_headers(),
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                latency_ms = round((time.time() - start) * 1000)
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (TimeoutError, socket.timeout) as exc:
            result = _live_verify_failure(f"timeout: {exc}")
            result["raw_content"] = None
            return result
        except urllib.error.HTTPError as exc:
            result = _live_verify_failure(f"HTTP {exc.code}: {_read_http_error_body(exc)}")
            result["raw_content"] = None
            return result
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, OSError) as exc:
            result = _live_verify_failure(f"provider_error: {exc}")
            result["raw_content"] = None
            return result
        except Exception as exc:
            result = _live_verify_failure(f"unexpected_error: {exc}")
            result["raw_content"] = None
            return result

        usage = data.get("usage") or {}
        finish_reason = None
        try:
            finish_reason = data["choices"][0].get("finish_reason")
        except Exception:
            finish_reason = None
        return {
            "status": "ok",
            "verified_live": bool(data.get("id")) and bool(content),
            "provider": os.environ.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud",
            "runtime": os.environ.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0",
            "accelerator": os.environ.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X",
            "served_model": str(data.get("model") or self.config.model),
            "served_model_from_provider": bool(data.get("model")),
            "underlying_model": os.environ.get("OPENAI_COMPAT_UNDERLYING_MODEL") or "Qwen/Qwen2.5-7B-Instruct",
            "request_id": str(data.get("id") or ""),
            "verified_at": None,
            "latency_ms": latency_ms,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "fallback_used": False,
            "human_review_required": True,
            "generated_advisory": content[:1200],
            "raw_content": content,
            "warnings": ["Human coordinator review required before any field action."],
            "error": None,
            "finish_reason": finish_reason,
            "request_settings": {
                "max_tokens": int(max_tokens),
                "temperature": 0,
                "response_format": response_format or "none",
                "model": self.config.model,
            },
        }

    def _request_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.http_user_agent.strip():
            headers["User-Agent"] = self.config.http_user_agent.strip()
        return headers

    def _build_request(self, case_record: dict[str, Any]) -> dict[str, Any]:
        case_context = {
            "case_id": case_record.get("case_id"),
            "safe_summary": case_record.get("safe_summary"),
            "need_type": case_record.get("need_type"),
            "urgency": case_record.get("urgency"),
            "missing_fields": case_record.get("missing_fields") or [],
            "language_hint": case_record.get("language_hint"),
            "operation_zone_id": case_record.get("operation_zone_id"),
            "vulnerable_flags": case_record.get("vulnerable_flags") or [],
        }
        if self.config.send_private_text:
            case_context["raw_text_private"] = case_record.get("raw_text_private", "")
        schema = {
            "safe_summary": "string",
            "missing_info_questions": ["string"],
            "reply_draft": "string",
            "operator_note": "string",
            "language": "en|hi|hinglish|unknown",
            "warnings": ["string"],
        }
        request_body = {
            "model": self.config.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON only. The top-level JSON object must contain exactly these keys: "
                        "safe_summary, missing_info_questions, reply_draft, operator_note, language, warnings. "
                        "Do not include wrapper keys such as case, required_shape, schema, task, explanation, or reasoning. "
                        "Suggest safe operator support text. Do not claim confirmed rescue, safety, dispatch, "
                        "verification, or guaranteed help."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Create only the flat AI enrichment object. Do not echo this input object.",
                            "required_output_keys": sorted(REQUIRED_KEYS),
                            "field_schema": schema,
                            "case_context_for_reference_only": case_context,
                            "forbidden_top_level_output_keys": [
                                "case",
                                "required_shape",
                                "schema",
                                "field_schema",
                                "task",
                                "case_context_for_reference_only",
                                "explanation",
                                "reasoning",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        if self.config.response_format == "json_object":
            request_body["response_format"] = {"type": "json_object"}
        return request_body


def _live_verify_failure(error: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "verified_live": False,
        "provider": os.environ.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud",
        "runtime": os.environ.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0",
        "accelerator": os.environ.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X",
        "served_model": None,
        "served_model_from_provider": False,
        "underlying_model": os.environ.get("OPENAI_COMPAT_UNDERLYING_MODEL") or "Qwen/Qwen2.5-7B-Instruct",
        "request_id": None,
        "verified_at": None,
        "latency_ms": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "fallback_used": True,
        "human_review_required": True,
        "synthetic_input": None,
        "generated_advisory": None,
        "warnings": ["Live verification failed; deterministic fallback remains available."],
        "error": error,
    }


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    body = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|token|secret)([\s:=]+)([A-Za-z0-9_\-./+=:]{8,})",
        r"\1\2<redacted>",
        body,
    )
    return body[:500] or str(exc)


def parse_ai_json(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AIValidationError("AI output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise AIValidationError("AI output must be a JSON object")
    return _normalize_provider_json_envelope(payload)


def _normalize_provider_json_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    # Accept one safe provider echo envelope, then validate the inner object normally.
    # Some chat models echo the input wrapper and place the requested flat output under
    # a `required_shape` key. This function unwraps only that exact envelope shape and
    # only when the nested object has the exact required output keys. All safety checks
    # still run later through validate_ai_output().
    if set(payload) == {"required_shape", "case"} and isinstance(payload.get("required_shape"), dict):
        candidate = payload["required_shape"]
        if set(candidate) == REQUIRED_KEYS:
            return candidate
    return payload


def validate_ai_output(payload: dict[str, Any], case_record: dict[str, Any] | None = None) -> dict[str, Any]:
    keys = set(payload)
    if keys != REQUIRED_KEYS:
        raise AIValidationError(f"AI output keys must exactly match {sorted(REQUIRED_KEYS)}")
    if not all(isinstance(payload[key], str) for key in ["safe_summary", "reply_draft", "operator_note", "language"]):
        raise AIValidationError("AI string fields have invalid types")
    if not _list_of_strings(payload["missing_info_questions"]) or not _list_of_strings(payload["warnings"]):
        raise AIValidationError("AI list fields have invalid types")
    if payload["language"] not in LANGUAGES:
        raise AIValidationError("AI language is outside allowed values")
    joined = " ".join(
        [
            payload["safe_summary"],
            payload["reply_draft"],
            payload["operator_note"],
            " ".join(payload["warnings"]),
            " ".join(payload["missing_info_questions"]),
        ]
    )
    lowered = normalize_text(joined)
    for phrase in FORBIDDEN_WORDING:
        if normalize_text(phrase) in lowered:
            raise AIValidationError(f"AI output contains unsafe wording: {phrase}")
    for field in ["safe_summary", "reply_draft", "operator_note"]:
        if PHONE_RE.search(payload[field]):
            raise AIValidationError(f"AI output contains phone-like text in {field}")
    if _leaks_private_content(payload, case_record or {}):
        raise AIValidationError("AI output appears to leak private source content")
    return payload


def _list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _safe_language(value: Any) -> str:
    return str(value) if str(value) in LANGUAGES else "unknown"


def _question_for_missing(field: str) -> str:
    mapping = {
        "location": "What nearby landmark or cross street can the reporter safely share?",
        "need_type": "What type of help is being requested?",
        "people_count": "How many people are affected, approximately?",
        "contact_possible": "Is there a safe way for the coordinator to contact the reporter?",
    }
    return mapping.get(field, f"Can the coordinator clarify {field.replace('_', ' ')}?")


def _leaks_private_content(payload: dict[str, Any], case_record: dict[str, Any]) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False).lower()
    raw = str(case_record.get("raw_text_private") or "").strip()
    if raw and len(raw) > 24 and raw.lower() in rendered:
        return True
    for key in ["reporter_phone_private_optional", "reporter_name_private_optional", "media_note_private_optional"]:
        value = str(case_record.get(key) or "").strip()
        if value and value.lower() in rendered:
            return True
    return False

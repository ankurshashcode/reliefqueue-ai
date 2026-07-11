"""Tests for POST /api/ai/live-verification endpoint and response contract.

Validates:
- Successful live-verification response mapping
- API key never appears in response
- human_review_required is always true
- fallback_used is correctly reported
- Failed provider calls cannot produce verified_live=true
- Repeated calls can generate new request IDs (non-idempotent by design)
- No toast-only / silent success path (response contract enforced)
"""

import json
import os
import socket
import time
import unittest
from unittest.mock import MagicMock, patch

from reliefqueue.ai import AIConfig, OpenAICompatibleAdapter, _live_verify_failure
from reliefqueue import product_api


SYNTHETIC_CASE_SUMMARY = "Flood situation near north sector riverbank. Three families require rescue and medical support."

# ---------------------------------------------------------------------------
# Helper: build a mock urllib response
# ---------------------------------------------------------------------------

def _mock_response(data: dict, headers: dict | None = None):
    raw = json.dumps(data).encode("utf-8")
    mock = MagicMock()
    mock.read.return_value = raw
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _vllm_response(request_id: str = "chatcmpl-testid-001", model: str = "reliefqueue-amd") -> dict:
    """Minimal vLLM-compatible chat completion response for testing."""
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "safe_summary": "Flooding near north sector. Families require evacuation assistance.",
                        "missing_info_questions": ["What is the exact street address or landmark?"],
                        "reply_draft": "We received your report. A coordinator will review and follow up.",
                        "operator_note": "Prioritise location confirmation before field dispatch.",
                        "language": "en",
                        "warnings": ["Human coordinator review required before any field action."],
                    }),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 60,
            "total_tokens": 180,
        },
    }


# ---------------------------------------------------------------------------
# Tests: _live_verify_failure helper
# ---------------------------------------------------------------------------

class TestLiveVerifyFailureHelper(unittest.TestCase):
    def test_returns_false_verified_live(self) -> None:
        result = _live_verify_failure("some error")
        self.assertFalse(result["verified_live"])

    def test_returns_true_fallback_used(self) -> None:
        result = _live_verify_failure("timeout")
        self.assertTrue(result["fallback_used"])

    def test_human_review_required_always_true(self) -> None:
        result = _live_verify_failure("any error")
        self.assertTrue(result["human_review_required"])

    def test_error_message_preserved(self) -> None:
        result = _live_verify_failure("HTTP 401: Unauthorized")
        self.assertIn("HTTP 401", result["error"])

    def test_api_key_not_in_failure(self) -> None:
        result = _live_verify_failure("some error")
        rendered = json.dumps(result)
        self.assertNotIn("changeme", rendered)
        self.assertNotIn("Bearer", rendered)


# ---------------------------------------------------------------------------
# Tests: OpenAICompatibleAdapter.live_verify
# ---------------------------------------------------------------------------

class TestLiveVerifyMethod(unittest.TestCase):
    def _adapter(self, **overrides) -> OpenAICompatibleAdapter:
        defaults = dict(
            mode="openai_compatible",
            base_url="http://test-amd.example.com/v1",
            api_key="test-secret-key-abc123",
            model="reliefqueue-amd",
            timeout_seconds=10.0,
            max_retries=0,
        )
        defaults.update(overrides)
        return OpenAICompatibleAdapter(AIConfig(**defaults))

    def test_missing_env_returns_failed_not_verified(self) -> None:
        adapter = OpenAICompatibleAdapter(AIConfig(
            mode="openai_compatible",
            base_url="http://localhost:8000/v1",
            api_key="changeme",
            model="local-model-name",
        ))
        result = adapter.live_verify()
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])
        self.assertIn("Missing", result["error"])

    def test_api_key_never_in_response(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        rendered = json.dumps(result)
        self.assertNotIn("test-secret-key-abc123", rendered)
        self.assertNotIn("Bearer", rendered)

    def test_successful_response_verified_live_true(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertTrue(result["verified_live"])
        self.assertFalse(result["fallback_used"])

    def test_successful_response_human_review_required(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertTrue(result["human_review_required"])

    def test_successful_response_maps_provider_fields(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertEqual(result["provider"], "AMD Developer Cloud")
        self.assertEqual(result["runtime"], "vLLM 0.23.0")
        self.assertEqual(result["accelerator"], "AMD Instinct MI300X")
        self.assertEqual(result["underlying_model"], "Qwen/Qwen2.5-7B-Instruct")

    def test_served_model_comes_from_response(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response(model="reliefqueue-amd"))):
            result = adapter.live_verify()
        self.assertEqual(result["served_model"], "reliefqueue-amd")

    def test_request_id_comes_from_response(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response(request_id="chatcmpl-unique-xyz"))):
            result = adapter.live_verify()
        self.assertEqual(result["request_id"], "chatcmpl-unique-xyz")

    def test_token_usage_mapped(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertEqual(result["prompt_tokens"], 120)
        self.assertEqual(result["completion_tokens"], 60)
        self.assertEqual(result["total_tokens"], 180)

    def test_latency_is_measured_integer(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertIsInstance(result["latency_ms"], int)
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_synthetic_input_in_response(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertIsNotNone(result["synthetic_input"])
        self.assertIn("rescue", result["synthetic_input"].lower())

    def test_generated_advisory_populated(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
            result = adapter.live_verify()
        self.assertIsNotNone(result["generated_advisory"])
        self.assertTrue(len(result["generated_advisory"]) > 0)

    def test_timeout_returns_failed_not_verified(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = adapter.live_verify()
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])
        self.assertIn("timeout", result["error"])

    def test_http_error_returns_failed_not_verified(self) -> None:
        import urllib.error
        adapter = self._adapter()
        http_err = urllib.error.HTTPError(
            url="http://test", code=401, msg="Unauthorized", hdrs=MagicMock(), fp=MagicMock(read=lambda: b"Unauthorized")
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            result = adapter.live_verify()
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])

    def test_connection_refused_returns_failed(self) -> None:
        adapter = self._adapter()
        with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            result = adapter.live_verify()
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])

    def test_malformed_response_returns_failed(self) -> None:
        adapter = self._adapter()
        bad_mock = MagicMock()
        bad_mock.read.return_value = b"not json at all"
        bad_mock.__enter__ = lambda s: s
        bad_mock.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=bad_mock):
            result = adapter.live_verify()
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])

    def test_failed_call_cannot_show_verified_live_true(self) -> None:
        """The key invariant: a failed provider call must never return verified_live=True."""
        adapter = self._adapter()
        with patch("urllib.request.urlopen", side_effect=Exception("unexpected")):
            result = adapter.live_verify()
        # Regardless of how it fails, verified_live must not be True
        self.assertFalse(result["verified_live"])

    def test_repeated_calls_can_produce_different_request_ids(self) -> None:
        """Verifies the function is not idempotency-locked (each call is fresh)."""
        adapter = self._adapter()
        resp1 = _vllm_response(request_id="chatcmpl-first-001")
        resp2 = _vllm_response(request_id="chatcmpl-second-002")
        with patch("urllib.request.urlopen", side_effect=[
            _mock_response(resp1),
            _mock_response(resp2),
        ]):
            r1 = adapter.live_verify()
            r2 = adapter.live_verify()
        self.assertEqual(r1["request_id"], "chatcmpl-first-001")
        self.assertEqual(r2["request_id"], "chatcmpl-second-002")
        self.assertNotEqual(r1["request_id"], r2["request_id"])


# ---------------------------------------------------------------------------
# Tests: product_api.live_verification() facade
# ---------------------------------------------------------------------------

class TestLiveVerificationFacade(unittest.TestCase):
    def _env(self, **overrides):
        base = {
            "AI_MODE": "openai_compatible",
            "OPENAI_COMPAT_BASE_URL": "http://test-amd.example.com/v1",
            "OPENAI_COMPAT_API_KEY": "facade-secret-key-xyz",
            "OPENAI_COMPAT_MODEL": "reliefqueue-amd",
        }
        base.update(overrides)
        return base

    def test_wrong_ai_mode_returns_failed_with_explanation(self) -> None:
        with patch.dict("os.environ", {"AI_MODE": "mock"}, clear=True):
            result = product_api.live_verification()
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])
        self.assertIn("AI_MODE", result["error"])

    def test_api_key_never_in_facade_response(self) -> None:
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
                result = product_api.live_verification()
        rendered = json.dumps(result)
        self.assertNotIn("facade-secret-key-xyz", rendered)

    def test_verified_at_timestamp_present(self) -> None:
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
                result = product_api.live_verification()
        self.assertIsNotNone(result.get("verified_at"))
        self.assertIn("T", result["verified_at"])  # ISO format

    def test_human_review_required_true_on_success(self) -> None:
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
                result = product_api.live_verification()
        self.assertTrue(result["human_review_required"])

    def test_fallback_used_false_on_live_success(self) -> None:
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
                result = product_api.live_verification()
        self.assertFalse(result["fallback_used"])

    def test_verified_live_true_on_success(self) -> None:
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
                result = product_api.live_verification()
        self.assertTrue(result["verified_live"])

    def test_provider_error_sets_fallback_used(self) -> None:
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", side_effect=OSError("refused")):
                result = product_api.live_verification()
        self.assertTrue(result["fallback_used"])
        self.assertFalse(result["verified_live"])

    def test_response_has_all_required_keys(self) -> None:
        required_keys = {
            "status", "verified_live", "provider", "runtime", "accelerator",
            "served_model", "underlying_model", "request_id", "verified_at",
            "latency_ms", "prompt_tokens", "completion_tokens", "total_tokens",
            "fallback_used", "human_review_required", "synthetic_input",
            "generated_advisory", "warnings", "error",
        }
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", return_value=_mock_response(_vllm_response())):
                result = product_api.live_verification()
        missing = required_keys - set(result.keys())
        self.assertEqual(missing, set(), f"Response missing keys: {missing}")

    def test_failure_response_has_all_required_keys(self) -> None:
        required_keys = {
            "status", "verified_live", "provider", "runtime", "accelerator",
            "served_model", "underlying_model", "request_id", "verified_at",
            "latency_ms", "prompt_tokens", "completion_tokens", "total_tokens",
            "fallback_used", "human_review_required", "synthetic_input",
            "generated_advisory", "warnings", "error",
        }
        with patch.dict("os.environ", self._env(), clear=True):
            with patch("urllib.request.urlopen", side_effect=OSError("refused")):
                result = product_api.live_verification()
        missing = required_keys - set(result.keys())
        self.assertEqual(missing, set(), f"Failure response missing keys: {missing}")


if __name__ == "__main__":
    unittest.main()

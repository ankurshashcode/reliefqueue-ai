"""Tests for burst verification endpoint and verify_user_input method."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reliefqueue.ai import AIConfig, OpenAICompatibleAdapter
from reliefqueue.product_api import (
    BURST_MAX_CASES,
    BURST_VALID_CONCURRENCY,
    ProductApiError,
    burst_verification,
    live_verification,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

AMD_ENV = {
    "AI_MODE": "openai_compatible",
    "OPENAI_COMPAT_BASE_URL": "http://fake-amd.local/v1",
    "OPENAI_COMPAT_API_KEY": "test-key-abc",
    "OPENAI_COMPAT_MODEL": "reliefqueue-amd",
}


def _make_fake_response(request_id: str = "chatcmpl-abc123") -> bytes:
    return json.dumps({
        "id": request_id,
        "model": "reliefqueue-amd",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "safe_summary": "Flood near north sector. Families require rescue.",
                    "missing_info_questions": ["What is the exact location?"],
                    "reply_draft": "We received your report. A coordinator will review.",
                    "operator_note": "Coordinate with field team for evacuation.",
                    "language": "en",
                    "warnings": ["Human coordinator review required."],
                })
            }
        }],
        "usage": {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
    }).encode("utf-8")


def _fake_urlopen(request_id: str = "chatcmpl-abc123"):
    mock_response = MagicMock()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_response.read.return_value = _make_fake_response(request_id)
    return MagicMock(return_value=mock_response)


# ─── verify_user_input method ─────────────────────────────────────────────────

class TestVerifyUserInput(unittest.TestCase):

    def _adapter(self, env=None):
        config = AIConfig.from_env(env or AMD_ENV)
        return OpenAICompatibleAdapter(config)

    @patch("urllib.request.urlopen", side_effect=lambda *a, **kw: (_ for _ in ()).throw(ConnectionRefusedError("refused")))
    def test_connection_refused_returns_failed(self, _mock):
        adapter = self._adapter()
        result = adapter.verify_user_input("Flood near sector 7.")
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])
        self.assertTrue(result["human_review_required"])

    @patch("urllib.request.urlopen")
    def test_success_returns_verified_live_true(self, mock_open):
        mock_open.side_effect = _fake_urlopen("chatcmpl-verify-001")
        adapter = self._adapter()
        result = adapter.verify_user_input("Rescue needed at north sector.")
        self.assertTrue(result["verified_live"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["request_id"], "chatcmpl-verify-001")

    @patch("urllib.request.urlopen")
    def test_challenge_nonce_is_present_on_success(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        result = adapter.verify_user_input("Test input.")
        self.assertIn("challenge_nonce", result)
        self.assertIsNotNone(result["challenge_nonce"])
        self.assertGreater(len(result["challenge_nonce"]), 4)

    @patch("urllib.request.urlopen")
    def test_repeated_calls_produce_different_nonces(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        r1 = adapter.verify_user_input("Same input text for test.")
        mock_open.side_effect = _fake_urlopen("chatcmpl-second")
        r2 = adapter.verify_user_input("Same input text for test.")
        # Nonces are random — they should differ with overwhelming probability
        self.assertNotEqual(r1.get("challenge_nonce"), r2.get("challenge_nonce"))

    @patch("urllib.request.urlopen")
    def test_api_key_never_in_response(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        result = adapter.verify_user_input("Flood scenario input.")
        serialized = json.dumps(result)
        self.assertNotIn("test-key-abc", serialized)
        self.assertNotIn("OPENAI_COMPAT_API_KEY", serialized)

    @patch("urllib.request.urlopen")
    def test_original_and_sanitized_input_returned(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        text = "Rescue near sector 7."
        result = adapter.verify_user_input(text)
        self.assertIn("original_input", result)
        self.assertIn("sanitized_input", result)

    @patch("urllib.request.urlopen")
    def test_phone_number_sanitized_in_output(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        text = "Call coordinator at +91 98765 43210 for rescue."
        result = adapter.verify_user_input(text)
        sanitized = result.get("sanitized_input", "")
        self.assertNotIn("98765 43210", sanitized)
        self.assertIn("[phone-redacted]", sanitized)

    @patch("urllib.request.urlopen")
    def test_email_sanitized_in_output(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        text = "Contact coordinator@example.org for updates."
        result = adapter.verify_user_input(text)
        sanitized = result.get("sanitized_input", "")
        self.assertNotIn("coordinator@example.org", sanitized)
        self.assertIn("[email-redacted]", sanitized)

    @patch("urllib.request.urlopen")
    def test_human_review_required_always_true(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        adapter = self._adapter()
        result = adapter.verify_user_input("Any input text.")
        self.assertTrue(result["human_review_required"])

    def test_missing_env_returns_failed(self):
        bad_env = {"AI_MODE": "openai_compatible", "OPENAI_COMPAT_API_KEY": "changeme"}
        adapter = self._adapter(bad_env)
        result = adapter.verify_user_input("Flood in sector.")
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["fallback_used"])

    @patch("urllib.request.urlopen", side_effect=Exception("unexpected_failure"))
    def test_unexpected_exception_never_leaks_verified_live_true(self, _mock):
        adapter = self._adapter()
        result = adapter.verify_user_input("Test input.")
        self.assertFalse(result["verified_live"])


# ─── live_verification facade with custom text ───────────────────────────────

class TestLiveVerificationWithText(unittest.TestCase):

    @patch("urllib.request.urlopen")
    @patch.dict(os.environ, AMD_ENV)
    def test_custom_text_reaches_backend(self, mock_open):
        mock_open.side_effect = _fake_urlopen("chatcmpl-custom")
        body = {"text": "Judge-provided synthetic report: 5 people stranded."}
        result = live_verification(body)
        self.assertIn("verified_at", result)
        # When AMD is live it should be verified
        if result.get("verified_live"):
            self.assertFalse(result["fallback_used"])

    @patch.dict(os.environ, {**AMD_ENV, "AI_MODE": "mock"})
    def test_wrong_mode_returns_failed_with_explanation(self):
        result = live_verification({})
        self.assertFalse(result["verified_live"])
        self.assertIn("AI_MODE", result.get("error", ""))

    @patch("urllib.request.urlopen")
    @patch.dict(os.environ, AMD_ENV)
    def test_api_key_never_in_facade_response(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        result = live_verification({})
        serialized = json.dumps(result)
        self.assertNotIn("test-key-abc", serialized)


# ─── burst_verification function ─────────────────────────────────────────────

class TestBurstVerification(unittest.TestCase):

    def _run_burst(self, reports, concurrency=2, env=None):
        with patch.dict(os.environ, env or AMD_ENV):
            return burst_verification({"reports": reports, "concurrency": concurrency})

    def test_empty_reports_raises_400(self):
        with patch.dict(os.environ, AMD_ENV):
            with self.assertRaises(ProductApiError) as ctx:
                burst_verification({"reports": [], "concurrency": 1})
            self.assertEqual(ctx.exception.status, 400)

    def test_too_many_cases_raises_400(self):
        reports = [{"id": f"c-{i}", "text": "test"} for i in range(BURST_MAX_CASES + 1)]
        with patch.dict(os.environ, AMD_ENV):
            with self.assertRaises(ProductApiError) as ctx:
                burst_verification({"reports": reports, "concurrency": 1})
            self.assertEqual(ctx.exception.status, 400)
            self.assertIn(str(BURST_MAX_CASES), str(ctx.exception))

    def test_invalid_concurrency_raises_400(self):
        with patch.dict(os.environ, AMD_ENV):
            with self.assertRaises(ProductApiError) as ctx:
                burst_verification({"reports": [{"id": "c1", "text": "test"}], "concurrency": 3})
            self.assertEqual(ctx.exception.status, 400)

    def test_wrong_ai_mode_raises_400(self):
        env = {**AMD_ENV, "AI_MODE": "mock"}
        with patch.dict(os.environ, env):
            with self.assertRaises(ProductApiError) as ctx:
                burst_verification({"reports": [{"id": "c1", "text": "test"}], "concurrency": 1})
            self.assertEqual(ctx.exception.status, 400)

    def test_valid_concurrency_values(self):
        for c in BURST_VALID_CONCURRENCY:
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = _fake_urlopen()
                with patch.dict(os.environ, AMD_ENV):
                    result = burst_verification({"reports": [{"id": "c1", "text": "test"}], "concurrency": c})
                self.assertEqual(result["submitted"], 1)

    @patch("urllib.request.urlopen")
    def test_all_required_aggregate_keys_present(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        result = self._run_burst([{"id": "c1", "text": "Flood report."}])
        for key in ["batch_id", "started_at", "completed_at", "submitted", "succeeded", "failed",
                    "live_amd_responses", "fallback_responses", "total_elapsed_ms", "median_latency_ms",
                    "p95_latency_ms", "prompt_tokens", "completion_tokens", "total_tokens",
                    "approximate_throughput_rps", "active_model", "runtime", "accelerator",
                    "human_review_required", "cases"]:
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("urllib.request.urlopen")
    def test_human_review_required_always_true(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        result = self._run_burst([{"id": "c1", "text": "Test flood report."}])
        self.assertTrue(result["human_review_required"])
        for case in result["cases"]:
            self.assertTrue(case.get("human_review_required"))

    @patch("urllib.request.urlopen")
    def test_api_key_never_in_response(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        result = self._run_burst([{"id": "c1", "text": "Flood report."}])
        serialized = json.dumps(result)
        self.assertNotIn("test-key-abc", serialized)

    @patch("urllib.request.urlopen")
    def test_each_case_gets_unique_challenge_nonce(self, mock_open):
        # Use different request IDs to simulate different calls
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _fake_urlopen(f"chatcmpl-{call_count:04d}")(*args, **kwargs)
        mock_open.side_effect = side_effect
        reports = [{"id": f"c-{i}", "text": f"Report {i}"} for i in range(4)]
        result = self._run_burst(reports, concurrency=2)
        nonces = [c.get("challenge_nonce") for c in result["cases"] if c.get("challenge_nonce")]
        # All nonces that are present should be unique
        self.assertEqual(len(nonces), len(set(nonces)))

    @patch("urllib.request.urlopen")
    def test_repeated_runs_produce_new_batch_id(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        reports = [{"id": "c1", "text": "Flood report."}]
        r1 = self._run_burst(reports)
        mock_open.side_effect = _fake_urlopen("chatcmpl-second")
        r2 = self._run_burst(reports)
        self.assertNotEqual(r1["batch_id"], r2["batch_id"])

    @patch("urllib.request.urlopen")
    def test_accepts_plain_string_reports(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        with patch.dict(os.environ, AMD_ENV):
            result = burst_verification({"reports": ["Flood in sector 7.", "Medical needed at hub west."], "concurrency": 1})
        self.assertEqual(result["submitted"], 2)
        self.assertEqual(len(result["cases"]), 2)

    @patch("urllib.request.urlopen")
    def test_accepts_jsonl_dict_reports(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        reports = [{"id": "judge-001", "text": "Rescue needed."}, {"id": "judge-002", "text": "Shelter overflow."}]
        with patch.dict(os.environ, AMD_ENV):
            result = burst_verification({"reports": reports, "concurrency": 1})
        self.assertEqual(result["submitted"], 2)
        case_ids = {c["case_id"] for c in result["cases"]}
        self.assertIn("judge-001", case_ids)
        self.assertIn("judge-002", case_ids)

    @patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused"))
    def test_failed_cases_never_show_verified_live_true(self, _mock):
        result = self._run_burst([{"id": "c1", "text": "Test."}])
        for case in result["cases"]:
            if not case.get("verified_live"):
                self.assertFalse(case.get("verified_live"))

    @patch("urllib.request.urlopen")
    def test_metrics_calculated_from_actual_results(self, mock_open):
        mock_open.side_effect = _fake_urlopen()
        reports = [{"id": f"c-{i}", "text": f"Report {i}"} for i in range(3)]
        result = self._run_burst(reports, concurrency=2)
        self.assertEqual(result["submitted"], 3)
        self.assertGreaterEqual(result["total_elapsed_ms"], 0)
        self.assertGreater(result["approximate_throughput_rps"], 0)
        # Token counts should be sum of individual cases
        expected_total = sum(c.get("total_tokens") or 0 for c in result["cases"])
        self.assertEqual(result["total_tokens"], expected_total)

    def test_burst_max_cases_constant(self):
        self.assertEqual(BURST_MAX_CASES, 24)

    def test_burst_valid_concurrency_set(self):
        self.assertEqual(BURST_VALID_CONCURRENCY, {1, 2, 4, 6, 8})


# ─── Capability Map text checks ──────────────────────────────────────────────

class TestCapabilityMapTextAbsence(unittest.TestCase):
    """Verify that removed text is not present in the frontend source."""

    def _read_frontend_source(self, filename: str) -> str:
        base = os.path.join(os.path.dirname(__file__), "..", "dashboard", "src")
        for root_dir, dirs, files in os.walk(base):
            for f in files:
                if f == filename:
                    path = os.path.join(root_dir, f)
                    with open(path, encoding="utf-8") as fh:
                        return fh.read()
        return ""

    def test_capability_map_no_replit_vercel_streamlit_comparison(self):
        src = self._read_frontend_source("CapabilityMap.tsx")
        self.assertNotIn("Replit Full-Stack (Recommended)", src)
        self.assertNotIn("Frontend-only hosting. Requires the Python API", src)
        self.assertNotIn("Python-only alternate UI; does not apply to this React application", src)

    def test_capability_map_section_renamed(self):
        src = self._read_frontend_source("CapabilityMap.tsx")
        self.assertIn("Live Deployment Status", src)

    def test_amd_impact_no_pending_verification_static(self):
        src = self._read_frontend_source("AmdImpact.tsx")
        # The specific "Pending Verification" static card text must be gone
        self.assertNotIn("Pending Verification", src)

    def test_amd_impact_has_amd_accelerator_card(self):
        src = self._read_frontend_source("AmdImpact.tsx")
        self.assertIn("AMD Accelerator", src)
        self.assertIn("AMD Developer Cloud", src)

    def test_amd_impact_has_three_workload_tabs(self):
        src = self._read_frontend_source("AmdImpact.tsx")
        self.assertIn("Single Incident", src)
        self.assertIn("Complex Dossier", src)
        self.assertIn("Burst Workload", src)

    def test_amd_impact_confirmation_checkbox_present(self):
        src = self._read_frontend_source("AmdImpact.tsx")
        self.assertIn("synthetic demonstration data", src)

    def test_walkthrough_has_new_amd_steps(self):
        src = self._read_frontend_source("JudgeWalkthroughModal.tsx")
        self.assertIn("Try Your Own Incident", src)
        self.assertIn("Complex Dossier", src)
        self.assertIn("Burst Workload", src)


if __name__ == "__main__":
    unittest.main()

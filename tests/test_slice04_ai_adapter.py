import json
from contextlib import redirect_stdout
from io import StringIO
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from reliefqueue.ai import (
    AIConfig,
    OpenAICompatibleAdapter,
    apply_ai_enrichment,
    parse_ai_json,
    validate_ai_output,
)
from reliefqueue.cli import build_cases
from reliefqueue.intake import load_json, load_jsonl
from reliefqueue.privacy import redact_public_case


ROOT = Path(__file__).resolve().parents[1]


class Slice04AIAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reports = load_jsonl(ROOT / "fixtures" / "reliefqueue_seed_reports.jsonl")
        cls.zones = load_json(ROOT / "fixtures" / "operation_zones.json")
        cls.cases = build_cases(cls.reports, cls.zones)

    def test_mock_output_is_deterministic_and_useful(self) -> None:
        left = build_cases(self.reports[:2], self.zones)
        right = build_cases(self.reports[:2], self.zones)
        report_left = apply_ai_enrichment(left, AIConfig(mode="mock"))
        report_right = apply_ai_enrichment(right, AIConfig(mode="mock"))
        self.assertEqual(report_left["status_counts"], {"success": 2})
        self.assertEqual(report_right["status_counts"], {"success": 2})
        self.assertEqual(
            [(case["ai_safe_summary"], case["ai_reply_draft"], case["ai_warnings"]) for case in left],
            [(case["ai_safe_summary"], case["ai_reply_draft"], case["ai_warnings"]) for case in right],
        )
        self.assertTrue(left[0]["ai_missing_info_questions"])

    def test_openai_compatible_missing_env_skips_without_network(self) -> None:
        config = AIConfig(
            mode="openai_compatible",
            base_url="http://localhost:8000/v1",
            api_key="changeme",
            model="local-model-name",
            timeout_seconds=0.01,
            max_retries=0,
        )
        adapter = OpenAICompatibleAdapter(config)
        self.assertEqual(adapter.health_check()["status"], "skipped_missing_env")
        result = adapter.enrich_case(self.cases[0])
        self.assertEqual(result["ai_status"], "skipped_missing_env")
        self.assertIn("Missing OpenAI-compatible env", result["ai_error"])

    def test_bad_json_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            parse_ai_json("safe_summary: not json")

    def test_unsafe_wording_rejected(self) -> None:
        payload = {
            "safe_summary": "confirmed rescued and confirmed safe",
            "missing_info_questions": [],
            "reply_draft": "Help is guaranteed.",
            "operator_note": "AI verified the emergency.",
            "language": "en",
            "warnings": [],
        }
        with self.assertRaisesRegex(ValueError, "unsafe wording"):
            validate_ai_output(payload, self.cases[0])

    def test_ai_failure_preserves_case_count(self) -> None:
        cases = build_cases(self.reports[:3], self.zones)
        report = apply_ai_enrichment(cases, AIConfig(mode="none"))
        self.assertEqual(len(cases), 3)
        self.assertEqual(report["status_counts"], {"not_requested": 3})
        self.assertTrue(all(case["ai_status"] == "not_requested" for case in cases))

    def test_public_export_redaction_after_ai(self) -> None:
        cases = build_cases(self.reports[:5], self.zones)
        apply_ai_enrichment(cases, AIConfig(mode="mock"))
        rows = [redact_public_case(case) for case in cases]
        rendered = json.dumps(rows, ensure_ascii=False)
        self.assertIsNone(re.search(r"(?:\+?\d[\s-]?){10,}", rendered))
        self.assertNotIn("raw_text_private", rendered)
        self.assertNotIn("ai_reply_draft", rendered)
        self.assertNotIn("Synthetic Asha", rendered)

    def test_ai_fields_are_suggested_and_review_needed_only(self) -> None:
        cases = build_cases(self.reports[:1], self.zones)
        before = {
            key: cases[0][key]
            for key in [
                "urgency",
                "need_type",
                "assignment_ready",
                "suggested_reply_draft",
                "safe_summary",
            ]
        }
        apply_ai_enrichment(cases, AIConfig(mode="mock"))
        after = cases[0]
        for key, value in before.items():
            self.assertEqual(after[key], value)
        ai_keys = {key for key in after if key.startswith("ai_")}
        self.assertTrue(
            {
                "ai_status",
                "ai_safe_summary",
                "ai_missing_info_questions",
                "ai_reply_draft",
                "ai_operator_note",
                "ai_review_required",
            }.issubset(ai_keys)
        )
        self.assertTrue(after["ai_review_required"])

    def test_openai_compatible_bad_endpoint_records_failure_without_losing_cases(self) -> None:
        cases = build_cases(self.reports[:2], self.zones)
        report = apply_ai_enrichment(
            cases,
            AIConfig(
                mode="openai_compatible",
                base_url="http://127.0.0.1:9/v1",
                api_key="test-key",
                model="test-model",
                timeout_seconds=0.05,
                max_retries=0,
            ),
        )
        self.assertEqual(len(cases), 2)
        self.assertTrue(set(report["status_counts"]).issubset({"provider_error", "timeout"}))
        self.assertTrue(all(case["ai_review_required"] for case in cases))


    def test_openai_request_headers_include_user_agent_for_fireworks(self) -> None:
        config = AIConfig(
            mode="openai_compatible",
            base_url="https://api.fireworks.ai/inference/v1",
            api_key="test-key",
            model="accounts/fireworks/models/deepseek-v4-flash",
            http_user_agent="ReliefQueueAI/0.1 OpenAICompatibleClient",
        )
        adapter = OpenAICompatibleAdapter(config)
        headers = adapter._request_headers()
        self.assertEqual(headers["User-Agent"], "ReliefQueueAI/0.1 OpenAICompatibleClient")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_openai_request_can_disable_response_format_for_provider_compatibility(self) -> None:
        config = AIConfig(
            mode="openai_compatible",
            base_url="https://api.fireworks.ai/inference/v1",
            api_key="test-key",
            model="accounts/fireworks/models/deepseek-v4-flash",
            response_format="none",
        )
        adapter = OpenAICompatibleAdapter(config)
        body = adapter._build_request(self.cases[0])
        self.assertNotIn("response_format", body)
        self.assertEqual(body["model"], "accounts/fireworks/models/deepseek-v4-flash")


    def test_provider_echo_envelope_is_unwrapped_then_validated(self) -> None:
        content = json.dumps(
            {
                "required_shape": {
                    "safe_summary": "safe public summary",
                    "missing_info_questions": ["Can the coordinator confirm the landmark?"],
                    "reply_draft": "Your report has been received for human review.",
                    "operator_note": "Review location clue before any field instruction.",
                    "language": "en",
                    "warnings": ["needs_human_review"],
                },
                "case": {"case_id": "echoed-input-should-not-be-output"},
            }
        )
        payload = parse_ai_json(content)
        self.assertEqual(set(payload), {
            "safe_summary",
            "missing_info_questions",
            "reply_draft",
            "operator_note",
            "language",
            "warnings",
        })
        self.assertEqual(validate_ai_output(payload, self.cases[0])["language"], "en")

    def test_prompt_asks_for_flat_output_without_required_shape_wrapper(self) -> None:
        adapter = OpenAICompatibleAdapter(
            AIConfig(
                mode="openai_compatible",
                base_url="https://api.fireworks.ai/inference/v1",
                api_key="test-key",
                model="accounts/fireworks/models/deepseek-v4-flash",
            )
        )
        body = adapter._build_request(self.cases[0])
        system_content = body["messages"][0]["content"]
        user_content = body["messages"][1]["content"]
        prompt_payload = json.loads(user_content)
        self.assertIn("top-level JSON object", system_content)
        self.assertNotIn("required_shape", prompt_payload)
        self.assertNotIn("case", prompt_payload)
        self.assertIn("required_output_keys", prompt_payload)
        self.assertIn("case_context_for_reference_only", prompt_payload)
        self.assertIn("required_shape", prompt_payload["forbidden_top_level_output_keys"])


    def test_ai_smoke_prints_sanitized_failure_details(self) -> None:
        from reliefqueue.cli import ai_smoke

        def fake_apply_ai_enrichment(cases, _config):
            for case in cases:
                case["ai_status"] = "failed_validation"
                case["ai_provider"] = "openai_compatible"
                case["ai_error"] = "AI output keys must exactly match required keys; token=secret-test-token; reporter +91 99999 99999"
                case["ai_review_required"] = True
            return {
                "mode": "openai_compatible",
                "health": {"status": "configured"},
                "status_counts": {"failed_validation": len(cases)},
                "redacted_endpoint": "https://api.fireworks.ai/inference/v1",
                "fallback_behavior": "deterministic case data is preserved",
            }

        env = {
            "AI_MODE": "openai_compatible",
            "OPENAI_COMPAT_BASE_URL": "https://api.fireworks.ai/inference/v1",
            "OPENAI_COMPAT_API_KEY": "test-key",
            "OPENAI_COMPAT_MODEL": "accounts/fireworks/models/deepseek-v4-flash",
        }
        buffer = StringIO()
        with patch.dict("os.environ", env, clear=True), patch(
            "reliefqueue.cli.apply_ai_enrichment", fake_apply_ai_enrichment
        ), redirect_stdout(buffer):
            result = ai_smoke(ROOT)
        output = buffer.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("AI failure details:", output)
        self.assertIn("failed_validation", output)
        self.assertIn("AI output keys must exactly match", output)
        self.assertIn("<redacted-phone>", output)
        self.assertIn("<redacted>", output)
        self.assertNotIn("99999 99999", output)
        self.assertNotIn("secret-test-token", output)

    def test_ai_smoke_bad_endpoint_returns_failure_code(self) -> None:
        from reliefqueue.cli import ai_smoke

        env = {
            "AI_MODE": "openai_compatible",
            "OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:9/v1",
            "OPENAI_COMPAT_API_KEY": "test-key",
            "OPENAI_COMPAT_MODEL": "test-model",
            "AI_TIMEOUT_SECONDS": "0.05",
            "AI_MAX_RETRIES": "0",
        }
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(ai_smoke(ROOT), 1)


if __name__ == "__main__":
    unittest.main()

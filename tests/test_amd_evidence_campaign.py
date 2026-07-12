from __future__ import annotations

import json
import os
from pathlib import Path
import unittest

from reliefqueue.amd_evidence import (
    AmdEvidenceError,
    amd_capability_payload,
    current_amd_runtime_status,
    load_amd_evidence_campaign,
    public_amd_evidence_payload,
    validate_amd_evidence_campaign,
)

ROOT = Path(__file__).resolve().parents[1]


class TestAmdEvidenceCampaign(unittest.TestCase):
    def test_frozen_campaign_is_valid_and_complete(self) -> None:
        campaign = load_amd_evidence_campaign()
        quality = campaign["final_resolved_quality"]
        self.assertEqual(quality["cases_resolved"], 24)
        self.assertEqual(quality["overall_pass_rate_pct"], 100.0)
        self.assertEqual(quality["source_coverage_rate_pct"], 100.0)
        self.assertEqual(quality["nonce_binding_rate_pct"], 100.0)
        self.assertEqual(quality["strict_raw_json_rate_pct"], 95.83)
        self.assertEqual(quality["strict_raw_json_anomaly_case_ids"], ["single-002"])

    def test_case_mix_and_review_boundary_are_preserved(self) -> None:
        campaign = load_amd_evidence_campaign()
        self.assertEqual(
            campaign["case_mix"],
            {"single_report": 8, "complex_dossier": 8, "adversarial": 8},
        )
        self.assertTrue(all(row["review_required"] for row in campaign["cases"]))
        self.assertFalse(campaign["uniform_prompt_run"])
        self.assertFalse(campaign["application_fallback_exercised"])

    def test_public_payload_does_not_claim_current_live_status(self) -> None:
        payload = public_amd_evidence_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["truthfulness"]["current_live_status_inferred"])
        self.assertEqual(payload["historical_evidence"]["evidence_scope"], "historical_verified_campaign")

    def test_runtime_status_redacts_url_and_key(self) -> None:
        env = {
            "AI_MODE": "openai_compatible",
            "OPENAI_COMPAT_BASE_URL": "https://private.example/v1",
            "OPENAI_COMPAT_API_KEY": "super-secret-value",
            "OPENAI_COMPAT_MODEL": "reliefqueue-amd",
            "OPENAI_COMPAT_UNDERLYING_MODEL": "Qwen/Qwen2.5-7B-Instruct",
        }
        status = current_amd_runtime_status(env)
        rendered = json.dumps(status)
        self.assertTrue(status["configured"])
        self.assertFalse(status["live_request_verified"])
        self.assertNotIn("private.example", rendered)
        self.assertNotIn("super-secret-value", rendered)

    def test_capability_payload_has_three_distinct_planes(self) -> None:
        payload = amd_capability_payload(env={"AI_MODE": "mock"})
        self.assertIn("historical_evidence", payload)
        self.assertIn("live_runtime", payload)
        self.assertIn("current_request", payload)
        self.assertEqual(payload["live_runtime"]["status"], "not_configured")
        self.assertFalse(payload["current_request"]["attempted"])

    def test_validator_rejects_misleading_uniform_run_claim(self) -> None:
        campaign = load_amd_evidence_campaign()
        campaign["uniform_prompt_run"] = True
        with self.assertRaises(AmdEvidenceError):
            validate_amd_evidence_campaign(campaign)

    def test_schema_file_exists(self) -> None:
        schema = json.loads((ROOT / "schemas" / "amd_evidence_campaign_v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["campaign_type"]["const"], "staged_composite")


if __name__ == "__main__":
    unittest.main()

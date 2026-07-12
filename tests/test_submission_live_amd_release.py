from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from reliefqueue import judge_rate_limit
from reliefqueue.product_api import ProductApiError, _require_live_amd_synthetic_confirmation

ROOT = Path(__file__).resolve().parents[1]


class SubmissionLiveAmdReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        judge_rate_limit.reset_live_amd_budgets_for_test()

    def tearDown(self) -> None:
        judge_rate_limit.reset_live_amd_budgets_for_test()

    def test_rate_budget_counts_estimated_provider_calls(self) -> None:
        env = {
            "RELIEFQUEUE_AMD_DEMO_RATE_WINDOW_SECONDS": "3600",
            "RELIEFQUEUE_AMD_DEMO_IP_BUDGET": "5",
            "RELIEFQUEUE_AMD_DEMO_GLOBAL_BUDGET": "100",
        }
        with patch.dict(os.environ, env, clear=False):
            first = judge_rate_limit.consume_live_amd_budget(
                "judge-a",
                "/api/ai/live-verification",
                {"workload_mode": "complex_dossier"},
                now=1000.0,
            )
            blocked = judge_rate_limit.consume_live_amd_budget(
                "judge-a",
                "/api/ai/burst-verification",
                {"reports": [{"id": "a", "text": "x"}]},
                now=1001.0,
            )
        self.assertTrue(first["allowed"])
        self.assertEqual(first["cost"], 3)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["scope"], "ip")
        self.assertEqual(blocked["cost"], 3)

    def test_burst_cost_is_bounded_by_reviewed_case_limit(self) -> None:
        body = {"reports": [{"id": str(i), "text": "synthetic"} for i in range(100)]}
        self.assertEqual(
            judge_rate_limit.estimated_live_amd_cost("/api/ai/burst-verification", body),
            judge_rate_limit.LIVE_AMD_MAX_CASES + 2,
        )

    def test_live_provider_routes_require_explicit_synthetic_confirmation(self) -> None:
        live_route = "/api/ai/live-verification"
        burst_route = "/api/ai/burst-verification"

        with self.assertRaisesRegex(ProductApiError, "Confirm synthetic demonstration data"):
            _require_live_amd_synthetic_confirmation(live_route, {"text": "Synthetic flood report"})
        _require_live_amd_synthetic_confirmation(live_route, {})
        _require_live_amd_synthetic_confirmation(
            live_route,
            {"text": "Synthetic flood report", "synthetic_confirmed": True},
        )

        with self.assertRaisesRegex(ProductApiError, "Confirm every report is synthetic"):
            _require_live_amd_synthetic_confirmation(
                burst_route,
                {"reports": [{"id": "a", "text": "Synthetic"}]},
            )
        _require_live_amd_synthetic_confirmation(
            burst_route,
            {"reports": [{"id": "a", "text": "Synthetic"}], "synthetic_confirmed": True},
        )

        source = (ROOT / "src/reliefqueue/product_api.py").read_text(encoding="utf-8")
        self.assertIn("_require_live_amd_synthetic_confirmation(route, body)", source)
        self.assertIn("Protect public live-provider routes without constraining internal Python callers", source)

    def test_readme_make_commands_and_live_claim_boundary_are_consistent(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for invalid in [
            "make implementation milestone-host-preflight",
            "make implementation milestone-live-proof",
            "make implementation milestone-live-clean",
            "make implementation milestone-host-setup",
        ]:
            self.assertNotIn(invalid, text)
        for expected in [
            "make phase01-host-preflight",
            "make phase01-live-proof",
            "make phase01-live-clean",
            "submission-live-amd-check",
            "does not claim that no other hardware or model could process the same input",
        ]:
            self.assertIn(expected, text)

    def test_ui_does_not_claim_current_amd_before_request_verification(self) -> None:
        impact = (ROOT / "dashboard/src/commandStudio/views/AmdImpact.tsx").read_text(encoding="utf-8")
        control = (ROOT / "dashboard/src/commandStudio/views/AIControl.tsx").read_text(encoding="utf-8")
        walkthrough = (ROOT / "dashboard/src/commandStudio/components/JudgeWalkthroughModal.tsx").read_text(encoding="utf-8")
        self.assertNotIn("The AMD MI300X endpoint will process", impact)
        self.assertIn("Attempt Live AMD Analysis", impact)
        self.assertIn('data-testid="amd-impact-comparison"', impact)
        self.assertIn("Deterministic support · 0 provider calls", impact)
        self.assertIn("Not a hardware-exclusivity benchmark", impact)
        self.assertNotIn("The current active model is", control)
        self.assertIn("Use Test Connection for current-request truth", control)
        self.assertIn("Deterministic Workflow Advisory", walkthrough)
        self.assertIn("not the live AMD path", walkthrough)
        self.assertIn("!step3Consent", walkthrough)
        self.assertGreaterEqual(walkthrough.count("synthetic_confirmed: true"), 3)

    def test_generated_reports_are_not_source_control_inputs(self) -> None:
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("reports/*", text)
        self.assertIn("!reports/.gitkeep", text)

    def test_makefile_exposes_offline_live_and_public_proof_targets(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("amd-quality-offline-validation:", text)
        self.assertIn("amd-quality-live-validation:", text)
        self.assertIn("submission-live-amd-check:", text)
        self.assertIn("RELIEFQUEUE_CONFIRM_LIVE_AMD=YES is required", text)

    def test_public_live_check_has_bounded_synthetic_contract(self) -> None:
        text = (ROOT / "scripts/submission_live_amd_check.py").read_text(encoding="utf-8")
        self.assertIn("synthetic_confirmed", text)
        self.assertIn("verification_bound_to_nonce", text)
        self.assertIn("fallback_used_false", text)
        self.assertIn("does not prove hardware exclusivity", text)
        self.assertNotIn("OPENAI_COMPAT_API_KEY", text)

    def test_submission_pack_optionally_embeds_verified_public_live_proof(self) -> None:
        text = (ROOT / "src/reliefqueue/submission_pack.py").read_text(encoding="utf-8")
        self.assertIn("submission-live-amd", text)
        self.assertIn("report.json", text)
        self.assertIn("08_live_amd_public_proof.json", text)
        self.assertIn("provider_calls_were_made_by_pack_generator", text)
        self.assertIn("verified_different_url", text)


if __name__ == "__main__":
    unittest.main()

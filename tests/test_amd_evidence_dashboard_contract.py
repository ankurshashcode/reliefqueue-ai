from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AmdEvidenceDashboardContractTests(unittest.TestCase):
    def test_amd_impact_separates_evidence_planes(self) -> None:
        text = (ROOT / "dashboard/src/commandStudio/views/AmdImpact.tsx").read_text(encoding="utf-8")
        self.assertIn("AmdEvidenceSummary", text)
        self.assertIn("Historical evidence only", text)
        self.assertIn("Live status is established per request", text)
        self.assertNotIn('label="Inference Mode" value="Live AMD/vLLM"', text)

    def test_capability_map_does_not_hardcode_current_live_provider(self) -> None:
        text = (ROOT / "dashboard/src/commandStudio/views/CapabilityMap.tsx").read_text(encoding="utf-8")
        self.assertIn("GET /api/product/amd/evidence", text)
        self.assertIn("GET /api/product/amd/capability", text)
        self.assertIn("Not configured in this process", text)
        self.assertIn("Provider: {liveRuntime?.configured", text)
        self.assertNotIn("AI provider: AMD Developer Cloud<br/>", text)
        self.assertNotIn("Active model: Qwen/Qwen2.5-7B-Instruct<br/>", text)
        self.assertIn('data-testid="capability-runtime-status"', text)
        self.assertIn("data-api-status={runtime.api.toLowerCase()}", text)
        self.assertIn("data-health-status={runtime.health.toLowerCase()}", text)

    def test_global_banner_uses_per_request_wording(self) -> None:
        text = (ROOT / "dashboard/src/commandStudio/App.tsx").read_text(encoding="utf-8")
        self.assertIn("AMD/vLLM evidence available", text)
        self.assertIn("Live status verified per request", text)
        self.assertNotIn("Live AMD/vLLM advisory inference", text)

    def test_summary_exposes_historical_runtime_and_request_labels(self) -> None:
        text = (ROOT / "dashboard/src/commandStudio/components/AmdEvidenceSummary.tsx").read_text(encoding="utf-8")
        for label in (
            "Historical verified campaign",
            "Current runtime configuration",
            "Current request result",
            "Staged composite",
            "Strict raw JSON",
            "Human Review",
            'data-testid="amd-human-review-status"',
        ):
            self.assertIn(label, text)


if __name__ == "__main__":
    unittest.main()

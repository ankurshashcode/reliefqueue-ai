from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_public_ship_check():
    script = ROOT / "scripts" / "public_ship_check.py"
    spec = importlib.util.spec_from_file_location("public_ship_check", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SubmissionFinalGateReleaseRepairTests(unittest.TestCase):
    def test_internal_testing_runbook_is_not_treated_as_submission_copy(self) -> None:
        module = load_public_ship_check()
        self.assertTrue(
            module.is_allowed(
                "docs/testing/website-testing.md",
                "Internal Codex and Daytona engineering notes",
            )
        )
        self.assertFalse(
            module.is_allowed(
                "docs/submission.md",
                "Internal Codex and Daytona engineering notes",
            )
        )

    def test_replit_navigation_uses_semantic_runtime_readiness(self) -> None:
        text = (ROOT / "dashboard/scripts/replitNavigationCheck.mjs").read_text(encoding="utf-8")
        self.assertIn('data-testid="capability-runtime-status"', text)
        self.assertIn('data-api-status="connected"', text)
        self.assertIn('data-health-status="passing"', text)
        self.assertNotIn("'Product API: Connected'", text)
        self.assertNotIn("'State persistence: Ephemeral'", text)

    def test_capability_map_exposes_semantic_runtime_state(self) -> None:
        text = (ROOT / "dashboard/src/commandStudio/views/CapabilityMap.tsx").read_text(encoding="utf-8")
        self.assertIn('data-testid="capability-runtime-status"', text)
        self.assertIn('data-api-status={runtime.api.toLowerCase()}', text)
        self.assertIn('data-health-status={runtime.health.toLowerCase()}', text)


if __name__ == "__main__":
    unittest.main()

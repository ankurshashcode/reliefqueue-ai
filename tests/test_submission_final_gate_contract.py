from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "submission_final_gate.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("submission_final_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SubmissionFinalGateContractTests(unittest.TestCase):
    def test_gate_removes_provider_credentials_and_forces_mock(self) -> None:
        module = load_gate_module()
        env = module.sanitized_environment(
            {
                "PATH": os.environ.get("PATH", ""),
                "OPENAI_COMPAT_API_KEY": "should-disappear",
                "FIREWORKS_API_KEY": "should-disappear",
                "AI_MODE": "openai_compatible",
            }
        )
        self.assertNotIn("OPENAI_COMPAT_API_KEY", env)
        self.assertNotIn("FIREWORKS_API_KEY", env)
        self.assertEqual(env["AI_MODE"], "mock")
        self.assertEqual(env["PYTHONPATH"], "src")

    def test_full_gate_covers_submission_critical_surfaces(self) -> None:
        module = load_gate_module()
        names = [name for name, _ in module.command_plan(fast=False, include_public=False)]
        for expected in [
            "amd-evidence-validate",
            "repository-tests",
            "no-secrets",
            "public-ship-check",
            "dashboard-build",
            "amd-evidence-ui-check",
            "command-center-click-smoke",
            "field-app-click-smoke",
            "local-coordinator-click-smoke",
            "product-complete-smoke",
            "replit-smoke",
            "replit-navigation-smoke",
            "submission-pack",
        ]:
            self.assertIn(expected, names)

    def test_makefile_exposes_submission_targets(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("submission-pack:", text)
        self.assertIn("submission-final-gate:", text)
        self.assertIn("submission-public-check:", text)


if __name__ == "__main__":
    unittest.main()

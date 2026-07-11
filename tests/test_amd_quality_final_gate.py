from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "amd_quality_live_validation.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "reliefqueue_amd_quality_live_validation",
        VALIDATOR,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load AMD quality live validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAmdFinalQualityGatePart8(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = _load_validator()

    def test_conflict_observation_count_accepts_one_direct_contradiction(self) -> None:
        record = {
            "contradictions": [{"source_ids": ["REPORT-006", "REPORT-007"]}],
            "superseded_updates": [{"older_source_id": "REPORT-005"}],
            "duplicate_clusters": [{"source_ids": ["REPORT-001", "REPORT-003"]}],
            "unverified_claims": [],
        }
        self.assertEqual(
            self.validator._conflict_resolution_observation_count(record),
            3,
        )


    def test_final_runner_allows_one_targeted_incident_supplement(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn(
            "dossier_calls in {1, 2, 3}",
            source,
        )
        self.assertIn(
            "dossier provider-call count must be 1, 2 or 3",
            source,
        )
        self.assertIn(
            "max_live_provider_calls > 8",
            source,
        )

    def test_final_runner_does_not_restore_three_direct_contradiction_gate(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertNotIn("fewer than three contradictions", source)
        self.assertIn("fewer than one direct contradiction", source)
        self.assertIn(
            "fewer than three aggregate conflict-resolution observations",
            source,
        )


if __name__ == "__main__":
    unittest.main()

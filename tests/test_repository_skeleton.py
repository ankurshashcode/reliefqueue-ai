from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositorySkeletonTests(unittest.TestCase):
    def test_required_seed_files_exist(self) -> None:
        required = [
            "docs/living-guide.md",
            "docs/safety-boundary.md",
            "docs/ai-boundary.md",
            "docs/pilot-readiness.md",
            "fixtures/reliefqueue_seed_reports.jsonl",
            "fixtures/operation_zones.json",
            "fixtures/field_workers.json",
            "fixtures/slice1_expected_behavior.json",
            "src/reliefqueue/__init__.py",
            "reports/.gitkeep",
            "schemas/.gitkeep",
        ]
        missing = [path for path in required if not (ROOT / path).exists()]
        self.assertEqual(missing, [])


    def test_seed_report_count_is_at_least_contract_minimum(self) -> None:
        seed_file = ROOT / "fixtures" / "reliefqueue_seed_reports.jsonl"
        rows = [line for line in seed_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(rows), 24)

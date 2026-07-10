import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reliefqueue.cli import build_cases
from reliefqueue.hardening import (
    amd_benchmark,
    audit_smoke,
    backup_demo_state,
    degraded_mode_smoke,
    operations_smoke,
    pilot_feedback_template,
    pilot_smoke,
    privacy_check,
    restore_demo_state,
    reviewer_pack,
    security_check,
)
from reliefqueue.intake import load_json, load_jsonl
from reliefqueue.reports import write_outputs
from reliefqueue.assignment import suggest_assignments


ROOT = Path(__file__).resolve().parents[1]


class HardeningCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "fixtures", self.root / "fixtures")
        shutil.copytree(ROOT / "src", self.root / "src")
        self.report_dir = self.root / "reports" / "latest"
        reports = load_jsonl(self.root / "fixtures" / "reliefqueue_seed_reports.jsonl")
        zones = load_json(self.root / "fixtures" / "operation_zones.json")
        workers = load_json(self.root / "fixtures" / "field_workers.json")
        cases = build_cases(reports, zones)
        suggestions = suggest_assignments(cases, workers)
        write_outputs(self.report_dir, cases, suggestions, "# validation\n", zones)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_privacy_and_audit_commands_write_safe_outputs(self) -> None:
        self.assertEqual(audit_smoke(self.report_dir), 0)
        self.assertEqual(privacy_check(self.report_dir), 0)
        public = (self.report_dir / "public" / "redacted_cases.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("raw_text_private", public)
        self.assertNotIn("reporter_phone_private_optional", public)
        audit = load_jsonl(self.report_dir / "field_audit_demo.jsonl")
        self.assertTrue(all(row.get("private_number_revealed") is False for row in audit if "private_number_revealed" in row))

    def test_operations_backup_restore_and_degraded_mode(self) -> None:
        self.assertEqual(operations_smoke(self.root, self.report_dir), 0)
        self.assertEqual(degraded_mode_smoke(self.report_dir), 0)
        self.assertEqual(backup_demo_state(self.root, self.report_dir), 0)
        self.assertEqual(restore_demo_state(self.root, self.report_dir), 0)
        self.assertTrue((self.report_dir / "operations_status.json").exists())
        self.assertTrue((self.report_dir / "restore-smoke" / "reports" / "latest" / "summary.json").exists())

    def test_reviewer_pack_excludes_private_markers(self) -> None:
        self.assertEqual(reviewer_pack(self.root, self.report_dir), 0)
        self.assertEqual(pilot_feedback_template(self.report_dir), 0)
        self.assertEqual(pilot_smoke(self.report_dir), 0)
        rendered = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (self.report_dir / "reviewer_pack").rglob("*")
            if path.is_file()
        )
        self.assertNotIn("raw_text_private", rendered)
        self.assertNotIn("PRIVATE_OPERATOR_EXPORT", rendered)

    def test_amd_benchmark_mock_and_missing_endpoint_are_local(self) -> None:
        with patch.dict("os.environ", {"AI_MODE": "mock", "BENCH_REPORT_COUNT": "3"}, clear=True):
            self.assertEqual(amd_benchmark(self.root, self.report_dir), 0)
        metrics = json.loads((self.report_dir / "amd_benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["report_count"], 3)
        self.assertEqual(metrics["ai_mode"], "mock")

        with patch.dict("os.environ", {"AI_MODE": "openai-compatible", "BENCH_REPORT_COUNT": "3"}, clear=True):
            self.assertEqual(amd_benchmark(self.root, self.report_dir), 0)
        metrics = json.loads((self.report_dir / "amd_benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["health_status"], "skipped_missing_env")

    def test_security_check_reports_no_values(self) -> None:
        self.assertEqual(security_check(self.root), 0)


if __name__ == "__main__":
    unittest.main()

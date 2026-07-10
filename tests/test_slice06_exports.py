import csv
import json
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from reliefqueue.assignment import suggest_assignments
from reliefqueue.cli import build_cases, export_public_command
from reliefqueue.exports import export_private, export_public, validate_public_exports
from reliefqueue.intake import load_json, load_jsonl
from reliefqueue.privacy import PUBLIC_CASE_FIELDS
from reliefqueue.reports import write_outputs


ROOT = Path(__file__).resolve().parents[1]


class Slice06ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "fixtures", self.root / "fixtures")
        self.report_dir = self.root / "reports" / "latest"
        reports = load_jsonl(self.root / "fixtures" / "reliefqueue_seed_reports.jsonl")
        zones = load_json(self.root / "fixtures" / "operation_zones.json")
        workers = load_json(self.root / "fixtures" / "field_workers.json")
        self.cases = build_cases(reports, zones)
        self.assignments = suggest_assignments(self.cases, workers)
        write_outputs(self.report_dir, self.cases, self.assignments, "# validation\n", zones)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_private_manifest_contains_private_labels(self) -> None:
        manifest = export_private(self.report_dir)
        self.assertEqual(manifest["export_type"], "private")
        for label in ["PRIVATE_OPERATOR_EXPORT", "DO_NOT_SHARE_PUBLICLY", "SYNTHETIC_DEMO_DATA"]:
            self.assertIn(label, manifest["labels"])
        rendered = (self.report_dir / "private" / "operator_cases.jsonl").read_text(encoding="utf-8")
        self.assertIn("PRIVATE_OPERATOR_EXPORT", rendered)
        self.assertIn("DO_NOT_SHARE_PUBLICLY", rendered)
        self.assertIn("SYNTHETIC_DEMO_DATA", rendered)
        csv_text = (self.report_dir / "private" / "operator_cases.csv").read_text(encoding="utf-8")
        self.assertIn("PRIVATE_OPERATOR_EXPORT", csv_text)

    def test_public_export_contains_only_allowlisted_keys(self) -> None:
        export_public(self.report_dir)
        rows = self._public_rows()
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertEqual(set(row), set(PUBLIC_CASE_FIELDS))

    def test_public_export_has_no_phone_like_strings(self) -> None:
        export_public(self.report_dir)
        result = validate_public_exports(self.report_dir)
        self.assertTrue(result["passed"], result["errors"])
        rendered = (self.report_dir / "public" / "redacted_cases.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("+910000000001", rendered)

    def test_public_export_has_no_raw_text_private_key(self) -> None:
        export_public(self.report_dir)
        rendered = (self.report_dir / "public" / "redacted_cases.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("raw_text_private", rendered)

    def test_public_export_has_no_known_private_fixture_names(self) -> None:
        export_public(self.report_dir)
        rendered = (self.report_dir / "public" / "redacted_cases.jsonl").read_text(encoding="utf-8")
        for name in ["Synthetic Asha", "Synthetic Ravi", "Synthetic Nurse"]:
            self.assertNotIn(name, rendered)

    def test_public_summaries_use_safe_vulnerable_categories(self) -> None:
        export_public(self.report_dir)
        rendered = (self.report_dir / "public" / "redacted_cases.jsonl").read_text(encoding="utf-8")
        for private_term in ["pregnant", "disabled", "medical_condition"]:
            self.assertNotIn(private_term, rendered.lower())
        self.assertIn("medical_risk", rendered)
        self.assertIn("mobility_support_needed", rendered)

    def test_leak_fixture_fails_validation(self) -> None:
        public_dir = self.report_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        leaked = {field: "" for field in PUBLIC_CASE_FIELDS}
        leaked.update(
            {
                "case_id": "case-leak",
                "public_case_ref": "public-leak",
                "safe_summary": "Synthetic Asha called +910000000001 and was confirmed rescued.",
                "urgency": "RED",
                "need_type": "rescue",
                "people_count_bucket": "1",
                "vulnerable_category_flags": ["child"],
                "raw_text_private": "private raw report",
            }
        )
        (public_dir / "redacted_cases.jsonl").write_text(json.dumps(leaked) + "\n", encoding="utf-8")
        result = validate_public_exports(self.report_dir)
        self.assertFalse(result["passed"])
        joined = "\n".join(result["errors"])
        self.assertIn("raw_text_private", joined)
        self.assertIn("phone-like", joined)
        self.assertIn("known private fixture name", joined)
        self.assertIn("unsafe wording", joined)

    def test_export_counts_match_source_cases(self) -> None:
        manifest = export_public(self.report_dir)
        rows = self._public_rows()
        self.assertEqual(len(rows), len(self.cases))
        self.assertEqual(manifest["record_counts"]["redacted_cases"], len(self.cases))
        self.assertEqual(manifest["record_counts"]["source_cases"], len(self.cases))

    def test_public_summaries_are_generated(self) -> None:
        export_public(self.report_dir)
        for name in [
            "zone_summary_public.csv",
            "need_type_summary_public.csv",
            "missing_info_summary_public.csv",
        ]:
            path = self.report_dir / "public" / name
            self.assertTrue(path.exists(), name)
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreater(len(rows), 0, name)

    def test_export_public_command_fails_when_redaction_fails(self) -> None:
        with mock.patch(
            "reliefqueue.cli.export_public",
            return_value={"files": ["redacted_cases.jsonl"], "redaction_passed": False},
        ):
            self.assertEqual(export_public_command(self.report_dir), 1)

    def test_unsafe_wording_regression_without_guard_fixture_false_positive(self) -> None:
        export_public(self.report_dir)
        public_dir = self.report_dir / "public"
        (public_dir / "guard_notes.md").write_text(
            "This doc mentions confirmed rescued and dispatched as forbidden examples.",
            encoding="utf-8",
        )
        result = validate_public_exports(self.report_dir)
        self.assertTrue(result["passed"], result["errors"])

        rows = self._public_rows()
        rows[0]["safe_summary"] = "Field team confirmed rescued."
        (public_dir / "redacted_cases.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        result = validate_public_exports(self.report_dir)
        self.assertFalse(result["passed"])
        self.assertIn("unsafe wording", "\n".join(result["errors"]))

    def _public_rows(self) -> list[dict]:
        path = self.report_dir / "public" / "redacted_cases.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    unittest.main()

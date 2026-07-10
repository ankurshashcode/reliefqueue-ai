import copy
import json
import re
import unittest
from pathlib import Path

from reliefqueue.assignment import suggest_assignments
from reliefqueue.cli import build_cases
from reliefqueue.intake import (
    ValidationError,
    load_json,
    load_jsonl,
    validate_reports,
    validate_workers,
    validate_zones,
)
from reliefqueue.privacy import redact_public_case
from reliefqueue.triage import detect_language, detect_need_type, extract_people_count
from reliefqueue.validation import validate_expected_behavior


ROOT = Path(__file__).resolve().parents[1]


class Slice01PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reports = load_jsonl(ROOT / "fixtures" / "reliefqueue_seed_reports.jsonl")
        cls.zones = load_json(ROOT / "fixtures" / "operation_zones.json")
        cls.workers = load_json(ROOT / "fixtures" / "field_workers.json")
        cls.cases = build_cases(cls.reports, cls.zones)
        cls.suggestions = suggest_assignments(cls.cases, cls.workers)

    def test_expected_behavior_contract_passes(self) -> None:
        errors, _notes = validate_expected_behavior(ROOT, self.reports, self.cases, self.suggestions)
        self.assertEqual(errors, [])

    def test_known_duplicate_groups_and_zones(self) -> None:
        by_report = {case["source_report_id"]: case for case in self.cases}
        self.assertTrue(by_report["seed-001"]["duplicate_cluster_id"])
        self.assertEqual(
            by_report["seed-001"]["duplicate_cluster_id"],
            by_report["seed-002"]["duplicate_cluster_id"],
        )
        self.assertEqual(
            by_report["seed-012"]["duplicate_cluster_id"],
            by_report["seed-013"]["duplicate_cluster_id"],
        )
        self.assertEqual(by_report["seed-001"]["operation_zone_id"], "zone-ward-01")
        self.assertEqual(by_report["seed-003"]["operation_zone_id"], "zone-village-03")
        self.assertEqual(by_report["seed-004"]["operation_zone_id"], "zone-ward-02")
        self.assertEqual(by_report["seed-016"]["operation_zone_id"], "zone-ward-04")
        self.assertEqual(by_report["seed-023"]["operation_zone_id"], "zone-ward-04")
        self.assertFalse(by_report["seed-006"]["assignment_ready"])

    def test_assignment_candidates_respect_worker_constraints(self) -> None:
        by_report = {case["source_report_id"]: case for case in self.cases}
        suggested_workers = {row["worker_id"] for row in self.suggestions}
        self.assertNotIn("worker-epsilon-offline", suggested_workers)
        self.assertNotIn("worker-delta-food", suggested_workers)
        self.assertTrue(
            all(row["case_id"] != by_report["seed-006"]["case_id"] for row in self.suggestions)
        )
        seed_001 = [row for row in self.suggestions if row["case_id"] == by_report["seed-001"]["case_id"]]
        self.assertEqual(seed_001[0]["worker_id"], "worker-alpha-boat")
        seed_003 = [row for row in self.suggestions if row["case_id"] == by_report["seed-003"]["case_id"]]
        self.assertEqual(seed_003[0]["worker_id"], "worker-beta-medical")

    def test_public_export_allowlist_excludes_private_content(self) -> None:
        forbidden_fields = {
            "raw_text_private",
            "reporter_name_private_optional",
            "reporter_phone_private_optional",
            "media_note_private_optional",
        }
        rows = [redact_public_case(case) for case in self.cases]
        for row in rows:
            self.assertTrue(forbidden_fields.isdisjoint(row))
            text = json.dumps(row, ensure_ascii=False)
            self.assertIsNone(re.search(r"\+91[0-9]{10}", text))
            self.assertNotIn("Synthetic Asha", text)
            self.assertNotIn("Synthetic Ravi", text)
            self.assertNotIn("Synthetic Nurse", text)

    def test_language_need_and_people_rules(self) -> None:
        self.assertEqual(detect_language("हम लोग मेन ब्रिज के पास फंसे हैं"), "hi")
        self.assertEqual(detect_language("Hanuman mandir ke paas doctor chahiye"), "hinglish")
        self.assertEqual(detect_need_type("Need doctor and insulin urgently"), "medical")
        self.assertEqual(detect_need_type("Need clean drinking water for 6 people"), "food_water")
        self.assertEqual(extract_people_count("Primary Health Centre, Ward 3. 2 people with her."), 2)
        self.assertIsNone(extract_people_count("Warehouse Lane has 200 food packets ready."))


    def test_slice01_report_schemas_match_required_outputs(self) -> None:
        from reliefqueue.reports import build_summary, write_zone_summary
        from reliefqueue.privacy import PUBLIC_CASE_FIELDS
        import csv
        import tempfile

        summary = build_summary(self.cases, self.suggestions)
        required_summary = {
            "run_id",
            "created_at",
            "input_count",
            "case_count",
            "urgency_counts",
            "need_type_counts",
            "missing_info_count",
            "duplicate_cluster_count",
            "duplicate_case_count",
            "zone_tagged_count",
            "assignment_ready_count",
            "assignment_candidate_count",
            "public_redaction_passed",
            "ai_mode",
        }
        self.assertTrue(required_summary.issubset(summary))
        self.assertEqual(summary["ai_mode"], "none")
        self.assertEqual(summary["input_count"], len(self.reports))
        self.assertEqual(summary["case_count"], len(self.cases))

        public_row = redact_public_case(self.cases[0])
        self.assertEqual(list(public_row), PUBLIC_CASE_FIELDS)
        self.assertIn("people_count_bucket", public_row)
        self.assertIn("vulnerable_category_flags", public_row)
        self.assertIn("missing_fields_safe", public_row)
        self.assertIn(public_row["public_status"], {"needs_review", "queued", "info_missing"})

        for row in self.suggestions:
            for field in [
                "operation_zone_id",
                "required_skills",
                "candidate_worker_id",
                "candidate_display_name_safe",
                "match_reasons",
                "constraint_warnings",
                "rank",
                "assignment_status",
            ]:
                self.assertIn(field, row)
            self.assertEqual(row["assignment_status"], "suggested_not_dispatched")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zone_summary.csv"
            write_zone_summary(path, self.cases, self.suggestions, self.zones)
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)
            required_zone_fields = {
                "operation_zone_id",
                "zone_name",
                "case_count",
                "red_count",
                "amber_count",
                "green_count",
                "review_count",
                "missing_location_count",
                "assignment_ready_count",
                "assignment_candidate_count",
            }
            self.assertTrue(required_zone_fields.issubset(rows[0]))

    def test_invalid_report_duplicate_id_and_missing_text(self) -> None:
        duplicate = copy.deepcopy(self.reports[:2])
        duplicate[1]["report_id"] = duplicate[0]["report_id"]
        with self.assertRaisesRegex(ValidationError, "duplicate"):
            validate_reports(duplicate)
        missing_text = copy.deepcopy(self.reports[:1])
        missing_text[0]["text"] = ""
        with self.assertRaisesRegex(ValidationError, "missing text"):
            validate_reports(missing_text)

    def test_invalid_worker_status_and_capacity(self) -> None:
        bad_status = copy.deepcopy(self.workers[:1])
        bad_status[0]["current_status"] = "teleporting"
        with self.assertRaisesRegex(ValidationError, "invalid status"):
            validate_workers(bad_status)
        over_capacity = copy.deepcopy(self.workers[:1])
        over_capacity[0]["current_active_cases"] = 9
        with self.assertRaisesRegex(ValidationError, "over capacity"):
            validate_workers(over_capacity)

    def test_invalid_zone_missing_identifiers(self) -> None:
        bad = copy.deepcopy(self.zones[:1])
        bad[0]["landmarks"] = []
        bad[0]["aliases"] = []
        bad[0]["ward_or_village"] = ""
        with self.assertRaisesRegex(ValidationError, "location identifiers"):
            validate_zones(bad)

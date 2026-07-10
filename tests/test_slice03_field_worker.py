import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELD_ALLOWLIST = [
    "case_id",
    "safe_summary",
    "urgency",
    "need_type",
    "people_count",
    "vulnerable_flags",
    "operation_zone_id",
    "location_clue",
    "geo_confidence",
    "coordinator_instruction",
    "assignment_status",
]
PRIVATE_KEYS = {
    "raw_text_private",
    "reporter_name_private_optional",
    "reporter_phone_private_optional",
    "media_note_private_optional",
    "source_channel",
    "source_report_id",
    "suggested_reply_draft",
    "privacy_level",
    "language_hint",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def worker_safe_case(row: dict, assignment: dict) -> dict:
    safe = {
        "case_id": row.get("case_id") or "unknown-case",
        "safe_summary": row.get("safe_summary") or "No safe summary provided.",
        "urgency": row.get("urgency") or "REVIEW",
        "need_type": row.get("need_type") or "unknown",
        "people_count": row.get("people_count"),
        "vulnerable_flags": row.get("vulnerable_flags") or [],
        "operation_zone_id": row.get("operation_zone_id") or "unknown",
        "location_clue": row.get("location_clue") or "location unclear",
        "geo_confidence": row.get("geo_confidence") or "unknown",
        "coordinator_instruction": "Pending coordinator instruction.",
        "assignment_status": assignment.get("assignment_status") or "suggested_not_dispatched",
    }
    return {field: safe[field] for field in FIELD_ALLOWLIST}


class Slice03FieldWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (ROOT / "reports" / "latest" / "cases.jsonl").exists():
            from reliefqueue.cli import run_demo

            run_demo()
        cls.cases = load_jsonl(ROOT / "reports" / "latest" / "cases.jsonl")
        cls.assignments = load_jsonl(ROOT / "reports" / "latest" / "field_assignment_candidates.jsonl")
        cls.workers = json.loads((ROOT / "fixtures" / "field_workers.json").read_text(encoding="utf-8"))

    def test_required_slice03_inputs_exist(self) -> None:
        required = [
            ROOT / "reports" / "latest" / "cases.jsonl",
            ROOT / "reports" / "latest" / "field_assignment_candidates.jsonl",
            ROOT / "fixtures" / "field_workers.json",
        ]
        self.assertEqual([str(path) for path in required if not path.exists()], [])
        self.assertGreater(len(self.cases), 0)
        self.assertGreater(len(self.assignments), 0)
        self.assertGreater(len(self.workers), 0)

    def test_worker_safe_case_allowlist_excludes_private_content(self) -> None:
        assignment = self.assignments[0]
        case = next(row for row in self.cases if row["case_id"] == assignment["case_id"])
        safe = worker_safe_case(case, assignment)
        self.assertEqual(list(safe), FIELD_ALLOWLIST)
        self.assertTrue(PRIVATE_KEYS.isdisjoint(safe))
        rendered = json.dumps(safe, ensure_ascii=False)
        self.assertIsNone(re.search(r"(?:\+?\d[\s-]?){10,}", rendered))
        self.assertNotIn("Synthetic", rendered)

    def test_worker_authorization_uses_assignment_candidates(self) -> None:
        worker = next(row for row in self.workers if row["worker_id"] == "worker-alpha-boat")
        authorized_zones = set(worker["authorized_zone_ids"])
        assigned_case_ids = {
            row["case_id"]
            for row in self.assignments
            if (row.get("candidate_worker_id") or row.get("worker_id")) == worker["worker_id"]
        }
        visible = [
            row
            for row in self.cases
            if row["case_id"] in assigned_case_ids
            and row.get("operation_zone_id")
            and row["operation_zone_id"] != "unknown"
            and row["operation_zone_id"] in authorized_zones
        ]
        self.assertGreater(len(visible), 0)
        self.assertTrue(all(row["case_id"] in assigned_case_ids for row in visible))
        self.assertTrue(all(row["operation_zone_id"] in authorized_zones for row in visible))

    def test_invalid_worker_cannot_fall_back_to_all_cases(self) -> None:
        worker_ids = {row["worker_id"] for row in self.workers}
        self.assertNotIn("worker-missing", worker_ids)
        visible_for_missing_worker = [
            row
            for row in self.assignments
            if (row.get("candidate_worker_id") or row.get("worker_id")) == "worker-missing"
        ]
        self.assertEqual(visible_for_missing_worker, [])

    def test_demo_audit_event_shapes_are_safe(self) -> None:
        status_event = {
            "event_id": "evt-demo-001",
            "created_at": "2026-06-28T10:00:00Z",
            "actor_worker_id": "worker-alpha-boat",
            "case_id": self.assignments[0]["case_id"],
            "event_type": "status_update",
            "new_status": "on_the_way",
            "source": "field_demo_route",
            "sync_state": "pending_sync",
        }
        contact_event = {
            "event_id": "evt-contact-001",
            "created_at": "2026-06-28T10:00:00Z",
            "actor_worker_id": "worker-alpha-boat",
            "case_id": self.assignments[0]["case_id"],
            "event_type": "contact_attempt_created",
            "contact_mode": "masked_relay_stub",
            "private_number_revealed": False,
        }
        self.assertEqual(status_event["event_type"], "status_update")
        self.assertEqual(contact_event["private_number_revealed"], False)
        self.assertIsNone(re.search(r"(?:\+?\d[\s-]?){10,}", json.dumps([status_event, contact_event])))


if __name__ == "__main__":
    unittest.main()

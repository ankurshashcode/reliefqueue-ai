from __future__ import annotations

import json
import os
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reliefqueue.amd_quality import (
    ACTIVE_CONTEXT_LIMIT,
    WORKLOAD_COMPLETION_BUDGETS,
    ContextBudgetError,
    build_cross_case_repair_prompt,
    build_cross_case_synthesis_prompt,
    build_dossier_reasoning_ledger,
    build_dossier_repair_prompt,
    build_dossier_incident_supplement_prompt,
    dossier_incident_supplement_required,
    build_model_metadata,
    build_workload_prompt,
    cross_case_semantic_issues,
    dossier_semantic_issues,
    enforce_context_budget,
    normalize_cross_case_synthesis,
    normalize_dossier_incident_supplement,
    normalize_structured_output,
    parse_burst_input,
    reconcile_provider_dossier_outputs,
    reconcile_provider_incident_supplement,
    sanitize_text,
)
from reliefqueue import product_api

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestAmdInferenceQualityParser(unittest.TestCase):
    """amd_inference_quality parser and structured contract tests."""

    def test_blank_line_three_report_fixture_parses_exactly_three(self) -> None:
        raw = (FIXTURES / "amd_quality_burst.txt").read_text(encoding="utf-8")
        cases = parse_burst_input(raw)
        self.assertEqual(len(cases), 3)
        self.assertIn("north road blocked", cases[1].text)
        self.assertIn("patients", cases[2].text)

    def test_explicit_separator_line(self) -> None:
        cases = parse_burst_input("A\n---\nB\nwrapped\n---\nC")
        self.assertEqual([case.text for case in cases], ["A", "B\nwrapped", "C"])

    def test_json_array_strings(self) -> None:
        cases = parse_burst_input(json.dumps(["one", "two"]))
        self.assertEqual([case.id for case in cases], ["case-01", "case-02"])

    def test_json_array_objects_preserves_valid_ids(self) -> None:
        cases = parse_burst_input(json.dumps([{"id": "REPORT-001", "text": "one"}]))
        self.assertEqual(cases[0].id, "REPORT-001")

    def test_jsonl_objects(self) -> None:
        raw = '{"id":"a","text":"one"}\n{"id":"b","text":"two"}'
        self.assertEqual([case.id for case in parse_burst_input(raw)], ["a", "b"])

    def test_rejects_more_than_24(self) -> None:
        with self.assertRaises(ValueError):
            parse_burst_input(json.dumps(["x"] * 25))

    def test_rejects_mixed_jsonl_plain_text(self) -> None:
        with self.assertRaises(ValueError):
            parse_burst_input('{"id":"a","text":"one"}\nplain text')


class TestAmdInferenceQualityContracts(unittest.TestCase):
    """amd_inference_quality provenance, budget, nonce and metadata tests."""

    def test_budget_allows_known_single_budget(self) -> None:
        budget = enforce_context_budget("short synthetic report", 1200)
        self.assertEqual(budget["requested_completion_tokens"], 1200)
        self.assertFalse(budget["silent_truncation_allowed"])

    def test_budget_rejects_oversize_without_truncating(self) -> None:
        with self.assertRaises(ContextBudgetError):
            enforce_context_budget("x" * 40000, 3000)

    def test_prompt_binds_nonce_and_requires_echo(self) -> None:
        messages = build_workload_prompt("single", "synthetic report", "JUDGE", "abc123")
        payload = json.loads(messages[-1]["content"])
        self.assertEqual(payload["challenge_nonce"], "abc123")
        self.assertEqual(payload["output_contract"]["challenge_nonce"], "abc123")
        self.assertIn("Echo challenge_nonce exactly", messages[0]["content"])

    def test_invalid_provider_json_is_explicit_local_fallback(self) -> None:
        structured, warnings, source = normalize_structured_output(
            "single",
            "not-json",
            "17 maybe 21 people, two wheelchair users, transformer hazard",
            "JUDGE",
        )
        self.assertEqual(source, "local_safe_fallback")
        self.assertTrue(warnings)
        self.assertTrue(structured["human_review_required"])
        self.assertIn("Local deterministic fallback", " ".join(structured["confidence_notes"]))

    def test_valid_provider_json_is_not_filled_with_local_reasoning(self) -> None:
        payload = {
            "challenge_nonce": "nonce-1",
            "situation_summary": "Provider summary",
            "recommended_priorities": [],
            "route_and_access_analysis": [],
            "human_review_required": True,
        }
        structured, warnings, source = normalize_structured_output("single", json.dumps(payload), "fallback text", "JUDGE")
        self.assertEqual(source, "provider_incomplete")
        self.assertEqual(structured["situation_summary"], "Provider summary")
        self.assertEqual(structured["recommended_priorities"], [])
        self.assertTrue(any("omitted core fields" in warning for warning in warnings))

    def test_cross_case_fallback_is_explicit(self) -> None:
        structured, warnings, source = normalize_cross_case_synthesis("not-json", [{"case_id": "A", "sanitized_input": "medical"}])
        self.assertEqual(source, "local_safe_fallback")
        self.assertTrue(warnings)
        self.assertIn("not AMD-generated", json.dumps(structured))

    def test_cross_case_prompt_binds_nonce(self) -> None:
        messages = build_cross_case_synthesis_prompt([{"case_id": "A", "structured_output": {"situation_summary": "x"}}], "nonce-x")
        payload = json.loads(messages[-1]["content"])
        self.assertEqual(payload["challenge_nonce"], "nonce-x")
        self.assertEqual(payload["output_contract"]["workload_mode"], "cross_case_synthesis")

    def test_metadata_does_not_claim_unreported_underlying_model(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            metadata = build_model_metadata(served_model="reliefqueue-amd", served_model_from_provider=False)
        self.assertEqual(metadata["served_model"], "reliefqueue-amd")
        self.assertIsNone(metadata["underlying_model"])
        self.assertFalse(metadata["underlying_model_reported"])
        self.assertEqual(metadata["metadata_source"], "backend_deployment_config")

    def test_metadata_uses_explicit_underlying_model_config(self) -> None:
        with patch.dict(os.environ, {"OPENAI_COMPAT_UNDERLYING_MODEL": "Qwen/Qwen2.5-72B-Instruct"}, clear=True):
            metadata = build_model_metadata(served_model="reliefqueue-amd")
        self.assertEqual(metadata["underlying_model"], "Qwen/Qwen2.5-72B-Instruct")
        self.assertTrue(metadata["underlying_model_reported"])

    def test_metadata_marks_served_model_provider_source_only_when_reported(self) -> None:
        metadata = build_model_metadata(served_model="reliefqueue-amd", served_model_from_provider=True)
        self.assertIn("provider_response:served_model", metadata["metadata_source"])

    def test_dossier_ledger_lists_all_reports_and_minimums(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
        ledger = build_dossier_reasoning_ledger(source)
        self.assertEqual(ledger["source_report_count"], 20)
        self.assertEqual(ledger["expected_report_ids"][0], "REPORT-001")
        self.assertEqual(ledger["expected_report_ids"][-1], "REPORT-020")
        self.assertGreaterEqual(ledger["minimum_output_counts"]["consolidated_incidents"], 5)
        self.assertEqual(ledger["minimum_output_counts"]["contradictions"], 1)
        self.assertGreaterEqual(
            ledger["minimum_output_counts"]["conflict_resolution_observations"],
            3,
        )
        self.assertGreaterEqual(ledger["minimum_output_counts"]["calculation_checks"], 2)
        candidates = ledger["calculation_candidates"]
        self.assertEqual(len(candidates), 3)
        rendered = json.dumps(candidates, sort_keys=True)
        self.assertIn('"result": 24', rendered)
        self.assertIn('"before_reconciliation": 7', rendered)
        self.assertIn('"if_all_possible_duplicates_confirmed": 5', rendered)
        self.assertIn("effective capacity 33", rendered)
        self.assertIn(["REPORT-001", "REPORT-003"], ledger["explicit_duplicate_pairs"])
        self.assertIn(["REPORT-013", "REPORT-014"], ledger["explicit_duplicate_pairs"])
        location_map = {
            item["source_id"]: item["locations"]
            for item in ledger["location_anchors"]
        }
        self.assertIn("old bus stand", location_map["REPORT-001"])
        self.assertIn("old pump house", location_map["REPORT-014"])

    def test_poor_live_dossier_is_semantically_incomplete(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
        poor = {
            "source_report_count": 20,
            "source_coverage": [],
            "uncovered_source_ids": [],
            "consolidated_incidents": [{}, {}, {}],
            "contradictions": [{}],
            "prioritized_operational_plan": [_priority(1), _priority(2), _priority(3), _priority(4)],
            "calculation_checks": [],
            "human_review_required": True,
        }
        issues = dossier_semantic_issues(poor, source)
        joined = " | ".join(issues)
        self.assertIn("source_coverage missing", joined)
        self.assertIn("consolidated_incidents requires at least 5", joined)
        self.assertIn(
            "conflict_resolution_observations requires at least 3", joined
        )
        self.assertIn("calculation_checks requires at least 2", joined)
        self.assertIn("REPORT-020", joined)

    def test_dossier_rejects_cross_location_merge_unverified_count_and_unsupported_gaps(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
        record = {
            "source_report_count": 20,
            "source_coverage": [
                {"source_id": f"REPORT-{index:03d}"}
                for index in range(1, 21)
            ],
            "uncovered_source_ids": [],
            "consolidated_incidents": [
                {
                    "source_ids": ["REPORT-001", "REPORT-014"],
                    "people_range": "4-14 people",
                },
                {
                    "source_ids": ["REPORT-006", "REPORT-007"],
                    "people_range": "200 people",
                },
                {}, {}, {},
            ],
            "contradictions": [{}, {}, {}],
            "unverified_claims": [
                {
                    "source_ids": ["REPORT-006"],
                    "claim": "Unverified claim says 200 people are trapped.",
                }
            ],
            "resource_gaps": [
                "oxygen cylinders needed",
                "additional wheelchairs needed",
                "additional high-clearance truck needed",
            ],
            "prioritized_operational_plan": [
                _priority(1), _priority(2), _priority(3), _priority(4), _priority(5)
            ],
            "calculation_checks": [],
            "human_review_required": True,
        }
        issues = dossier_semantic_issues(record, source)
        joined = " | ".join(issues)
        self.assertIn("distinct explicit locations: REPORT-001, REPORT-014", joined)
        self.assertIn("unverified 200-person claim appears as a confirmed people range", joined)
        self.assertIn("unsupported oxygen cylinders shortage", joined)
        self.assertIn("unsupported wheelchairs shortage", joined)
        self.assertIn("unsupported high-clearance truck shortage", joined)

    def test_dossier_source_coverage_rejects_duplicate_rows(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
        ledger = build_dossier_reasoning_ledger(source)
        coverage = [
            {
                "source_id": source_id,
                "disposition": "incident",
                "linked_incident_id": f"incident-{index:02d}",
                "notes": "covered",
            }
            for index, source_id in enumerate(ledger["expected_report_ids"], start=1)
        ]
        coverage.append(dict(coverage[0]))
        record = {
            "source_report_count": 20,
            "source_coverage": coverage,
            "uncovered_source_ids": [],
            "consolidated_incidents": [{}, {}, {}, {}, {}],
            "contradictions": [{}, {}, {}],
            "prioritized_operational_plan": [
                _priority(1), _priority(2), _priority(3), _priority(4), _priority(5)
            ],
            "calculation_checks": ledger["calculation_candidates"],
            "confidence_notes": json.dumps(ledger["preservation_anchors"]),
            "human_review_required": True,
        }
        issues = dossier_semantic_issues(record, source)
        self.assertTrue(any("source_coverage repeats IDs" in issue for issue in issues))
        self.assertTrue(any("source_coverage must contain exactly 20 rows" in issue for issue in issues))

    def test_cross_case_rejects_waiting_on_insulin_shortfall(self) -> None:
        cases = [
            {
                "case_id": "live-burst-3",
                "sanitized_input": "Clinic has 12 insulin doses for 19 patients.",
            }
        ]
        synthesis = {
            "challenge_nonce": "n",
            "inventory_conflicts": [],
            "cases_that_can_wait_with_reason": [
                {"case_id": "live-burst-3", "reason": "supplier can be contacted"}
            ],
            "human_review_required": True,
        }
        issues = cross_case_semantic_issues(synthesis, cases)
        joined = " | ".join(issues)
        self.assertIn("cannot be marked safe-to-wait", joined)
        self.assertIn("12 insulin doses versus 19 patients", joined)


    def test_sanitizer_preserves_report_dates_and_times(self) -> None:
        source = (
            "[REPORT-001 | 2026-07-11 09:04 | SMS] "
            "Call +91 98765 43210 before 08:30."
        )
        sanitized = sanitize_text(source)
        self.assertIn("2026-07-11 09:04", sanitized)
        self.assertIn("08:30", sanitized)
        self.assertIn("[phone-redacted]", sanitized)
        self.assertNotIn("98765", sanitized)


    def test_dossier_initial_and_repair_prompts_fit_active_context(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
        initial = build_workload_prompt("complex_dossier", source, "JUDGE", "nonce-initial")
        initial_budget = enforce_context_budget(
            initial[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
        )
        self.assertLessEqual(
            initial_budget["estimated_total_tokens"],
            ACTIVE_CONTEXT_LIMIT,
        )
        initial_payload = json.loads(initial[-1]["content"])
        self.assertIn("source_reports", initial_payload)
        self.assertNotIn("reports", initial_payload["source_ledger"])

        poor = {
            "source_report_count": 20,
            "consolidated_incidents": [{}, {}, {}],
            "contradictions": [{}],
            "prioritized_operational_plan": [_priority(1)],
            "human_review_required": True,
        }
        issues = dossier_semantic_issues(poor, source)
        repair = build_dossier_repair_prompt(source, poor, issues, "nonce-repair")
        repair_budget = enforce_context_budget(
            repair[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"],
        )
        self.assertLessEqual(
            repair_budget["estimated_total_tokens"],
            ACTIVE_CONTEXT_LIMIT,
        )
        repair_payload = json.loads(repair[-1]["content"])
        self.assertIsInstance(repair_payload["deterministic_semantic_issues"], dict)
        self.assertNotIn("reports", repair_payload["source_ledger"])

    def test_cross_case_repair_prompt_fits_active_context(self) -> None:
        cases = [
            {
                "case_id": "case-01",
                "sanitized_input": "9 people need water",
                "structured_output": {"situation_summary": "9 people need water"},
            },
            {
                "case_id": "case-02",
                "sanitized_input": "wheelchair user, north road blocked",
                "structured_output": {"situation_summary": "wheelchair evacuation"},
            },
            {
                "case_id": "case-03",
                "sanitized_input": "12 insulin doses for 19 patients",
                "structured_output": {"situation_summary": "insulin shortage"},
            },
        ]
        previous = {
            "cases_that_can_wait_with_reason": [{"case_id": "case-03", "reason": "supplier"}],
            "inventory_conflicts": [],
        }
        issues = cross_case_semantic_issues(previous, cases)
        repair = build_cross_case_repair_prompt(cases, previous, issues, "nonce-repair")
        budget = enforce_context_budget(repair[-1]["content"], 1400)
        self.assertLessEqual(budget["estimated_total_tokens"], 8192)



class FakeAdapter:
    def __init__(
        self,
        invalid: bool = False,
        *,
        dossier_incomplete_first: bool = False,
        synthesis_unsafe_first: bool = False,
    ) -> None:
        self.invalid = invalid
        self.dossier_incomplete_first = dossier_incomplete_first
        self.synthesis_unsafe_first = synthesis_unsafe_first
        self.calls: list[dict[str, object]] = []
        self._lock = threading.Lock()
        self._counter = 0

    def _complete_dossier(self, nonce: str, payload: dict[str, object]) -> dict[str, object]:
        ledger = payload.get("source_ledger") if isinstance(payload.get("source_ledger"), dict) else {}
        reports = ledger.get("reports") if isinstance(ledger, dict) else []
        if not isinstance(reports, list):
            reports = []
        expected_ids = ledger.get("expected_report_ids") if isinstance(ledger, dict) else []
        if not isinstance(expected_ids, list):
            expected_ids = []
        report_ids = [
            str(value)
            for value in expected_ids
            if value
        ] or [
            str(row.get("source_id"))
            for row in reports
            if isinstance(row, dict) and row.get("source_id")
        ]
        contract = (
            payload.get("output_contract")
            if isinstance(payload.get("output_contract"), dict)
            else {}
        )
        source_evidence_index = (
            contract.get("source_evidence_index")
            if isinstance(contract, dict)
            else []
        )
        if not isinstance(source_evidence_index, list):
            source_evidence_index = []
        preserved_source_text = [
            " ".join(
                [
                    str(item.get("source_id") or ""),
                    *[str(value) for value in item.get("terms") or []],
                    *[str(value) for value in item.get("numbers") or []],
                ]
            )
            for item in source_evidence_index
            if isinstance(item, dict)
        ]
        coverage = [
            {
                "source_id": source_id,
                "disposition": "incident",
                "linked_incident_id": f"incident-{index:02d}",
                "notes": next(
                    (
                        str(row.get("text") or "")
                        for row in reports
                        if isinstance(row, dict) and row.get("source_id") == source_id
                    ),
                    "source covered",
                ),
            }
            for index, source_id in enumerate(report_ids, start=1)
        ]
        incidents = [
            {
                "incident_id": f"incident-{index:02d}",
                "source_ids": [source_id],
                "evidence": ["source-grounded evidence"],
                "latest_update": "latest source timestamp retained",
                "location": f"location-{index}",
                "needs": ["coordinator review"],
                "people_range": "source count retained",
                "vulnerable_groups": [],
                "urgency_rationale": "source-grounded",
                "missing_fields": [],
                "confidence": "medium",
            }
            for index, source_id in enumerate(report_ids[:5], start=1)
        ]
        return {
            "schema_version": "reliefqueue-dossier-analysis/v2",
            "workload_mode": "complex_dossier",
            "challenge_nonce": nonce,
            "situation_summary": "Dossier summary with complete source coverage.",
            "source_report_count": len(report_ids),
            "source_coverage": coverage,
            "uncovered_source_ids": [],
            "source_evidence_index": source_evidence_index,
            "consolidated_incidents": incidents,
            "duplicate_clusters": [
                {"source_ids": report_ids[:2], "reason": "source-grounded duplicate review"}
            ],
            "contradictions": [
                {"source_ids": report_ids[:2], "conflict": "count/status conflict", "working_assumption": "verify latest"},
                {"source_ids": report_ids[2:4], "conflict": "route/status conflict", "working_assumption": "use verified update"},
                {"source_ids": report_ids[4:6], "conflict": "location/capacity conflict", "working_assumption": "retain latest"},
            ],
            "superseded_updates": [
                {
                    "older_source_id": report_ids[0] if report_ids else "REPORT-001",
                    "newer_source_id": report_ids[-1] if report_ids else "REPORT-020",
                    "change": "later verified update retained",
                }
            ],
            "unverified_claims": [
                {
                    "source_ids": ["REPORT-006"],
                    "claim": "Unverified source claim says 200 people may be trapped.",
                    "verification_needed": "Confirm source and people count before treating it as fact.",
                }
            ],
            "people_count_ranges": preserved_source_text,
            "resource_gaps": [
                "12 insulin doses versus 19 patients: shortfall 7 before duplicate reconciliation"
            ],
            "capacity_pressure": [
                "Community Hall safe capacity 43 versus 67 registered: overflow 24"
            ],
            "calculation_checks": [
                {
                    "label": "School shelter effective capacity",
                    "source_ids": ["REPORT-009"],
                    "inputs": ["capacity 45", "12 unusable beds", "41 registered"],
                    "formula": "45 - 12 = 33; 41 - 33",
                    "result": "effective capacity 33; overflow 8",
                },
                {
                    "label": "Community Hall overflow",
                    "source_ids": ["REPORT-020"],
                    "inputs": ["67 registered", "43 safe capacity", "previous capacity 80"],
                    "formula": "67 - 43",
                    "result": "67 - 43 = 24 people above safe capacity",
                },
                {
                    "label": "Insulin shortfall range",
                    "source_ids": ["REPORT-011"],
                    "inputs": ["19 patients", "12 doses", "up to 2 duplicates"],
                    "formula": "19 - 12; (19 - 2) - 12",
                    "result": "shortfall 7 before reconciliation; minimum 5 if both duplicates confirmed",
                },
            ],
            "route_constraints": preserved_source_text,
            "cross_incident_dependencies": [
                "wheelchair-ramp van, oxygen-reserved van, small-van water access and bridge restrictions require sequencing"
            ],
            "do_not_merge_notes": [
                "Keep distinct locations separate unless source evidence supports a duplicate cluster"
            ],
            "prioritized_operational_plan": [
                _priority(1), _priority(2), _priority(3), _priority(4), _priority(5)
            ],
            "missing_information_questions": ["Confirm duplicates and current locations"],
            "coordinator_review_gates": ["No automatic dispatch"],
            "confidence_notes": preserved_source_text,
            "warnings": ["Human review required"],
            "quality_self_check": {
                "all_sources_covered": True,
                "numeric_facts_preserved": True,
                "unsupported_resource_gaps_avoided": True,
                "later_updates_preserved": True,
            },
            "human_review_required": True,
        }

    def _complete_cross_case(self, nonce: str) -> dict[str, object]:
        return {
            "challenge_nonce": nonce,
            "highest_risk_cases": [
                {"case_id": "live-burst-3", "reason": "12 insulin doses for 19 patients creates a medication shortfall"},
                {"case_id": "live-burst-2", "reason": "wheelchair evacuation with a blocked road"},
            ],
            "resource_competition": ["accessible transport and medical delivery compete for vehicles"],
            "shared_route_bottlenecks": ["south lane"],
            "possible_duplicate_cases": [],
            "inventory_conflicts": ["insulin: 12 doses versus 19 patients, shortfall 7 before reconciliation"],
            "suggested_sequence": [_priority(1), _priority(2), _priority(3)],
            "cases_that_can_wait_with_reason": [
                {"case_id": "live-burst-1", "reason": "water need still requires prompt review but lacks a stated medical emergency"}
            ],
            "missing_facts_that_could_change_order": ["confirm duplicate insulin patients"],
            "aggregate_resource_implications": ["reserve accessible transport and secure insulin supply"],
            "coordinator_review_gates": ["human approval"],
            "human_review_required": True,
        }

    def complete_messages(self, messages, *, max_tokens, response_format="json_object"):
        payload = json.loads(messages[-1]["content"])
        mode = payload.get("workload_mode") or payload.get("output_contract", {}).get("workload_mode")
        nonce = payload["challenge_nonce"]
        with self._lock:
            self._counter += 1
            request_id = f"req-{self._counter}"
            self.calls.append({"mode": mode, "nonce": nonce, "max_tokens": max_tokens, "messages": messages})
            call_number = self._counter
        if self.invalid:
            content = "not-json"
        elif mode == "complex_dossier" and self.dossier_incomplete_first:
            content = json.dumps(
                {
                    "challenge_nonce": nonce,
                    "situation_summary": "Incomplete dossier summary.",
                    "source_report_count": 20,
                    "consolidated_incidents": [{"source_ids": ["REPORT-001"]}],
                    "prioritized_operational_plan": [_priority(1)],
                    "human_review_required": True,
                }
            )
        elif mode in {"complex_dossier", "complex_dossier_repair"}:
            content = json.dumps(self._complete_dossier(nonce, payload))
        elif mode == "cross_case_synthesis" and self.synthesis_unsafe_first:
            content = json.dumps(
                {
                    "challenge_nonce": nonce,
                    "highest_risk_cases": [{"case_id": "live-burst-2", "reason": "evacuation"}],
                    "resource_competition": ["transport"],
                    "shared_route_bottlenecks": ["south lane"],
                    "possible_duplicate_cases": [],
                    "inventory_conflicts": [],
                    "suggested_sequence": [_priority(1)],
                    "cases_that_can_wait_with_reason": [
                        {"case_id": "live-burst-3", "reason": "supplier can be contacted"}
                    ],
                    "missing_facts_that_could_change_order": ["supplier ETA"],
                    "aggregate_resource_implications": ["transport"],
                    "coordinator_review_gates": ["human approval"],
                    "human_review_required": True,
                }
            )
        elif mode in {"cross_case_synthesis", "cross_case_synthesis_repair"}:
            content = json.dumps(self._complete_cross_case(nonce))
        else:
            content = json.dumps(
                {
                    "challenge_nonce": nonce,
                    "situation_summary": "17 people, possibly 21; two wheelchair users; water lasts six hours.",
                    "critical_facts": ["east road blocked by transformer", "west route small vehicles only"],
                    "contradictions": ["17 versus 21 people"],
                    "risk_escalators": ["wheelchair", "six-hour water window"],
                    "recommended_priorities": [_priority(1), _priority(2), _priority(3)],
                    "resource_implications": ["wheelchair-ramp vehicle and water supply"],
                    "route_and_access_analysis": ["avoid transformer exclusion zone; verify west route"],
                    "missing_information": ["confirm people count"],
                    "coordinator_questions": ["Is utility isolation confirmed?", "Which accessible vehicle fits west route?"],
                    "public_reply_draft": "Coordinator review pending.",
                    "confidence_notes": ["synthetic"],
                    "warnings": ["no automatic dispatch"],
                    "human_review_required": True,
                }
            )
        return {
            "status": "ok",
            "verified_live": True,
            "fallback_used": False,
            "provider": "AMD Developer Cloud",
            "runtime": "vLLM",
            "accelerator": "AMD Instinct MI300X",
            "served_model": "reliefqueue-amd",
            "underlying_model": None,
            "request_id": request_id,
            "latency_ms": 5,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "raw_content": content,
            "generated_advisory": content,
            "warnings": [],
            "error": None,
            "finish_reason": "stop",
            "request_settings": {"max_tokens": max_tokens},
        }



def _priority(rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "action": f"Action {rank}",
        "reason": "Reason",
        "dependency": "Coordinator approval",
        "verify_before_action": "Verify facts",
    }


class TestAmdInferenceQualityProductBoundary(unittest.TestCase):
    """amd_inference_quality truthfulness and provider-synthesis tests."""

    def test_invalid_provider_output_cannot_be_verified_live(self) -> None:
        adapter = FakeAdapter(invalid=True)
        result = product_api._structured_workload_verification(adapter, "synthetic incident", "single", "JUDGE")
        self.assertFalse(result["verified_live"])
        self.assertTrue(result["provider_transport_verified_live"])
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["analysis_source"], "local_safe_fallback")
        self.assertTrue(result["nonce_sent_to_provider"])
        self.assertFalse(result["nonce_echoed_by_provider"])

    def test_valid_provider_output_is_nonce_bound(self) -> None:
        adapter = FakeAdapter()
        result = product_api._structured_workload_verification(adapter, (FIXTURES / "amd_quality_single.txt").read_text(), "single", "JUDGE")
        self.assertTrue(result["verified_live"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["analysis_source"], "provider")
        self.assertTrue(result["verification_bound_to_nonce"])
        self.assertEqual(result["challenge_nonce"], adapter.calls[0]["nonce"])

    def test_burst_uses_real_fourth_provider_call_for_cross_case_synthesis(self) -> None:
        adapter = FakeAdapter()
        config = SimpleNamespace(mode="openai_compatible", model="reliefqueue-amd")
        reports = [
            {"id": "live-burst-1", "text": "9 people need drinking water near Clock Tower."},
            {"id": "live-burst-2", "text": "Wheelchair user; north road blocked, south lane open."},
            {"id": "live-burst-3", "text": "Clinic has 12 insulin doses for 19 patients."},
        ]
        with patch.object(product_api.AIConfig, "from_env", return_value=config), patch.object(product_api, "OpenAICompatibleAdapter", return_value=adapter):
            result = product_api.burst_verification({"concurrency": 1, "reports": reports})
        self.assertEqual(result["submitted"], 3)
        self.assertEqual(result["parsed"], 3)
        self.assertEqual(result["provider_call_count"], 4)
        self.assertEqual([call["mode"] for call in adapter.calls], ["burst_case", "burst_case", "burst_case", "cross_case_synthesis"])
        self.assertTrue(result["cross_case_evidence"]["verified_live"])
        self.assertEqual(result["cross_case_evidence"]["analysis_source"], "provider")
        self.assertTrue(result["verified_live"])
        nonces = [str(call["nonce"]) for call in adapter.calls]
        self.assertEqual(len(set(nonces)), 4)

    def test_incomplete_dossier_gets_one_provider_repair_pass(self) -> None:
        adapter = FakeAdapter(dossier_incomplete_first=True)
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
        result = product_api._structured_workload_verification(
            adapter,
            source,
            "complex_dossier",
            "JUDGE-DOSSIER",
        )
        self.assertEqual([call["mode"] for call in adapter.calls], [
            "complex_dossier",
            "complex_dossier_repair",
        ])
        self.assertEqual(result["provider_call_count"], 2)
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_succeeded"])
        self.assertTrue(result["semantic_completeness"])
        self.assertEqual(result["semantic_issues"], [])
        self.assertTrue(result["verified_live"])
        self.assertEqual(len(result["provider_request_ids"]), 2)
        self.assertEqual(result["provider_total_tokens"], 60)
        self.assertEqual(result["deterministic_prompt_support"]["source_report_count"], 20)
        self.assertEqual(result["deterministic_prompt_support"]["calculation_candidate_count"], 3)
        self.assertEqual(result["deterministic_prompt_support"]["final_analysis_source"], "provider")

    def test_unsafe_cross_case_synthesis_gets_one_provider_repair_pass(self) -> None:
        adapter = FakeAdapter(synthesis_unsafe_first=True)
        config = SimpleNamespace(mode="openai_compatible", model="reliefqueue-amd")
        reports = [
            {"id": "live-burst-1", "text": "9 people need drinking water near Clock Tower."},
            {"id": "live-burst-2", "text": "Wheelchair user; north road blocked, south lane open."},
            {"id": "live-burst-3", "text": "Clinic has 12 insulin doses for 19 patients."},
        ]
        with patch.object(product_api.AIConfig, "from_env", return_value=config), patch.object(
            product_api,
            "OpenAICompatibleAdapter",
            return_value=adapter,
        ):
            result = product_api.burst_verification(
                {"concurrency": 1, "reports": reports}
            )
        self.assertEqual(
            [call["mode"] for call in adapter.calls],
            [
                "burst_case",
                "burst_case",
                "burst_case",
                "cross_case_synthesis",
                "cross_case_synthesis_repair",
            ],
        )
        self.assertEqual(result["provider_call_count"], 5)
        self.assertEqual(result["synthesis_call_count"], 2)
        self.assertTrue(result["cross_case_evidence"]["repair_attempted"])
        self.assertTrue(result["cross_case_evidence"]["repair_succeeded"])
        self.assertTrue(result["cross_case_evidence"]["semantic_completeness"])
        self.assertTrue(result["verified_live"])
        self.assertEqual(result["provider_total_tokens"], 150)



if __name__ == "__main__":
    unittest.main()

# BEGIN RELIEFQUEUE AMD BURST CONTRACT REPAIR PART 1 TESTS
class TestAmdBurstContractRepairPart1(unittest.TestCase):
    def test_output_contract_envelope_is_flattened_without_local_synthesis(self):
        import json
        from unittest.mock import patch
        import reliefqueue.amd_quality as quality

        nested = {
            "schema_version": "reliefqueue-burst-case-analysis/v1",
            "workload_mode": "burst_case",
            "case_id": "case-01",
            "challenge_nonce": "nonce-01",
            "situation_summary": "Nine people need drinking water.",
            "critical_facts": ["Nine people need drinking water."],
            "contradictions": [],
            "risk_escalators": ["Water is unavailable."],
            "recommended_priorities": [{"rank": 1, "action": "Verify water access."}],
            "resource_implications": ["Drinking water may be required."],
            "route_and_access_analysis": ["Confirm access to Clock Tower."],
            "missing_information": ["Exact location."],
            "coordinator_questions": ["Where is the group?"],
            "confidence_notes": ["Synthetic input."],
            "warnings": ["Coordinator review required."],
            "human_review_required": True,
        }
        raw = json.dumps({
            "workload_mode": "burst_case",
            "case_id": "case-01",
            "challenge_nonce": "nonce-01",
            "output_contract": nested,
        })
        with patch.object(
            quality,
            "_PART1_ORIGINAL_NORMALIZE_STRUCTURED_OUTPUT",
            return_value=(nested, [], "provider"),
        ) as original:
            structured, warnings, source = quality.normalize_structured_output(
                "burst_case", raw, "synthetic report", "case-01"
            )

        canonical = json.loads(original.call_args.args[1])
        self.assertNotIn("output_contract", canonical)
        self.assertEqual(canonical["challenge_nonce"], "nonce-01")
        self.assertEqual(structured, nested)
        self.assertEqual(source, "provider")
        self.assertTrue(any("without local synthesis" in warning for warning in warnings))

    def test_explicit_empty_cross_case_lists_are_valid_negative_evidence(self):
        from unittest.mock import patch
        import reliefqueue.amd_quality as quality

        structured = {
            "schema_version": "reliefqueue-cross-case-synthesis/v1",
            "workload_mode": "cross_case_synthesis",
            "challenge_nonce": "nonce-synthesis",
            "highest_risk_cases": [{"case_id": "case-03", "reason": "Insulin shortfall"}],
            "resource_competition": [],
            "shared_route_bottlenecks": [],
            "possible_duplicate_cases": [],
            "inventory_conflicts": ["12 insulin doses versus 19 patients"],
            "suggested_sequence": [{"rank": 1, "action": "Review insulin shortfall"}],
            "cases_that_can_wait_with_reason": [{"case_id": "case-01", "reason": "Lower immediate risk"}],
            "missing_facts_that_could_change_order": ["Updated clinic inventory"],
            "aggregate_resource_implications": ["Insulin shortfall requires review"],
            "coordinator_review_gates": ["Confirm inventory before action"],
            "human_review_required": True,
        }
        warning = "Provider cross-case JSON omitted core fields: resource_competition. Missing sections are empty, not locally invented."
        with patch.object(
            quality,
            "_PART1_ORIGINAL_NORMALIZE_CROSS_CASE_SYNTHESIS",
            return_value=(structured, [warning], "provider_incomplete"),
        ), patch.object(quality, "cross_case_semantic_issues", return_value=[]):
            result, warnings, source = quality.normalize_cross_case_synthesis("{}", [])

        self.assertEqual(result, structured)
        self.assertEqual(source, "provider")
        self.assertFalse(any("omitted core fields" in item for item in warnings))
        self.assertTrue(any("negative findings" in item for item in warnings))
# END RELIEFQUEUE AMD BURST CONTRACT REPAIR PART 1 TESTS

# BEGIN RELIEFQUEUE AMD DOSSIER COMPLETION REPAIR PART 2 TESTS
class TestAmdDossierCompletionRepairPart2(unittest.TestCase):
    def test_live_evidence_driven_dossier_budgets_exceed_truncated_ceilings(self) -> None:
        self.assertGreater(
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
            3000,
        )
        self.assertGreater(
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"],
            2800,
        )

    def test_compact_dossier_prompt_preserves_context_headroom(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        initial = build_workload_prompt(
            "complex_dossier",
            source,
            "JUDGE-DOSSIER",
            "nonce-initial",
        )
        initial_payload = json.loads(initial[-1]["content"])
        initial_budget = enforce_context_budget(
            initial[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
        )
        self.assertLessEqual(
            initial_budget["estimated_total_tokens"],
            ACTIVE_CONTEXT_LIMIT,
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT - initial_budget["estimated_total_tokens"],
            300,
        )
        coverage_schema = initial_payload["output_contract"]["source_coverage"][0]
        self.assertEqual(
            list(coverage_schema),
            ["source_id", "disposition", "linked_incident_id"],
        )
        self.assertTrue(
            initial_payload["compact_output_rules"][
                "source_coverage_notes_forbidden"
            ]
        )
        self.assertIn("never inside output_contract", initial[0]["content"])
        self.assertNotIn(', "case_id"', initial[-1]["content"])

    def test_compact_repair_prompt_preserves_context_headroom(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        previous = {
            "situation_summary": "Provider output truncated.",
            "source_report_count": 20,
            "consolidated_incidents": [{"source_ids": ["REPORT-001"]}],
            "prioritized_operational_plan": [_priority(1)],
            "human_review_required": True,
        }
        issues = dossier_semantic_issues(previous, source)
        repair = build_dossier_repair_prompt(
            source,
            previous,
            issues,
            "nonce-repair",
        )
        repair_payload = json.loads(repair[-1]["content"])
        repair_budget = enforce_context_budget(
            repair[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"],
        )
        self.assertLessEqual(
            repair_budget["estimated_total_tokens"],
            ACTIVE_CONTEXT_LIMIT,
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT - repair_budget["estimated_total_tokens"],
            300,
        )
        self.assertTrue(
            repair_payload["compact_output_rules"][
                "source_coverage_notes_forbidden"
            ]
        )
        self.assertNotIn(', "challenge_nonce"', repair[-1]["content"])
# END RELIEFQUEUE AMD DOSSIER COMPLETION REPAIR PART 2 TESTS

# BEGIN RELIEFQUEUE AMD DOSSIER EXACT-TARGET REPAIR PART 3 TESTS
class TestAmdDossierExactTargetRepairPart3(unittest.TestCase):
    def test_repair_prompt_preserves_exact_missing_terms_and_numbers(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        issues = [
            "contradictions requires at least 3 items, got 1",
            "REPORT-016 missing required terms: wheelchair, oxygen",
            "REPORT-019 missing required terms: transformer, utility isolation",
            "REPORT-019 missing required numbers: 50",
            "REPORT-006 unverified 200-person claim appears as a confirmed people range",
            "calculation_checks missing source-linked row for safe-capacity overflow",
        ]
        repair = build_dossier_repair_prompt(
            source,
            {"situation_summary": "Do not anchor the rewrite to this output."},
            issues,
            "nonce-part3",
        )
        payload = json.loads(repair[-1]["content"])
        exact = payload["deterministic_semantic_issues"]
        self.assertEqual(
            exact["missing_by_source"]["REPORT-016"]["terms"],
            ["wheelchair", "oxygen"],
        )
        self.assertEqual(
            exact["missing_by_source"]["REPORT-019"]["terms"],
            ["transformer", "utility isolation"],
        )
        self.assertEqual(
            exact["missing_by_source"]["REPORT-019"]["numbers"],
            ["50"],
        )
        self.assertNotIn("previous_provider_output_summary", payload)
        self.assertIn("unverified 200-person", json.dumps(exact))

    def test_prompt_support_includes_calculation_inputs_and_conflict_candidates(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        prompt = build_workload_prompt(
            "complex_dossier",
            source,
            "JUDGE-DOSSIER",
            "nonce-part3-initial",
        )
        payload = json.loads(prompt[-1]["content"])
        ledger = payload["source_ledger"]
        safe_capacity = next(
            item
            for item in ledger["calculation_candidates"]
            if item["label"] == "safe-capacity overflow"
        )
        self.assertEqual(
            safe_capacity["inputs"],
            ["previous capacity 80", "safe capacity 43", "registered 67"],
        )
        self.assertIn("REPORT-015", ledger["conflict_update_source_ids"])
        self.assertIn("REPORT-020", ledger["conflict_update_source_ids"])

    def test_part3_prompts_keep_required_context_headroom(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        initial = build_workload_prompt(
            "complex_dossier", source, "JUDGE-DOSSIER", "nonce-part3-initial"
        )
        repair = build_dossier_repair_prompt(
            source,
            {"situation_summary": "Incomplete provider output."},
            [
                "contradictions requires at least 3 items, got 1",
                "REPORT-016 missing required terms: wheelchair, oxygen",
                "REPORT-019 missing required terms: transformer, utility isolation",
                "REPORT-019 missing required numbers: 50",
                "REPORT-006 unverified 200-person claim appears as a confirmed people range",
                "calculation_checks missing source-linked row for safe-capacity overflow",
            ],
            "nonce-part3-repair",
        )
        initial_budget = enforce_context_budget(
            initial[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
        )
        repair_budget = enforce_context_budget(
            repair[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"],
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT - initial_budget["estimated_total_tokens"], 300
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT - repair_budget["estimated_total_tokens"], 300
        )
# END RELIEFQUEUE AMD DOSSIER EXACT-TARGET REPAIR PART 3 TESTS


# BEGIN RELIEFQUEUE AMD DOSSIER SOURCE-EVIDENCE REPAIR PART 4 TESTS
class TestAmdDossierSourceEvidenceRepairPart4(unittest.TestCase):
    def test_prompt_carries_exact_source_evidence_index_without_duplicate_ledger(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        initial = build_workload_prompt(
            "complex_dossier",
            source,
            "JUDGE-DOSSIER",
            "nonce-part4-initial",
        )
        payload = json.loads(initial[-1]["content"])
        index = payload["output_contract"]["source_evidence_index"]
        report_018 = next(
            row for row in index if row["source_id"] == "REPORT-018"
        )
        self.assertEqual(
            report_018["terms"],
            ["water purification", "dry food", "small van"],
        )
        self.assertEqual(report_018["numbers"], ["60", "120"])
        self.assertNotIn("preservation_anchors", payload["source_ledger"])
        self.assertNotIn("location_anchors", payload["source_ledger"])
        budget = enforce_context_budget(
            initial[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT - budget["estimated_total_tokens"],
            300,
        )

    def test_repair_prompt_retains_exact_index_and_required_headroom(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        repair = build_dossier_repair_prompt(
            source,
            {"situation_summary": "Incomplete provider output."},
            [
                "contradictions requires at least 1 items, got 0",
                "REPORT-018 missing required terms: water purification, dry food, small van",
                "REPORT-018 missing required numbers: 60, 120",
            ],
            "nonce-part4-repair",
        )
        payload = json.loads(repair[-1]["content"])
        self.assertTrue(
            payload["compact_output_rules"]["source_coverage_notes_forbidden"]
        )
        self.assertIn(
            "source_evidence_index",
            payload["output_contract"],
        )
        self.assertIn(
            "Copy output_contract.source_evidence_index exactly",
            repair[0]["content"],
        )
        budget = enforce_context_budget(
            repair[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"],
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT - budget["estimated_total_tokens"],
            300,
        )

    def test_conflict_updates_satisfy_aggregate_without_inventing_three_contradictions(self) -> None:
        source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(
            encoding="utf-8"
        )
        ledger = build_dossier_reasoning_ledger(source)
        record = FakeAdapter()._complete_dossier(
            "nonce-part4",
            {
                "source_ledger": {
                    "expected_report_ids": ledger["expected_report_ids"],
                },
                "output_contract": {
                    "source_evidence_index": [
                        {
                            "source_id": item["source_id"],
                            "terms": item["required_terms"],
                            "numbers": item["required_numbers"],
                        }
                        for item in ledger["preservation_anchors"]
                    ]
                },
            },
        )
        record["contradictions"] = record["contradictions"][:1]
        issues = dossier_semantic_issues(record, source)
        self.assertFalse(
            any(
                issue.startswith("contradictions requires at least 3")
                for issue in issues
            ),
            issues,
        )
        self.assertFalse(
            any(
                issue.startswith("conflict_resolution_observations")
                for issue in issues
            ),
            issues,
        )
        self.assertEqual(issues, [])
# END RELIEFQUEUE AMD DOSSIER SOURCE-EVIDENCE REPAIR PART 4 TESTS


# BEGIN RELIEFQUEUE AMD DOSSIER PROVIDER RECONCILIATION PART 5 TESTS
class TestAmdDossierProviderReconciliationPart5(unittest.TestCase):
    def _fixture(self) -> str:
        return (
            FIXTURES / "amd_quality_complex_dossier.txt"
        ).read_text(encoding="utf-8")

    def _captured(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def test_schema_fragment_does_not_replace_valid_top_level_result(self) -> None:
        raw = self._captured("amd_quality_dossier_part4a_repair.json")
        structured, warnings, source = normalize_structured_output(
            "complex_dossier", raw, self._fixture(), "JUDGE-DOSSIER"
        )
        self.assertEqual(source, "provider_incomplete")
        self.assertEqual(len(structured["source_coverage"]), 17)
        self.assertEqual(len(structured["consolidated_incidents"]), 5)
        self.assertEqual(len(structured["prioritized_operational_plan"]), 4)
        self.assertNotIn(
            "Provider wrapped the requested JSON in output_contract",
            " | ".join(warnings),
        )

    def test_exact_part4a_provider_calls_reconcile_without_local_analysis(self) -> None:
        fixture = self._fixture()
        initial, _, initial_source = normalize_structured_output(
            "complex_dossier",
            self._captured("amd_quality_dossier_part4a_initial.json"),
            fixture,
            "JUDGE-DOSSIER",
        )
        repair, _, repair_source = normalize_structured_output(
            "complex_dossier",
            self._captured("amd_quality_dossier_part4a_repair.json"),
            fixture,
            "JUDGE-DOSSIER",
        )
        merged, evidence = reconcile_provider_dossier_outputs(initial, repair)
        self.assertEqual(initial_source, "provider")
        self.assertEqual(repair_source, "provider_incomplete")
        self.assertEqual(dossier_semantic_issues(merged, fixture), [])
        self.assertEqual(len(merged["source_coverage"]), 20)
        self.assertGreaterEqual(len(merged["prioritized_operational_plan"]), 5)
        self.assertEqual(
            evidence["carried_source_ids"],
            ["REPORT-004", "REPORT-005", "REPORT-017"],
        )
        self.assertFalse(evidence["local_operational_conclusions_added"] )
        self.assertEqual(evidence["missing_core_fields"], [])

    def test_product_boundary_reconciles_exact_part4a_provider_shapes(self) -> None:
        class CapturedAdapter:
            def __init__(self, owner: "TestAmdDossierProviderReconciliationPart5") -> None:
                self.owner = owner
                self.calls = []

            def complete_messages(
                self, messages, *, max_tokens, response_format="json_object"
            ):
                payload = json.loads(messages[-1]["content"])
                nonce = payload["challenge_nonce"]
                call_index = len(self.calls)
                file_name = (
                    "amd_quality_dossier_part4a_initial.json"
                    if call_index == 0
                    else "amd_quality_dossier_part4a_repair.json"
                )
                response = json.loads(self.owner._captured(file_name))
                response["challenge_nonce"] = nonce
                raw = json.dumps(response, ensure_ascii=False)
                self.calls.append({
                    "max_tokens": max_tokens,
                    "messages": messages,
                    "nonce": nonce,
                })
                return {
                    "status": "ok",
                    "verified_live": True,
                    "fallback_used": False,
                    "provider": "AMD Developer Cloud",
                    "runtime": "vLLM",
                    "accelerator": "AMD Instinct MI300X",
                    "served_model": "reliefqueue-amd",
                    "underlying_model": None,
                    "request_id": f"captured-{call_index + 1}",
                    "latency_ms": 1,
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "raw_content": raw,
                    "generated_advisory": raw,
                    "warnings": [],
                    "error": None,
                    "finish_reason": "stop",
                    "request_settings": {"max_tokens": max_tokens},
                }

        adapter = CapturedAdapter(self)
        result = product_api._structured_workload_verification(
            adapter,
            self._fixture(),
            "complex_dossier",
            "JUDGE-DOSSIER",
        )
        self.assertEqual(len(adapter.calls), 2)
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_succeeded"])
        self.assertTrue(result["verified_live"])
        self.assertEqual(result["analysis_source"], "provider")
        self.assertEqual(result["semantic_issues"], [])
        self.assertEqual(
            result["provider_reconciliation"]["carried_source_ids"],
            ["REPORT-004", "REPORT-005", "REPORT-017"],
        )
        self.assertFalse(
            result["provider_reconciliation"][
                "local_operational_conclusions_added"
            ]
        )
# END RELIEFQUEUE AMD DOSSIER PROVIDER RECONCILIATION PART 5 TESTS


# BEGIN RELIEFQUEUE AMD DOSSIER UNSUPPORTED-CLAIM QUARANTINE PART 6 TESTS
class TestAmdDossierUnsupportedClaimQuarantinePart6(unittest.TestCase):
    def _fixture(self) -> str:
        return (
            FIXTURES / "amd_quality_complex_dossier.txt"
        ).read_text(encoding="utf-8")

    def _captured(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def _normalized_pair(self):
        fixture = self._fixture()
        initial, _, initial_source = normalize_structured_output(
            "complex_dossier",
            self._captured("amd_quality_dossier_part5_initial.json"),
            fixture,
            "JUDGE-DOSSIER",
        )
        repair, _, repair_source = normalize_structured_output(
            "complex_dossier",
            self._captured("amd_quality_dossier_part5_repair.json"),
            fixture,
            "JUDGE-DOSSIER",
        )
        return fixture, initial, repair, initial_source, repair_source

    def test_exact_part5_live_claims_are_quarantined_without_replacement(self) -> None:
        fixture, initial, repair, initial_source, repair_source = (
            self._normalized_pair()
        )
        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
        )
        self.assertEqual(initial_source, "provider")
        self.assertEqual(repair_source, "provider_incomplete")
        self.assertEqual(dossier_semantic_issues(merged, fixture), [])
        self.assertEqual(merged["resource_gaps"], [])
        self.assertTrue(evidence["unsupported_provider_claims_removed"])
        self.assertEqual(
            evidence["quarantined_unsupported_resource_gap_claims"],
            [
                "oxygen cylinders shortage; source only states allocation or availability",
                "wheelchairs shortage; source only states allocation or availability",
                "high-clearance truck shortage; source only states allocation or availability",
            ],
        )
        self.assertFalse(evidence["local_operational_conclusions_added"])

    def test_source_safe_provider_gap_is_not_broadly_removed(self) -> None:
        fixture, initial, repair, _, _ = self._normalized_pair()
        repair = dict(repair)
        repair["resource_gaps"] = [
            "insulin dose shortfall range is 5 to 7"
        ]
        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
        )
        self.assertEqual(
            merged["resource_gaps"],
            ["insulin dose shortfall range is 5 to 7"],
        )
        self.assertFalse(evidence["unsupported_provider_claims_removed"])
        self.assertEqual(
            evidence["quarantined_unsupported_resource_gap_claims"],
            [],
        )
        self.assertEqual(dossier_semantic_issues(merged, fixture), [])

    def test_product_boundary_accepts_exact_part5_live_provider_shapes(self) -> None:
        class CapturedAdapter:
            def __init__(
                self,
                owner: "TestAmdDossierUnsupportedClaimQuarantinePart6",
            ) -> None:
                self.owner = owner
                self.calls = []

            def complete_messages(
                self, messages, *, max_tokens, response_format="json_object"
            ):
                payload = json.loads(messages[-1]["content"])
                nonce = payload["challenge_nonce"]
                call_index = len(self.calls)
                file_name = (
                    "amd_quality_dossier_part5_initial.json"
                    if call_index == 0
                    else "amd_quality_dossier_part5_repair.json"
                )
                response = json.loads(self.owner._captured(file_name))
                response["challenge_nonce"] = nonce
                raw = json.dumps(response, ensure_ascii=False)
                self.calls.append(
                    {
                        "max_tokens": max_tokens,
                        "messages": messages,
                        "nonce": nonce,
                    }
                )
                return {
                    "status": "ok",
                    "verified_live": True,
                    "fallback_used": False,
                    "provider": "AMD Developer Cloud",
                    "runtime": "vLLM",
                    "accelerator": "AMD Instinct MI300X",
                    "served_model": "reliefqueue-amd",
                    "served_model_from_provider": True,
                    "underlying_model": "Qwen/Qwen2.5-7B-Instruct",
                    "request_id": f"captured-part6-{call_index + 1}",
                    "latency_ms": 1,
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "raw_content": raw,
                    "generated_advisory": raw,
                    "warnings": [],
                    "error": None,
                    "finish_reason": "stop",
                    "request_settings": {"max_tokens": max_tokens},
                }

        adapter = CapturedAdapter(self)
        result = product_api._structured_workload_verification(
            adapter,
            self._fixture(),
            "complex_dossier",
            "JUDGE-DOSSIER",
        )
        self.assertEqual(len(adapter.calls), 2)
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_succeeded"])
        self.assertTrue(result["verified_live"])
        self.assertEqual(result["analysis_source"], "provider")
        self.assertEqual(result["semantic_issues"], [])
        self.assertTrue(
            result["provider_reconciliation"][
                "unsupported_provider_claims_removed"
            ]
        )
        self.assertFalse(
            result["provider_reconciliation"][
                "local_operational_conclusions_added"
            ]
        )
# END RELIEFQUEUE AMD DOSSIER UNSUPPORTED-CLAIM QUARANTINE PART 6 TESTS


# BEGIN RELIEFQUEUE AMD DOSSIER INCIDENT RECONCILIATION PART 7 TESTS
class TestAmdDossierIncidentReconciliationPart7(unittest.TestCase):
    def _fixture(self) -> str:
        return (
            FIXTURES / "amd_quality_complex_dossier.txt"
        ).read_text(encoding="utf-8")

    def _captured(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def _normalized_pair(self):
        fixture = self._fixture()
        initial, _, initial_source = normalize_structured_output(
            "complex_dossier",
            self._captured("amd_quality_dossier_part6_initial.json"),
            fixture,
            "JUDGE-DOSSIER",
        )
        repair, _, repair_source = normalize_structured_output(
            "complex_dossier",
            self._captured("amd_quality_dossier_part6_repair.json"),
            fixture,
            "JUDGE-DOSSIER",
        )
        return fixture, initial, repair, initial_source, repair_source

    def test_exact_part6_live_incidents_reconcile_without_local_incident_creation(
        self,
    ) -> None:
        fixture, initial, repair, initial_source, repair_source = (
            self._normalized_pair()
        )
        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
            source_text=fixture,
        )
        incident_evidence = evidence[
            "provider_incident_reconciliation"
        ]

        self.assertEqual(initial_source, "provider")
        self.assertEqual(repair_source, "provider_incomplete")
        self.assertEqual(dossier_semantic_issues(merged, fixture), [])
        self.assertEqual(len(repair["consolidated_incidents"]), 2)
        self.assertEqual(len(merged["consolidated_incidents"]), 5)
        self.assertFalse(
            incident_evidence["local_incident_conclusions_added"]
        )
        self.assertEqual(
            incident_evidence["quarantined_repair_incidents"],
            [
                {
                    "incident_id": "INCIDENT-002",
                    "source_ids": [
                        "REPORT-002",
                        "REPORT-013",
                        "REPORT-014",
                    ],
                    "location_conflicts": [
                        ["REPORT-002", "REPORT-013"],
                        ["REPORT-002", "REPORT-014"],
                    ],
                    "reason": (
                        "provider incident merged source reports with "
                        "distinct explicit locations"
                    ),
                }
            ],
        )
        self.assertEqual(
            incident_evidence["carried_initial_provider_incidents"],
            [
                {
                    "incident_id": "INCIDENT-002",
                    "source_ids": ["REPORT-002"],
                },
                {
                    "incident_id": "INCIDENT-003",
                    "source_ids": ["REPORT-005"],
                },
                {
                    "incident_id": "INCIDENT-004",
                    "source_ids": ["REPORT-006", "REPORT-007"],
                },
                {
                    "incident_id": "INCIDENT-005",
                    "source_ids": ["REPORT-008"],
                },
            ],
        )
        self.assertEqual(
            incident_evidence["quarantined_unverified_people_ranges"],
            [
                {
                    "incident_id": "INCIDENT-004",
                    "source_ids": ["REPORT-006"],
                    "removed_people_range": "200",
                    "reason": (
                        "provider people_range presented an explicitly "
                        "unverified 200-person claim without a qualifier"
                    ),
                }
            ],
        )
        bridge_incident = next(
            item
            for item in merged["consolidated_incidents"]
            if item.get("incident_id") == "INCIDENT-004"
        )
        self.assertEqual(bridge_incident.get("people_range"), "")
        self.assertFalse(evidence["local_operational_conclusions_added"])

    def test_source_safe_repair_incident_remains_authoritative(self) -> None:
        fixture, initial, repair, _, _ = self._normalized_pair()
        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
            source_text=fixture,
        )
        first = merged["consolidated_incidents"][0]
        self.assertEqual(first["incident_id"], "INCIDENT-001")
        self.assertEqual(
            first["needs"],
            "drinking water, food, medical care",
        )
        self.assertEqual(
            evidence["provider_incident_reconciliation"][
                "skipped_initial_provider_incident_overlaps"
            ][0]["incident_id"],
            "INCIDENT-001",
        )

    def test_product_boundary_accepts_exact_part6_live_provider_shapes(
        self,
    ) -> None:
        class CapturedAdapter:
            def __init__(
                self,
                owner: "TestAmdDossierIncidentReconciliationPart7",
            ) -> None:
                self.owner = owner
                self.calls = []

            def complete_messages(
                self,
                messages,
                *,
                max_tokens,
                response_format="json_object",
            ):
                payload = json.loads(messages[-1]["content"])
                nonce = payload["challenge_nonce"]
                call_index = len(self.calls)
                file_name = (
                    "amd_quality_dossier_part6_initial.json"
                    if call_index == 0
                    else "amd_quality_dossier_part6_repair.json"
                )
                response = json.loads(self.owner._captured(file_name))
                response["challenge_nonce"] = nonce
                if isinstance(response.get("output_contract"), dict):
                    response["output_contract"][
                        "challenge_nonce"
                    ] = nonce
                raw = json.dumps(response, ensure_ascii=False)
                self.calls.append(
                    {
                        "max_tokens": max_tokens,
                        "messages": messages,
                        "nonce": nonce,
                    }
                )
                return {
                    "status": "ok",
                    "verified_live": True,
                    "fallback_used": False,
                    "provider": "AMD Developer Cloud",
                    "runtime": "vLLM",
                    "accelerator": "AMD Instinct MI300X",
                    "served_model": "reliefqueue-amd",
                    "served_model_from_provider": True,
                    "underlying_model": "Qwen/Qwen2.5-7B-Instruct",
                    "request_id": (
                        f"captured-part7-{call_index + 1}"
                    ),
                    "latency_ms": 1,
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "raw_content": raw,
                    "generated_advisory": raw,
                    "warnings": [],
                    "error": None,
                    "finish_reason": "stop",
                    "request_settings": {
                        "max_tokens": max_tokens
                    },
                }

        adapter = CapturedAdapter(self)
        result = product_api._structured_workload_verification(
            adapter,
            self._fixture(),
            "complex_dossier",
            "JUDGE-DOSSIER",
        )
        self.assertEqual(len(adapter.calls), 2)
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_succeeded"])
        self.assertTrue(result["verified_live"])
        self.assertEqual(result["analysis_source"], "provider")
        self.assertEqual(result["semantic_issues"], [])
        incident_evidence = result["provider_reconciliation"][
            "provider_incident_reconciliation"
        ]
        self.assertEqual(
            incident_evidence["merged_incident_count"],
            5,
        )
        self.assertFalse(
            incident_evidence["local_incident_conclusions_added"]
        )


# END RELIEFQUEUE AMD DOSSIER INCIDENT RECONCILIATION PART 7 TESTS

# BEGIN RELIEFQUEUE AMD DOSSIER CONFLICT-OBSERVATION RECONCILIATION PART 8B TESTS
class TestAmdDossierConflictObservationReconciliationPart8B(
    unittest.TestCase
):
    def _fixture(self) -> str:
        return (
            FIXTURES / "amd_quality_complex_dossier.txt"
        ).read_text(encoding="utf-8")

    def _normalized(self, file_name: str) -> dict:
        source = self._fixture()
        raw = (FIXTURES / file_name).read_text(encoding="utf-8")
        record, _, _ = normalize_structured_output(
            "complex_dossier",
            raw,
            source,
            "JUDGE-DOSSIER",
        )
        return record

    def test_source_safe_initial_conflict_observations_fill_empty_repair_sections(
        self,
    ) -> None:
        source = self._fixture()
        initial = self._normalized(
            "amd_quality_dossier_part6_initial.json"
        )
        repair = self._normalized(
            "amd_quality_dossier_part8_repair.json"
        )

        self.assertEqual(repair["contradictions"], [])
        self.assertEqual(repair["superseded_updates"], [])
        self.assertEqual(repair["duplicate_clusters"], [])
        self.assertEqual(repair["unverified_claims"], [])

        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
            source_text=source,
        )

        self.assertEqual(dossier_semantic_issues(merged, source), [])
        conflict = evidence["provider_conflict_reconciliation"]
        self.assertEqual(
            conflict["carried_initial_provider_fields"],
            [
                "contradictions",
                "superseded_updates",
                "duplicate_clusters",
                "unverified_claims",
            ],
        )
        self.assertEqual(conflict["source_safety_issues"], [])
        self.assertFalse(conflict["local_conflict_observations_added"])
        self.assertFalse(evidence["local_operational_conclusions_added"])

    def test_nonempty_repair_conflict_section_remains_authoritative(
        self,
    ) -> None:
        source = self._fixture()
        initial = self._normalized(
            "amd_quality_dossier_part6_initial.json"
        )
        repair = self._normalized(
            "amd_quality_dossier_part8_repair.json"
        )
        repair_contradiction = {
            "source_ids": ["REPORT-006", "REPORT-007"],
            "conflict": "repair-authored bridge status",
            "working_assumption": "damaged, not collapsed",
        }
        repair["contradictions"] = [repair_contradiction]

        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
            source_text=source,
        )

        self.assertEqual(
            merged["contradictions"],
            [repair_contradiction],
        )
        conflict = evidence["provider_conflict_reconciliation"]
        self.assertNotIn(
            "contradictions",
            conflict["carried_initial_provider_fields"],
        )

    def test_source_unsafe_initial_conflict_sections_are_not_carried(
        self,
    ) -> None:
        source = self._fixture()
        initial = self._normalized(
            "amd_quality_dossier_part6_initial.json"
        )
        repair = self._normalized(
            "amd_quality_dossier_part8_repair.json"
        )
        initial["contradictions"] = []
        initial["superseded_updates"] = []
        initial["duplicate_clusters"] = []
        initial["unverified_claims"] = []

        merged, evidence = reconcile_provider_dossier_outputs(
            initial,
            repair,
            source_text=source,
        )

        conflict = evidence["provider_conflict_reconciliation"]
        self.assertTrue(conflict["source_safety_issues"])
        self.assertEqual(
            conflict["carried_initial_provider_fields"],
            [],
        )
        self.assertEqual(merged["contradictions"], [])
        self.assertEqual(merged["unverified_claims"], [])


# END RELIEFQUEUE AMD DOSSIER CONFLICT-OBSERVATION RECONCILIATION PART 8B TESTS



# BEGIN RELIEFQUEUE AMD DOSSIER TARGETED INCIDENT SUPPLEMENT PART 8C TESTS

class TestAmdDossierTargetedIncidentSupplementPart8C(
    unittest.TestCase
):
    def _source(self) -> str:
        return (
            FIXTURES / "amd_quality_complex_dossier.txt"
        ).read_text(encoding="utf-8")

    def _failed_reconciled(self) -> dict:
        return json.loads(
            (
                FIXTURES
                / "amd_quality_dossier_part8b_reconciled.json"
            ).read_text(encoding="utf-8")
        )

    def _provider_reconciliation(self) -> dict:
        return json.loads(
            (
                FIXTURES
                / "amd_quality_dossier_part8b_reconciliation.json"
            ).read_text(encoding="utf-8")
        )

    def _safe_supplement(self, nonce: str) -> dict:
        return {
            "schema_version": (
                "reliefqueue-dossier-incident-supplement/v1"
            ),
            "workload_mode": (
                "complex_dossier_incident_supplement"
            ),
            "challenge_nonce": nonce,
            "corrected_incidents": [
                {
                    "incident_id": "INCIDENT-001",
                    "source_ids": [
                        "REPORT-001",
                        "REPORT-003",
                    ],
                    "location": "Old Bus Stand",
                    "needs": "drinking water",
                    "people_range": "14 families",
                    "vulnerable_groups": "children, elderly",
                    "urgency_rationale": (
                        "drinking water finished; east lane flooded"
                    ),
                    "missing_fields": (
                        "verify household overlap and OCR count"
                    ),
                    "confidence": "medium",
                },
                {
                    "incident_id": "INCIDENT-006",
                    "source_ids": ["REPORT-002"],
                    "location": (
                        "North embankment lane behind bus stand"
                    ),
                    "needs": "flood evacuation review",
                    "people_range": "18 people",
                    "vulnerable_groups": (
                        "3 elderly, teenager, pregnant person"
                    ),
                    "urgency_rationale": (
                        "home flooding near north embankment"
                    ),
                    "missing_fields": (
                        "exact lane and water depth"
                    ),
                    "confidence": "medium",
                },
            ],
            "human_review_required": True,
        }

    def test_exact_part8b_failure_accepts_source_safe_provider_partition(
        self,
    ) -> None:
        source = self._source()
        current = self._failed_reconciled()
        reconciliation = self._provider_reconciliation()
        supplement = self._safe_supplement("nonce-part8c")

        merged, evidence = reconcile_provider_incident_supplement(
            current,
            supplement,
            source,
            reconciliation,
        )

        self.assertEqual(dossier_semantic_issues(merged, source), [])
        self.assertEqual(
            len(merged["consolidated_incidents"]),
            6,
        )
        self.assertTrue(evidence["complete_source_partition"])
        self.assertEqual(
            evidence["covered_allowed_source_ids"],
            ["REPORT-001", "REPORT-002", "REPORT-003"],
        )
        self.assertEqual(evidence["rejected_provider_incidents"], [])
        self.assertFalse(evidence["local_incident_conclusions_added"])

        links = {
            row["source_id"]: row["linked_incident_id"]
            for row in merged["source_coverage"]
            if row["source_id"] in {
                "REPORT-001",
                "REPORT-002",
                "REPORT-003",
            }
        }
        self.assertEqual(
            links,
            {
                "REPORT-001": "INCIDENT-001",
                "REPORT-002": "INCIDENT-006",
                "REPORT-003": "INCIDENT-001",
            },
        )

    def test_cross_location_provider_remerge_is_rejected(
        self,
    ) -> None:
        source = self._source()
        current = self._failed_reconciled()
        reconciliation = self._provider_reconciliation()
        supplement = self._safe_supplement("nonce-part8c")
        supplement["corrected_incidents"] = [
            {
                "incident_id": "INCIDENT-001",
                "source_ids": [
                    "REPORT-001",
                    "REPORT-002",
                    "REPORT-003",
                ],
                "location": "Old Bus Stand",
                "needs": "water and evacuation",
                "people_range": "18",
                "vulnerable_groups": "pregnant, elderly",
                "urgency_rationale": "flooding",
                "missing_fields": "verify",
                "confidence": "low",
            }
        ]

        merged, evidence = reconcile_provider_incident_supplement(
            current,
            supplement,
            source,
            reconciliation,
        )

        self.assertEqual(
            len(merged["consolidated_incidents"]),
            4,
        )
        self.assertFalse(evidence["complete_source_partition"])
        self.assertTrue(evidence["rejected_provider_incidents"])
        self.assertIn(
            "consolidated_incidents requires at least 5",
            " | ".join(dossier_semantic_issues(merged, source)),
        )

    def test_targeted_prompt_is_bounded_and_source_specific(
        self,
    ) -> None:
        source = self._source()
        current = self._failed_reconciled()
        reconciliation = self._provider_reconciliation()
        issues = [
            "consolidated_incidents requires at least 5 items, got 4"
        ]

        self.assertTrue(
            dossier_incident_supplement_required(
                issues,
                reconciliation,
            )
        )
        prompt = build_dossier_incident_supplement_prompt(
            source,
            current,
            issues,
            reconciliation,
            "nonce-part8c",
        )
        payload = json.loads(prompt[-1]["content"])
        budget = enforce_context_budget(
            prompt[-1]["content"],
            WORKLOAD_COMPLETION_BUDGETS[
                "complex_dossier_incident_supplement"
            ],
        )

        self.assertEqual(
            payload["allowed_source_ids"],
            ["REPORT-001", "REPORT-002", "REPORT-003"],
        )
        self.assertEqual(
            [
                row["source_id"]
                for row in payload["source_reports"]
            ],
            [
                "REPORT-001",
                "REPORT-002",
                "REPORT-003",
                "REPORT-004",
            ],
        )
        self.assertEqual(
            payload["explicit_duplicate_pairs"],
            [["REPORT-001", "REPORT-003"]],
        )
        self.assertEqual(
            payload["forbidden_location_merges"],
            [["REPORT-001", "REPORT-002"]],
        )
        self.assertGreaterEqual(
            ACTIVE_CONTEXT_LIMIT
            - budget["estimated_total_tokens"],
            300,
        )
        self.assertFalse(
            dossier_incident_supplement_required(
                [
                    "calculation_checks missing source-linked row "
                    "for safe-capacity overflow"
                ],
                reconciliation,
            )
        )

    def test_normalizer_preserves_provider_incidents_and_nonce(
        self,
    ) -> None:
        raw = json.dumps(
            self._safe_supplement("nonce-part8c")
        )
        record, warnings, source = (
            normalize_dossier_incident_supplement(raw)
        )
        self.assertEqual(source, "provider")
        self.assertEqual(
            record["challenge_nonce"],
            "nonce-part8c",
        )
        self.assertEqual(
            len(record["corrected_incidents"]),
            2,
        )
        self.assertEqual(warnings, [])

    def test_product_boundary_uses_at_most_two_repairs(
        self,
    ) -> None:
        source = self._source()
        current = self._failed_reconciled()
        repair = json.loads(
            (
                FIXTURES
                / "amd_quality_dossier_part8b_repair.json"
            ).read_text(encoding="utf-8")
        )
        initial = json.loads(json.dumps(current))
        initial["consolidated_incidents"] = [
            json.loads(
                json.dumps(repair["consolidated_incidents"][0])
            ),
            *json.loads(
                json.dumps(current["consolidated_incidents"])
            ),
        ]
        owner = self

        class IncidentSupplementAdapter:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def complete_messages(
                self,
                messages,
                *,
                max_tokens,
                response_format="json_object",
            ):
                payload = json.loads(messages[-1]["content"])
                mode = (
                    payload.get("workload_mode")
                    or payload.get("output_contract", {}).get(
                        "workload_mode"
                    )
                )
                nonce = payload["challenge_nonce"]
                self.calls.append(
                    {
                        "mode": mode,
                        "nonce": nonce,
                        "max_tokens": max_tokens,
                    }
                )
                if mode == "complex_dossier":
                    output = json.loads(json.dumps(initial))
                elif mode == "complex_dossier_repair":
                    output = json.loads(json.dumps(repair))
                elif (
                    mode
                    == "complex_dossier_incident_supplement"
                ):
                    output = owner._safe_supplement(nonce)
                else:
                    raise AssertionError(mode)
                output["challenge_nonce"] = nonce
                content = json.dumps(output)
                return {
                    "status": "ok",
                    "verified_live": True,
                    "fallback_used": False,
                    "provider": "AMD Developer Cloud",
                    "runtime": "vLLM",
                    "accelerator": "AMD Instinct MI300X",
                    "served_model": "reliefqueue-amd",
                    "underlying_model": None,
                    "request_id": f"req-{len(self.calls)}",
                    "latency_ms": 5,
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "raw_content": content,
                    "generated_advisory": content,
                    "warnings": [],
                    "error": None,
                    "finish_reason": "stop",
                    "request_settings": {
                        "max_tokens": max_tokens
                    },
                }

        adapter = IncidentSupplementAdapter()
        result = product_api._structured_workload_verification(
            adapter,
            source,
            "complex_dossier",
            "JUDGE-DOSSIER",
        )

        self.assertEqual(
            [call["mode"] for call in adapter.calls],
            [
                "complex_dossier",
                "complex_dossier_repair",
                "complex_dossier_incident_supplement",
            ],
        )
        self.assertEqual(result["provider_call_count"], 3)
        self.assertEqual(result["repair_rounds"], 2)
        self.assertTrue(result["incident_supplement_attempted"])
        self.assertTrue(result["incident_supplement_succeeded"])
        self.assertTrue(result["repair_succeeded"])
        self.assertTrue(result["verified_live"])
        self.assertEqual(result["analysis_source"], "provider")
        self.assertEqual(result["semantic_issues"], [])
        self.assertEqual(
            result["request_settings"][
                "maximum_semantic_repair_calls"
            ],
            2,
        )
        self.assertEqual(
            result["request_settings"][
                "selected_completion_max_tokens"
            ],
            WORKLOAD_COMPLETION_BUDGETS[
                "complex_dossier_incident_supplement"
            ],
        )
        self.assertEqual(result["provider_total_tokens"], 90)
        supplement_evidence = result["repair_evidence"][
            "incident_supplement_evidence"
        ]["provider_incident_supplement"]
        self.assertTrue(
            supplement_evidence["complete_source_partition"]
        )
        self.assertFalse(
            supplement_evidence[
                "local_incident_conclusions_added"
            ]
        )


# END RELIEFQUEUE AMD DOSSIER TARGETED INCIDENT SUPPLEMENT PART 8C TESTS

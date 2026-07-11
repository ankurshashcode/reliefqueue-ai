#!/usr/bin/env python3
"""Bounded, assertion-driven AMD quality live validation.

Default mode is dry-run/offline. Set ``AMD_QUALITY_LIVE=1`` only in a trusted
operator environment with the configured AMD/vLLM credentials. The script
never prints the API key and fails when live output is generic, fallback-based,
unbound to the challenge nonce, or missing fixture-specific reasoning.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from reliefqueue.amd_quality import (
    cross_case_semantic_issues,
    dossier_semantic_issues,
    parse_burst_input,
)
from reliefqueue.product_api import burst_verification, live_verification

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
DEFAULT_OUT = ROOT / "reports" / "amd-inference-quality" / "latest" / "live-evidence.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-count", type=int, default=1)
    parser.add_argument("--dossier-count", type=int, default=1)
    parser.add_argument("--burst-count", type=int, default=3)
    parser.add_argument("--max-live-provider-calls", type=int, default=8)
    parser.add_argument("--max-technical-retries", type=int, default=2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _conflict_resolution_observation_count(analysis: dict[str, Any]) -> int:
    """Count provider-authored conflict, update, duplicate and uncertainty observations."""

    return sum(
        len(analysis.get(key) or [])
        for key in [
            "contradictions",
            "superseded_updates",
            "duplicate_clusters",
            "unverified_claims",
        ]
    )


def _validate_common(name: str, result: dict[str, Any], errors: list[str]) -> None:
    _require(result.get("verified_live") is True, f"{name}: verified_live is not true", errors)
    _require(result.get("fallback_used") is False, f"{name}: fallback_used is not false", errors)
    _require(result.get("analysis_source") == "provider", f"{name}: analysis_source is not provider", errors)
    _require(result.get("provider_response_received") is True, f"{name}: provider response not recorded", errors)
    _require(result.get("nonce_sent_to_provider") is True, f"{name}: nonce not sent to provider", errors)
    _require(result.get("nonce_echoed_by_provider") is True, f"{name}: provider did not echo nonce", errors)
    _require(result.get("verification_bound_to_nonce") is True, f"{name}: result not bound to nonce", errors)
    _require(bool(result.get("request_id")), f"{name}: missing request_id", errors)
    _require(bool(result.get("challenge_nonce")), f"{name}: missing challenge_nonce", errors)
    _require(result.get("human_review_required") is True, f"{name}: human review not required", errors)
    _require(result.get("private_text_sent") is False, f"{name}: private_text_sent not false", errors)
    _require(result.get("secret_values_exposed") is False, f"{name}: secret_values_exposed not false", errors)
    if "semantic_completeness" in result:
        _require(result.get("semantic_completeness") is True, f"{name}: semantic completeness failed", errors)
        _require(not (result.get("semantic_issues") or []), f"{name}: semantic issues remain", errors)
    if result.get("repair_attempted"):
        _require(result.get("repair_succeeded") is True, f"{name}: repair attempted but did not succeed", errors)


def _validate_single(result: dict[str, Any], errors: list[str]) -> None:
    _validate_common("single", result, errors)
    analysis = result.get("structured_output") or {}
    text = _text(analysis)
    for concept in ["17", "21", "wheelchair", "six", "transformer", "east road", "west route", "small vehicle"]:
        _require(concept in text, f"single: missing concept {concept!r}", errors)
    priorities = analysis.get("recommended_priorities") or []
    questions = (analysis.get("coordinator_questions") or []) + (analysis.get("missing_information") or [])
    _require(len(priorities) >= 3, "single: fewer than three ranked priorities", errors)
    _require(len(questions) >= 2, "single: fewer than two questions/missing-information items", errors)
    _require(bool(analysis.get("route_and_access_analysis")), "single: missing route/access analysis", errors)
    _require(bool(analysis.get("resource_implications")), "single: missing resource implications", errors)


def _validate_dossier(result: dict[str, Any], errors: list[str]) -> None:
    _validate_common("dossier", result, errors)
    analysis = result.get("structured_output") or {}
    source = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
    semantic = dossier_semantic_issues(analysis, source)
    for issue in semantic:
        errors.append("dossier semantic: " + issue)

    text = _text(analysis)
    for concept in [
        "report-001", "report-003", "report-006", "report-007",
        "damaged", "not collapsed", "80", "43", "67", "24",
        "12", "19", "7", "5", "wheelchair", "oxygen",
        "textile", "clinic road", "45", "33", "41", "8",
        "water purification", "dry food", "transformer", "utility isolation",
    ]:
        _require(concept in text, f"dossier: missing fixture-specific concept {concept!r}", errors)

    coverage = analysis.get("source_coverage") or []
    covered_ids = {
        str(item.get("source_id") or "").lower()
        for item in coverage
        if isinstance(item, dict)
    }
    _require(len(coverage) == 20, "dossier: source_coverage does not contain exactly 20 reports", errors)
    _require("report-001" in covered_ids and "report-020" in covered_ids, "dossier: source coverage endpoints missing", errors)
    _require(not (analysis.get("uncovered_source_ids") or []), "dossier: uncovered_source_ids is not empty", errors)
    _require(
        len(analysis.get("consolidated_incidents") or []) >= 5,
        "dossier: fewer than five consolidated incidents",
        errors,
    )
    _require(
        len(analysis.get("contradictions") or []) >= 1,
        "dossier: fewer than one direct contradiction",
        errors,
    )
    _require(
        _conflict_resolution_observation_count(analysis) >= 3,
        "dossier: fewer than three aggregate conflict-resolution observations",
        errors,
    )
    _require(
        len(analysis.get("calculation_checks") or []) >= 2,
        "dossier: fewer than two arithmetic checks",
        errors,
    )
    _require(
        len(analysis.get("prioritized_operational_plan") or []) >= 5,
        "dossier: fewer than five ranked actions",
        errors,
    )

    # Specific anti-conflation and anti-hallucination checks derived from the fixture.
    for incident in analysis.get("consolidated_incidents") or []:
        if not isinstance(incident, dict):
            continue
        ids = {str(value).upper() for value in incident.get("source_ids") or []}
        _require(
            not ({"REPORT-001", "REPORT-014"} <= ids),
            "dossier: REPORT-001 and REPORT-014 were incorrectly merged across distinct locations",
            errors,
        )
    resource_gaps = _text(analysis.get("resource_gaps") or [])
    for unsupported in [
        "oxygen cylinders needed",
        "additional wheelchairs needed",
        "additional high-clearance truck needed",
    ]:
        _require(unsupported not in resource_gaps, f"dossier: unsupported resource gap {unsupported!r}", errors)

    calculations = _text(analysis.get("calculation_checks") or [])
    _require(all(value in calculations for value in ["67", "43", "24"]), "dossier: missing 67-43=24 shelter calculation", errors)
    _require(all(value in calculations for value in ["19", "12", "7", "5"]), "dossier: missing 19/12 insulin shortfall range", errors)
    _require(all(value in calculations for value in ["45", "12", "33", "41", "8"]), "dossier: missing school shelter 45-12=33 and overflow 8", errors)



def _validate_burst(result: dict[str, Any], errors: list[str]) -> None:
    _require(result.get("submitted") == 3, "burst: submitted is not 3", errors)
    _require(result.get("parsed") == 3, "burst: parsed is not 3", errors)
    _require(result.get("succeeded") == 3, "burst: succeeded is not 3", errors)
    _require(result.get("fallback_responses") == 0, "burst: per-case fallback detected", errors)
    _require(result.get("verified_live") is True, "burst: batch is not fully verified live", errors)
    _require(int(result.get("provider_call_count") or 0) in {4, 5}, "burst: provider_call_count must be 4 or 5", errors)

    cases = result.get("cases") or []
    _require(len(cases) == 3, "burst: cases length is not 3", errors)
    for index, case in enumerate(cases, start=1):
        _validate_common(f"burst-case-{index}", case, errors)
    request_ids = {case.get("request_id") for case in cases if case.get("request_id")}
    nonces = {case.get("challenge_nonce") for case in cases if case.get("challenge_nonce")}
    _require(len(request_ids) == 3, "burst: per-case request IDs are not unique", errors)
    _require(len(nonces) == 3, "burst: per-case nonces are not unique", errors)

    synthesis = result.get("cross_case_synthesis") or {}
    evidence = result.get("cross_case_evidence") or {}
    _validate_common("burst-synthesis", evidence, errors)
    for key in [
        "highest_risk_cases", "inventory_conflicts", "suggested_sequence",
        "missing_facts_that_could_change_order", "aggregate_resource_implications",
        "coordinator_review_gates",
    ]:
        _require(bool(synthesis.get(key)), f"burst synthesis: missing {key}", errors)
    for key in [
        "resource_competition", "shared_route_bottlenecks", "possible_duplicate_cases",
    ]:
        _require(
            key in synthesis and isinstance(synthesis.get(key), list),
            f"burst synthesis: missing explicit list {key}",
            errors,
        )

    for issue in cross_case_semantic_issues(synthesis, cases):
        errors.append("burst synthesis semantic: " + issue)
    inventory = _text(synthesis.get("inventory_conflicts") or [])
    _require(all(value in inventory for value in ["insulin", "12", "19"]), "burst synthesis: insulin arithmetic not explicit", errors)
    waiting_ids = {
        str(item.get("case_id") or "")
        for item in synthesis.get("cases_that_can_wait_with_reason") or []
        if isinstance(item, dict)
    }
    _require("case-03" not in waiting_ids, "burst synthesis: insulin-shortage case marked safe-to-wait", errors)



def main() -> int:
    args = parse_args()
    if (args.single_count, args.dossier_count, args.burst_count) != (1, 1, 3):
        raise SystemExit("This bounded validator requires exactly 1 single, 1 dossier and 3 burst cases.")
    if args.max_live_provider_calls > 8 or args.max_technical_retries > 2:
        raise SystemExit("Requested live-call or retry ceiling exceeds reviewed limits.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    burst_text = (FIXTURES / "amd_quality_burst.txt").read_text(encoding="utf-8")
    parsed_cases = parse_burst_input(burst_text)
    dry_evidence = {
        "status": "dry_run",
        "provider_calls_total": 0,
        "technical_retries": 0,
        "parser_regression": {"submitted": 3, "parsed": len(parsed_cases)},
        "message": "Set AMD_QUALITY_LIVE=1 for the trusted bounded live stage.",
    }
    if os.environ.get("AMD_QUALITY_LIVE") != "1":
        args.output.write_text(json.dumps(dry_evidence, indent=2), encoding="utf-8")
        print(f"dry-run evidence written: {args.output}; provider_calls_total=0")
        return 0

    single_text = (FIXTURES / "amd_quality_single.txt").read_text(encoding="utf-8")
    dossier_text = (FIXTURES / "amd_quality_complex_dossier.txt").read_text(encoding="utf-8")
    single = live_verification({"workload_mode": "single", "text": single_text, "synthetic_confirmed": True})
    dossier = live_verification({"workload_mode": "complex_dossier", "text": dossier_text, "synthetic_confirmed": True})
    burst = burst_verification(
        {
            "concurrency": 1,
            "reports": [{"id": case.id, "text": case.text} for case in parsed_cases],
            "synthetic_confirmed": True,
        }
    )

    single_calls = int(single.get("provider_call_count") or 1)
    dossier_calls = int(dossier.get("provider_call_count") or 1)
    burst_calls = int(burst.get("provider_call_count") or 0)
    provider_calls_total = single_calls + dossier_calls + burst_calls
    technical_retries = 0
    errors: list[str] = []
    _require(6 <= provider_calls_total <= args.max_live_provider_calls, "live provider-call total must be between 6 and the reviewed ceiling", errors)
    _require(dossier_calls in {1, 2, 3}, "dossier provider-call count must be 1, 2 or 3", errors)
    _require(burst_calls in {4, 5}, "burst provider-call count must be 4 or 5", errors)
    _require(technical_retries <= args.max_technical_retries, "technical-retry ceiling exceeded", errors)
    _validate_single(single, errors)
    _validate_dossier(dossier, errors)
    _validate_burst(burst, errors)

    request_ids: list[str] = []
    for result in [single, dossier, burst]:
        ids = result.get("provider_request_ids")
        if isinstance(ids, list) and ids:
            request_ids.extend(str(value) for value in ids if value)
        elif result.get("request_id"):
            request_ids.append(str(result["request_id"]))
    _require(
        len(request_ids) == provider_calls_total,
        f"provider request ID count {len(request_ids)} does not match provider call count {provider_calls_total}",
        errors,
    )
    _require(
        len(set(request_ids)) == provider_calls_total,
        "provider request IDs are not all unique",
        errors,
    )

    evidence = {
        "status": "pass" if not errors else "fail",
        "provider_calls_total": provider_calls_total,
        "technical_retries": technical_retries,
        "call_breakdown": {
            "single": single_calls,
            "dossier": dossier_calls,
            "burst": burst_calls,
        },
        "request_ids": request_ids,
        "single": single,
        "dossier": dossier,
        "burst": burst,
        "model_metadata": dossier.get("model_metadata") or single.get("model_metadata"),
        "validation_errors": errors,
        "human_review_required": True,
    }
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"live evidence written: {args.output}; provider_calls_total={provider_calls_total}; status={evidence['status']}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# BEGIN RELIEFQUEUE AMD FINAL QUALITY GATE PART 8
# Aligns the consolidated live runner with the accepted Part 7 semantic contract.
# END RELIEFQUEUE AMD FINAL QUALITY GATE PART 8

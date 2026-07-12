#!/usr/bin/env python3
"""Opt-in public proof that the deployed judge path reaches live AMD/vLLM.

This check sends only bundled synthetic disaster-response text. It verifies
provider transport, nonce binding, structured output, zero fallback, model
metadata, and mandatory human review. It never accepts or prints provider
credentials.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "submission-live-amd" / "latest" / "report.json"

SYNTHETIC_DOSSIER = """[REPORT-001 | SMS] Flood water at Sector 7 bridge. Five people on a roof, including two children. Boat access requested.
[REPORT-002 | Field update] Sector 7 household evacuated at 14:10; one adult still needs a mobility-safe transfer.
[REPORT-003 | WhatsApp] Relief hub west has an elderly diabetic resident with six insulin doses left for an estimated 19-day isolation period.
[REPORT-004 | Field] East road blocked by a fallen transformer. Small vehicles can use the west route; large trucks cannot pass.
[REPORT-005 | Shelter] School shelter capacity 45, current occupancy 41, eight additional arrivals expected. Overflow decision required.
[REPORT-006 | OCR] Water stock: 80 containers received, 43 distributed, 24 reserved; reconcile the unexplained difference before allocation.
[REPORT-007 | Update] Initial bridge-collapse report was incorrect: bridge is damaged, not collapsed. Do not merge this with the textile-market incident.
[REPORT-008 | Coordinator] Prioritize life safety, medicine continuity, route access, shelter overflow, inventory reconciliation, and questions that could change ordering.
"""

BURST_REPORTS = [
    {"id": "judge-burst-1", "text": "Family of four on a rooftop near Sector 7; boat rescue access uncertain after bridge damage."},
    {"id": "judge-burst-2", "text": "Insulin stock is 6 doses for a resident isolated up to 19 days; cold-chain handoff and replenishment required."},
    {"id": "judge-burst-3", "text": "School shelter capacity 45, occupancy 41, eight arrivals expected; identify overflow and transport dependencies."},
]


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    raw = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "ReliefQueueSubmissionLiveAMDCheck/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise RuntimeError(f"{path} returned non-object JSON")
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {detail}") from exc


def validate_common(name: str, result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = {
        "verified_live": result.get("verified_live") is True,
        "fallback_used_false": result.get("fallback_used") is False,
        "analysis_source_provider": result.get("analysis_source") == "provider",
        "nonce_sent": result.get("nonce_sent_to_provider") is True,
        "nonce_echoed": result.get("nonce_echoed_by_provider") is True,
        "nonce_bound": result.get("verification_bound_to_nonce") is True,
        "request_id": bool(result.get("request_id")),
        "challenge_nonce": bool(result.get("challenge_nonce")),
        "human_review": result.get("human_review_required") is True,
    }
    for check, passed in checks.items():
        if not passed:
            errors.append(f"{name}: {check} failed")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("public_url")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    if os.environ.get("RELIEFQUEUE_CONFIRM_LIVE_AMD") != "YES":
        raise SystemExit("Set RELIEFQUEUE_CONFIRM_LIVE_AMD=YES to authorize the bounded live provider check.")
    if not args.public_url.startswith(("https://", "http://")):
        raise SystemExit("public_url must start with https:// or http://")

    dossier = post_json(
        args.public_url,
        "/api/ai/live-verification",
        {"workload_mode": "complex_dossier", "text": SYNTHETIC_DOSSIER, "synthetic_confirmed": True},
        args.timeout,
    )
    burst = post_json(
        args.public_url,
        "/api/ai/burst-verification",
        {"reports": BURST_REPORTS, "concurrency": 2, "synthetic_confirmed": True},
        args.timeout,
    )

    errors = validate_common("dossier", dossier)
    dossier_output = dossier.get("structured_output") or {}
    if dossier.get("semantic_completeness") is not True:
        errors.append("dossier: semantic completeness failed")
    source_coverage = dossier_output.get("source_coverage") or []
    if len(source_coverage) < 8:
        errors.append("dossier: expected source coverage for all eight synthetic reports")
    if not (dossier_output.get("contradictions") or dossier_output.get("superseded_updates")):
        errors.append("dossier: conflict/update reconciliation missing")
    if not dossier_output.get("calculation_checks"):
        errors.append("dossier: calculation checks missing")
    if not dossier_output.get("prioritized_operational_plan"):
        errors.append("dossier: prioritized operational plan missing")
    if burst.get("verified_live") is not True:
        errors.append("burst: batch not verified_live")
    if burst.get("fallback_used") is not False or int(burst.get("fallback_responses") or 0) != 0:
        errors.append("burst: fallback detected")
    if int(burst.get("submitted") or 0) != len(BURST_REPORTS):
        errors.append("burst: submitted count mismatch")
    if int(burst.get("succeeded") or 0) != len(BURST_REPORTS):
        errors.append("burst: not every case verified live")
    synthesis = burst.get("cross_case_evidence") or {}
    errors.extend(validate_common("burst-synthesis", synthesis))
    synthesis_output = burst.get("cross_case_synthesis") or {}
    if not synthesis_output:
        errors.append("burst: cross-case synthesis missing")
    for key in ["highest_risk_cases", "suggested_sequence", "missing_facts_that_could_change_order"]:
        if not synthesis_output.get(key):
            errors.append(f"burst: cross-case synthesis missing {key}")

    report = {
        "contract": "reliefqueue-submission-live-amd-check/v1",
        "generated_at_utc": utc_now(),
        "public_url": args.public_url.rstrip("/"),
        "status": "PASS" if not errors else "FAIL",
        "synthetic_only": True,
        "human_review_required": True,
        "claim_boundary": "Proves this deployed request path reached a nonce-bound provider response; it does not prove hardware exclusivity.",
        "dossier": dossier,
        "burst": burst,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SUBMISSION_LIVE_AMD_CHECK={report['status']}")
    print(f"SUBMISSION_LIVE_AMD_REPORT={args.output}")
    print(f"DOSSIER_LATENCY_MS={dossier.get('latency_ms')}")
    print(f"BURST_SUCCEEDED={burst.get('succeeded')}/{burst.get('submitted')}")
    print(f"BURST_PROVIDER_CALLS={burst.get('provider_call_count')}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

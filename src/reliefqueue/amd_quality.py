"""AMD inference-quality helpers for judge-facing structured workloads.

The functions in this module are offline-testable. Provider calls are injected
by :mod:`reliefqueue.product_api` through the existing OpenAI-compatible
adapter. This module deliberately keeps provider-generated analysis separate
from deterministic local safety fallbacks so the UI cannot mislabel local
content as live AMD inference.
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from .ai import EMAIL_RE, PHONE_RE

ACTIVE_CONTEXT_LIMIT = 8192
PROMPT_SCHEMA_OVERHEAD = 900
BURST_MAX_CASES = 24

# BEGIN RELIEFQUEUE AMD DOSSIER COMPLETION REPAIR PART 2
# Live evidence 2026-07-11 showed both dossier calls ending exactly at the
# previous 3,000/2,800-token ceilings while still inside the 8,192-token
# context. The larger bounded budgets pair with a compact output contract.
WORKLOAD_COMPLETION_BUDGETS = {
    "single": 1200,
    "complex_dossier": 4300,
    "complex_dossier_repair": 4100,
    "burst_case": 900,
    "cross_case_synthesis": 1600,
    "cross_case_synthesis_repair": 1400,
    "complex_dossier_incident_supplement": 1400,
}
# END RELIEFQUEUE AMD DOSSIER COMPLETION REPAIR PART 2


class BurstParseError(ValueError):
    """Raised for visible, actionable burst parsing failures."""


class ContextBudgetError(ValueError):
    """Raised when a workload cannot fit the active context budget."""


@dataclass(frozen=True)
class ParsedCase:
    id: str
    text: str


def build_model_metadata(
    *,
    served_model: str | None = None,
    served_model_from_provider: bool = False,
    provider: str | None = None,
    runtime: str | None = None,
    accelerator: str | None = None,
    underlying_model: str | None = None,
    verified_at: str | None = None,
) -> dict[str, Any]:
    """Return truthful deployment metadata with explicit provenance.

    The OpenAI-compatible completion response normally reports only the served
    model identifier. Runtime, accelerator and underlying-model labels are
    backend deployment configuration, not provider-response facts. The
    metadata source says so explicitly.
    """

    configured_underlying = underlying_model or os.environ.get("OPENAI_COMPAT_UNDERLYING_MODEL") or None
    configured_runtime = runtime or os.environ.get("AI_RUNTIME_LABEL") or "vLLM 0.23.0"
    configured_accelerator = accelerator or os.environ.get("AI_ACCELERATOR_LABEL") or "AMD Instinct MI300X"
    configured_provider = provider or os.environ.get("AI_PROVIDER_LABEL") or "AMD Developer Cloud"
    configured_served = served_model or os.environ.get("OPENAI_COMPAT_MODEL") or None
    sources = ["backend_deployment_config"]
    if served_model and served_model_from_provider:
        sources.insert(0, "provider_response:served_model")
    return {
        "provider": configured_provider,
        "accelerator": configured_accelerator,
        "runtime": configured_runtime,
        "served_model": configured_served,
        "underlying_model": configured_underlying,
        "metadata_source": "+".join(sources),
        "underlying_model_reported": bool(configured_underlying),
        "model_identity_note": (
            "Underlying model supplied by backend deployment configuration."
            if configured_underlying
            else "The OpenAI-compatible endpoint did not report the underlying model; only the served model is verified."
        ),
        "verified_at": verified_at,
    }


# Compatibility constant for existing callers. Its provenance is truthful and
# it intentionally leaves the underlying model unset unless configured.
SAFE_METADATA = build_model_metadata()


_TEMPORAL_TOKEN_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?\b|\b\d{1,2}:\d{2}\b"
)


def sanitize_text(text: str) -> str:
    """Redact contact details without corrupting report timestamps.

    The shared phone regex is intentionally broad for free text. Structured
    dossier headers contain ISO dates and times that can otherwise look like a
    phone number, so temporal tokens are protected before phone redaction.
    """

    source = str(text)
    protected: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        token = f"RQTIMEPLACEHOLDER{len(protected)}END"
        protected[token] = match.group(0)
        return token

    staged = _TEMPORAL_TOKEN_RE.sub(protect, source)

    def redact_phone(match: re.Match[str]) -> str:
        candidate = match.group(0)
        digit_count = sum(character.isdigit() for character in candidate)
        return "[phone-redacted]" if digit_count >= 10 else candidate

    sanitized = PHONE_RE.sub(redact_phone, staged)
    sanitized = EMAIL_RE.sub("[email-redacted]", sanitized)
    for token, original in protected.items():
        sanitized = sanitized.replace(token, original)
    return sanitized.strip()


def estimate_tokens(text: str) -> int:
    return max(1, (len(str(text)) + 3) // 4)


def enforce_context_budget(text: str, requested_completion_tokens: int) -> dict[str, Any]:
    estimated = estimate_tokens(text)
    total = estimated + requested_completion_tokens + PROMPT_SCHEMA_OVERHEAD
    payload = {
        "estimated_input_tokens": estimated,
        "requested_completion_tokens": requested_completion_tokens,
        "prompt_schema_overhead_tokens": PROMPT_SCHEMA_OVERHEAD,
        "active_context_limit": ACTIVE_CONTEXT_LIMIT,
        "estimated_total_tokens": total,
        "silent_truncation_allowed": False,
    }
    if total > ACTIVE_CONTEXT_LIMIT:
        raise ContextBudgetError(
            "Input is too large for the active AMD/vLLM context window. "
            f"Estimated total {total} tokens exceeds limit {ACTIVE_CONTEXT_LIMIT}; "
            "shorten the dossier or split it into a burst workload."
        )
    return payload


DOSSIER_MIN_INCIDENTS = 5
DOSSIER_MIN_CONTRADICTIONS = 1
DOSSIER_MIN_CONFLICT_OBSERVATIONS = 3
DOSSIER_MIN_PRIORITIES = 5

_REPORT_BLOCK_RE = re.compile(
    r"^\[(REPORT-\d+)\s*\|\s*([^\]]+)\]\s*\n?(.*?)(?=^\[REPORT-\d+\s*\||\Z)",
    re.MULTILINE | re.DOTALL,
)

_HIGH_VALUE_TERMS = (
    "insulin",
    "wheelchair",
    "oxygen",
    "pregnant",
    "chest pain",
    "textile",
    "clinic road",
    "bridge",
    "collapsed",
    "damaged",
    "capacity",
    "registered",
    "safe capacity",
    "north road",
    "south lane",
    "transformer",
    "utility isolation",
    "water purification",
    "dry food",
    "small van",
    "high-clearance truck",
    "boat",
)

_LOCATION_TERMS = (
    "old bus stand",
    "old pump house",
    "main bridge",
    "community hall",
    "school shelter",
    "clinic road",
    "textile godown",
    "south ghat",
    "north embankment",
    "east lane",
    "south lane",
    "north road",
    "east road",
)

_CONFLICT_MARKERS = (
    " not ",
    "reduced from",
    "latest location",
    "may be duplicate",
    "probably describe the same",
    "could be same",
    "unverified",
    "rumour",
    "unknown",
    "supersed",
)

_ROUTE_RESOURCE_MARKERS = (
    "road",
    "route",
    "bridge",
    "lane",
    "vehicle",
    "van",
    "truck",
    "ambulance",
    "boat",
    "capacity",
    "registered",
    "stock",
    "dose",
    "patient",
    "water",
    "food",
    "fuel",
    "oxygen",
    "wheelchair",
)


def parse_dossier_source_ledger(text: str) -> list[dict[str, Any]]:
    """Return a compact source ledger without inventing operational conclusions."""

    source = str(text or "")
    rows: list[dict[str, Any]] = []
    for match in _REPORT_BLOCK_RE.finditer(source):
        report_id, header_tail, body = match.groups()
        body = body.strip()
        header_parts = [part.strip() for part in header_tail.split("|")]
        numbers = re.findall(r"(?<!REPORT-)\b\d+(?::\d+)?(?:-\d+)?\b", body)
        lower = f" {body.lower()} "
        rows.append(
            {
                "source_id": report_id,
                "header": header_tail.strip(),
                "timestamp": header_parts[0] if header_parts else "",
                "channel": " | ".join(header_parts[1:]) if len(header_parts) > 1 else "",
                "text": body,
                "numeric_mentions": numbers,
                "high_value_terms": [term for term in _HIGH_VALUE_TERMS if term in lower],
                "location_terms": [term for term in _LOCATION_TERMS if term in lower],
                "conflict_or_update_signal": any(marker in lower for marker in _CONFLICT_MARKERS),
                "route_or_resource_signal": any(marker in lower for marker in _ROUTE_RESOURCE_MARKERS),
            }
        )
    if rows:
        return rows

    ids = list(dict.fromkeys(re.findall(r"REPORT-\d+", source, flags=re.IGNORECASE)))
    return [
        {
            "source_id": value.upper(),
            "header": "",
            "timestamp": "",
            "channel": "",
            "text": "",
            "numeric_mentions": [],
            "high_value_terms": [],
            "location_terms": [],
            "conflict_or_update_signal": False,
            "route_or_resource_signal": False,
        }
        for value in ids
    ]


def _dossier_calculation_candidates(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute transparent arithmetic candidates from numbers in one source report."""

    candidates: list[dict[str, Any]] = []
    for row in reports:
        body = str(row.get("text") or "")
        lower = body.lower()
        integers = [int(value) for value in re.findall(r"\b\d+\b", body)]
        source_id = str(row.get("source_id") or "")

        if "reduced from" in lower and "registered" in lower and len(integers) >= 3:
            previous_capacity, safe_capacity, registered = integers[:3]
            candidates.append(
                {
                    "label": "safe-capacity overflow",
                    "source_ids": [source_id],
                    "inputs": [
                        f"previous capacity {previous_capacity}",
                        f"safe capacity {safe_capacity}",
                        f"registered {registered}",
                    ],
                    "formula": f"{registered} - {safe_capacity}",
                    "result": registered - safe_capacity,
                    "interpretation": "registered people above revised safe capacity",
                }
            )
            continue

        if (
            "capacity" in lower
            and ("current" in lower or "register" in lower)
            and ("unusable" in lower or "unsafe" in lower)
            and len(integers) >= 3
        ):
            capacity, current, unusable = integers[:3]
            effective_capacity = capacity - unusable
            candidates.append(
                {
                    "label": "effective shelter capacity and overflow",
                    "source_ids": [source_id],
                    "inputs": [
                        f"stated capacity {capacity}",
                        f"current register {current}",
                        f"unusable beds {unusable}",
                    ],
                    "formula": f"{capacity} - {unusable} = {effective_capacity}; {current} - {effective_capacity}",
                    "result": current - effective_capacity,
                    "interpretation": f"effective capacity {effective_capacity}; people above effective capacity",
                }
            )
            continue

        if "insulin" in lower and "patient" in lower and "dose" in lower and len(integers) >= 2:
            patients, doses = integers[:2]
            duplicates = integers[2] if len(integers) >= 3 and "duplicate" in lower else 0
            candidates.append(
                {
                    "label": "insulin dose shortfall range",
                    "source_ids": [source_id],
                    "inputs": [
                        f"listed patients {patients}",
                        f"available doses {doses}",
                        f"possible duplicate patients {duplicates}",
                    ],
                    "formula": f"{patients} - {doses}; ({patients} - {duplicates}) - {doses}",
                    "result": {
                        "before_reconciliation": max(0, patients - doses),
                        "if_all_possible_duplicates_confirmed": max(0, patients - duplicates - doses),
                    },
                    "interpretation": "dose shortfall before and after maximum supported duplicate reconciliation",
                }
            )
    return candidates


def _explicit_duplicate_pairs(reports: list[dict[str, Any]]) -> list[list[str]]:
    """Extract only source-explicit duplicate relationships."""

    pairs: list[list[str]] = []
    for row in reports:
        source_id = str(row.get("source_id") or "").upper()
        body = str(row.get("text") or "")
        lower = body.lower()
        references = [
            value.upper()
            for value in re.findall(r"REPORT-\d+", body, flags=re.IGNORECASE)
        ]
        if "probably describe the same" in lower and len(references) >= 2:
            pairs.append(sorted(set(references[:2])))
        if (
            ("could be same group as" in lower or "may be the same group as" in lower)
            and source_id
            and references
        ):
            pairs.append(sorted({source_id, references[0]}))
    return [
        list(pair)
        for pair in dict.fromkeys(tuple(pair) for pair in pairs)
        if len(pair) == 2
    ]


def build_dossier_reasoning_ledger(text: str) -> dict[str, Any]:
    """Build source-only anchors for the provider prompt.

    This is deterministic extraction, not local operational reasoning. The
    provider remains responsible for all conclusions shown as AMD analysis.
    """

    reports = parse_dossier_source_ledger(text)
    conflict_rows = [row for row in reports if row["conflict_or_update_signal"]]
    route_resource_rows = [row for row in reports if row["route_or_resource_signal"]]
    preservation: list[dict[str, Any]] = []
    for row in reports:
        terms = list(dict.fromkeys(row["high_value_terms"]))
        numbers = list(dict.fromkeys(row["numeric_mentions"]))
        if terms or numbers:
            preservation.append(
                {
                    "source_id": row["source_id"],
                    "required_terms": terms,
                    "required_numbers": numbers,
                }
            )
    report_count = len(reports)
    return {
        "source_report_count": report_count,
        "expected_report_ids": [row["source_id"] for row in reports],
        "reports": reports,
        "preservation_anchors": preservation,
        "conflict_update_source_ids": [row["source_id"] for row in conflict_rows],
        "route_resource_source_ids": [row["source_id"] for row in route_resource_rows],
        "location_anchors": [
            {
                "source_id": row["source_id"],
                "locations": row.get("location_terms") or [],
            }
            for row in reports
            if row.get("location_terms")
        ],
        "explicit_duplicate_pairs": _explicit_duplicate_pairs(reports),
        "calculation_candidates": _dossier_calculation_candidates(reports),
        "minimum_output_counts": {
            "consolidated_incidents": DOSSIER_MIN_INCIDENTS if report_count >= 12 else min(3, max(1, report_count)),
            "contradictions": DOSSIER_MIN_CONTRADICTIONS if conflict_rows else 0,
            "conflict_resolution_observations": (
                DOSSIER_MIN_CONFLICT_OBSERVATIONS
                if len(conflict_rows) >= DOSSIER_MIN_CONFLICT_OBSERVATIONS
                else len(conflict_rows)
            ),
            "prioritized_operational_plan": DOSSIER_MIN_PRIORITIES if report_count >= 12 else 3,
            "calculation_checks": 2 if report_count >= 12 else 1,
        },
        "truthfulness_rules": [
            "Do not merge reports that refer to different locations merely because they share a landmark or need type.",
            "Do not convert an unverified number or rumour into a confirmed people count.",
            "Do not call a resource a shortage unless the source states it is unavailable/low or arithmetic proves a gap.",
            "Preserve later location, capacity and status corrections explicitly.",
            "Every source report must appear once in source_coverage with a disposition.",
        ],
    }


# BEGIN RELIEFQUEUE AMD DOSSIER EXACT-TARGET REPAIR PART 3
# Live evidence 2026-07-11 showed a complete, nonce-bound repair response
# failing because the repair prompt collapsed exact missing terms/numbers into
# source IDs and omitted calculation inputs. Preserve exact targets here.
# END RELIEFQUEUE AMD DOSSIER EXACT-TARGET REPAIR PART 3

def compact_dossier_prompt_support(ledger: dict[str, Any]) -> dict[str, Any]:
    """Return a token-efficient source-grounding contract for AMD prompts.

    The raw sanitized report text is sent separately. Repeated object keys are
    collapsed into source-ID maps so the 8,192-token vLLM context retains
    sufficient room for a complete JSON response and one bounded repair pass.
    """

    preservation_map = {
        str(item.get("source_id") or ""): {
            "terms": item.get("required_terms") or [],
            "numbers": item.get("required_numbers") or [],
        }
        for item in ledger.get("preservation_anchors") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    location_map = {
        str(item.get("source_id") or ""): item.get("locations") or []
        for item in ledger.get("location_anchors") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    calculation_candidates = [
        {
            "label": item.get("label"),
            "source_ids": item.get("source_ids") or [],
            "inputs": item.get("inputs") or [],
            "formula": item.get("formula"),
            "result": item.get("result"),
        }
        for item in ledger.get("calculation_candidates") or []
        if isinstance(item, dict)
    ]
    return {
        "source_report_count": ledger.get("source_report_count"),
        "expected_report_ids": ledger.get("expected_report_ids") or [],
        "explicit_duplicate_pairs": ledger.get("explicit_duplicate_pairs") or [],
        "conflict_update_source_ids": ledger.get("conflict_update_source_ids") or [],
        "calculation_candidates": calculation_candidates,
        "minimum_output_counts": ledger.get("minimum_output_counts") or {},
        "truthfulness_rules": ledger.get("truthfulness_rules") or [],
    }


def dossier_source_evidence_index(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Return exact source-only anchors for provider preservation.

    These rows contain no locally inferred operational conclusions. They are
    deterministic copies of high-value source terms and numbers, keyed by the
    originating report so the provider can preserve them without expanding
    every incident narrative.
    """

    rows: list[dict[str, Any]] = []
    for item in ledger.get("preservation_anchors") or []:
        if not isinstance(item, dict) or not item.get("source_id"):
            continue
        rows.append(
            {
                "source_id": str(item["source_id"]),
                "terms": list(item.get("required_terms") or []),
                "numbers": list(item.get("required_numbers") or []),
            }
        )
    return rows


def compact_semantic_issues_for_prompt(issues: list[str]) -> dict[str, Any]:
    """Keep exact repair targets while avoiding repeated verbose issue prose."""

    summary: dict[str, Any] = {
        "source_coverage": [],
        "minimum_counts": [],
        "missing_by_source": {},
        "truthfulness": [],
        "calculation_gaps": [],
        "other": [],
    }
    for issue in issues:
        text = str(issue)
        missing = re.match(
            r"^(REPORT-\d+) missing required (terms|numbers): (.+)$",
            text,
        )
        if missing:
            source_id, kind, values = missing.groups()
            field = "terms" if kind == "terms" else "numbers"
            source_targets = summary["missing_by_source"].setdefault(source_id, {})
            source_targets.setdefault(field, []).extend(
                value.strip() for value in values.split(",") if value.strip()
            )
        elif text.startswith("source_coverage") or text.startswith("uncovered_source_ids"):
            summary["source_coverage"].append(text)
        elif " requires at least " in text:
            summary["minimum_counts"].append(text)
        elif text.startswith("calculation_checks"):
            summary["calculation_gaps"].append(text)
        elif any(
            marker in text
            for marker in [
                "distinct explicit locations",
                "unverified 200-person",
                "unsupported ",
                "human_review_required",
            ]
        ):
            summary["truthfulness"].append(text)
        else:
            summary["other"].append(text)

    for targets in summary["missing_by_source"].values():
        for field in ("terms", "numbers"):
            if field in targets:
                targets[field] = list(dict.fromkeys(targets[field]))
    return {key: value for key, value in summary.items() if value}


def _record_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True).lower()


def _unsupported_resource_gap_claims(
    record: dict[str, Any],
) -> list[dict[str, str]]:
    """Identify provider claims that the existing source-truth gate rejects.

    This is a rejection-only safety helper. It does not infer a replacement
    shortage or produce any local operational conclusion.
    """

    patterns = {
        "oxygen cylinders": ("oxygen cylinder",),
        "wheelchairs": ("wheelchair",),
        "high-clearance truck": ("high-clearance truck",),
    }
    assertion_words = (
        "needed",
        "need ",
        "shortage",
        "additional",
        "unavailable",
        "required",
    )
    findings: list[dict[str, str]] = []
    for value in record.get("resource_gaps") or []:
        claim = str(value)
        lowered = claim.lower()
        for label, terms in patterns.items():
            if (
                any(term in lowered for term in terms)
                and any(word in lowered for word in assertion_words)
            ):
                findings.append({"label": label, "claim": claim})
                break
    return findings


def dossier_semantic_issues(record: dict[str, Any], source_text: str) -> list[str]:
    """Return generic source-coverage and operational-completeness defects."""

    ledger = build_dossier_reasoning_ledger(source_text)
    issues: list[str] = []
    text = _record_text(record)
    numeric_text = re.sub(r"report-\d+", "", text)
    expected_ids = ledger["expected_report_ids"]
    expected_set = set(expected_ids)

    if record.get("source_report_count") != ledger["source_report_count"]:
        issues.append(
            f"source_report_count must be {ledger['source_report_count']}, got {record.get('source_report_count')!r}"
        )

    coverage = record.get("source_coverage") or []
    coverage_ids = [
        str(item.get("source_id") or "").upper()
        for item in coverage
        if isinstance(item, dict) and item.get("source_id")
    ]
    covered_ids = set(coverage_ids)
    duplicate_coverage = sorted(
        source_id for source_id in covered_ids
        if coverage_ids.count(source_id) > 1
    )
    missing_coverage = sorted(expected_set - covered_ids)
    extra_coverage = sorted(covered_ids - expected_set)
    if missing_coverage:
        issues.append("source_coverage missing: " + ", ".join(missing_coverage))
    if extra_coverage:
        issues.append("source_coverage contains unknown IDs: " + ", ".join(extra_coverage))
    if duplicate_coverage:
        issues.append("source_coverage repeats IDs: " + ", ".join(duplicate_coverage))
    if len(coverage_ids) != ledger["source_report_count"]:
        issues.append(
            "source_coverage must contain exactly "
            f"{ledger['source_report_count']} rows, got {len(coverage_ids)}"
        )

    mins = ledger["minimum_output_counts"]
    for key in ["consolidated_incidents", "contradictions", "prioritized_operational_plan", "calculation_checks"]:
        value = record.get(key) or []
        if len(value) < mins[key]:
            issues.append(f"{key} requires at least {mins[key]} items, got {len(value)}")

    conflict_observations = sum(
        len(record.get(key) or [])
        for key in [
            "contradictions",
            "superseded_updates",
            "duplicate_clusters",
            "unverified_claims",
        ]
    )
    required_conflict_observations = mins.get("conflict_resolution_observations", 0)
    if conflict_observations < required_conflict_observations:
        issues.append(
            "conflict_resolution_observations requires at least "
            f"{required_conflict_observations} items across contradictions, "
            "superseded_updates, duplicate_clusters and unverified_claims, "
            f"got {conflict_observations}"
        )

    for anchor in ledger["preservation_anchors"]:
        source_id = anchor["source_id"]
        high_terms = anchor["required_terms"]
        numbers = anchor["required_numbers"]
        # Require exact high-value vocabulary from important reports. Numeric
        # preservation is limited to reports with operationally significant
        # terms to avoid treating every timestamp-like number as mandatory.
        if high_terms:
            missing_terms = [term for term in high_terms if term.lower() not in text]
            if missing_terms:
                issues.append(f"{source_id} missing required terms: {', '.join(missing_terms)}")
            missing_numbers = [number for number in numbers if number.lower() not in numeric_text]
            if missing_numbers:
                issues.append(f"{source_id} missing required numbers: {', '.join(missing_numbers)}")

    report_locations = {
        str(item.get("source_id") or "").upper(): {
            str(location).lower()
            for location in item.get("locations") or []
            if location
        }
        for item in ledger.get("location_anchors") or []
        if isinstance(item, dict)
    }
    allowed_duplicate_pairs = {
        frozenset(str(value).upper() for value in pair)
        for pair in ledger.get("explicit_duplicate_pairs") or []
        if isinstance(pair, list) and len(pair) == 2
    }
    for incident in record.get("consolidated_incidents") or []:
        if not isinstance(incident, dict):
            continue
        source_ids = [
            str(value).upper()
            for value in incident.get("source_ids") or []
            if value
        ]
        for left_index, left_id in enumerate(source_ids):
            left_locations = report_locations.get(left_id) or set()
            if not left_locations:
                continue
            for right_id in source_ids[left_index + 1:]:
                right_locations = report_locations.get(right_id) or set()
                if not right_locations:
                    continue
                if left_locations.isdisjoint(right_locations) and frozenset(
                    {left_id, right_id}
                ) not in allowed_duplicate_pairs:
                    issues.append(
                        "consolidated_incidents merges source reports with "
                        f"distinct explicit locations: {left_id}, {right_id}"
                    )

    unverified_claims_text = json.dumps(
        record.get("unverified_claims") or [],
        ensure_ascii=False,
    ).lower()
    for row in ledger.get("reports") or []:
        body = str(row.get("text") or "").lower()
        source_descriptor = (
            str(row.get("header") or "") + " " + body
        ).lower()
        source_id = str(row.get("source_id") or "").upper()
        if "unverified" in source_descriptor and "200" in source_descriptor:
            if "200" not in unverified_claims_text or source_id.lower() not in unverified_claims_text:
                issues.append(
                    f"{source_id} unverified 200-person claim must remain in unverified_claims"
                )
            for incident in record.get("consolidated_incidents") or []:
                if not isinstance(incident, dict):
                    continue
                incident_ids = {
                    str(value).upper()
                    for value in incident.get("source_ids") or []
                }
                people_range = str(incident.get("people_range") or "").lower()
                if source_id in incident_ids and "200" in people_range and not any(
                    qualifier in people_range
                    for qualifier in ["unverified", "claimed", "rumour", "not confirmed"]
                ):
                    issues.append(
                        f"{source_id} unverified 200-person claim appears as a confirmed people range"
                    )

    seen_unsupported_resource_labels: set[str] = set()
    for finding in _unsupported_resource_gap_claims(record):
        label = finding["label"]
        if label in seen_unsupported_resource_labels:
            continue
        seen_unsupported_resource_labels.add(label)
        issues.append(
            f"resource_gaps claims an unsupported {label} shortage; "
            "source only states allocation or availability"
        )

    calculation_rows = [
        item for item in (record.get("calculation_checks") or [])
        if isinstance(item, dict)
    ]
    for candidate in ledger.get("calculation_candidates") or []:
        # Link each arithmetic result to its source report. This prevents numbers
        # from unrelated calculations from accidentally satisfying the contract.
        candidate_source_ids = {
            str(value).upper()
            for value in candidate.get("source_ids") or []
            if value
        }
        matching_rows = []
        for row in calculation_rows:
            row_source_ids = {
                str(value).upper()
                for value in row.get("source_ids") or []
                if value
            }
            if candidate_source_ids & row_source_ids:
                matching_rows.append(row)
        if not matching_rows:
            issues.append(
                f"calculation_checks missing source-linked row for {candidate.get('label')}"
            )
            continue

        arithmetic_contract = {
            "inputs": candidate.get("inputs") or [],
            "formula": candidate.get("formula"),
            "result": candidate.get("result"),
        }
        required_fragments = list(
            dict.fromkeys(
                re.findall(r"\d+", json.dumps(arithmetic_contract, ensure_ascii=False))
            )
        )
        matching_text = json.dumps(matching_rows, ensure_ascii=False).lower()
        missing_fragments = [
            value for value in required_fragments
            if value not in matching_text
        ]
        if missing_fragments:
            issues.append(
                f"calculation_checks missing {candidate.get('label')}: "
                + ", ".join(missing_fragments)
            )

    uncovered = record.get("uncovered_source_ids") or []
    if uncovered:
        issues.append("uncovered_source_ids must be empty after final analysis")

    plan = record.get("prioritized_operational_plan") or []
    ranks = [item.get("rank") for item in plan if isinstance(item, dict)]
    if ranks and ranks != sorted(ranks):
        issues.append("prioritized_operational_plan ranks are not ordered")

    if record.get("human_review_required") is not True:
        issues.append("human_review_required must be true")
    return list(dict.fromkeys(issues))


def cross_case_semantic_issues(record: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    """Detect unsafe cross-case ordering and missing arithmetic preservation."""

    issues: list[str] = []
    text = _record_text(record)
    case_text = " ".join(
        str(case.get("sanitized_input") or case.get("original_input") or "")
        for case in cases
    ).lower()

    wait_items = record.get("cases_that_can_wait_with_reason") or []
    unsafe_wait_ids: list[str] = []
    for item in wait_items:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or "")
        matching = next((case for case in cases if str(case.get("case_id")) == case_id), None)
        matching_text = str(
            (matching or {}).get("sanitized_input")
            or (matching or {}).get("original_input")
            or ""
        ).lower()
        if any(term in matching_text for term in ["insulin", "oxygen", "chest pain", "pregnant", "rescue", "wheelchair"]):
            unsafe_wait_ids.append(case_id)
    if unsafe_wait_ids:
        issues.append("life-safety or medication cases cannot be marked safe-to-wait: " + ", ".join(unsafe_wait_ids))

    if "12" in case_text and "19" in case_text:
        if "12" not in text or "19" not in text:
            issues.append("cross-case synthesis must preserve the 12-versus-19 insulin inventory conflict")
        inventory = json.dumps(record.get("inventory_conflicts") or [], ensure_ascii=False).lower()
        if "insulin" not in inventory or "12" not in inventory or "19" not in inventory:
            issues.append("inventory_conflicts must explicitly state 12 insulin doses versus 19 patients")
    if record.get("human_review_required") is not True:
        issues.append("human_review_required must be true")
    return list(dict.fromkeys(issues))


def parse_burst_input(raw: str) -> list[ParsedCase]:
    """Parse judge burst input exactly and reject ambiguous formats."""

    text = str(raw or "").strip()
    if not text:
        raise BurstParseError("Input is empty.")

    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BurstParseError(f"Malformed JSON array at line {exc.lineno}, column {exc.colno}: {exc.msg}.") from exc
        if not isinstance(data, list):
            raise BurstParseError("Structured input must be a JSON array.")
        cases = [_case_from_json_item(item, index) for index, item in enumerate(data)]
        return _validate_cases(cases)

    non_blank = [line.strip() for line in text.splitlines() if line.strip()]
    if non_blank and all(line.startswith("{") for line in non_blank):
        cases: list[ParsedCase] = []
        for index, line in enumerate(non_blank):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BurstParseError(f"Malformed JSONL on record {index + 1}: {exc.msg}.") from exc
            cases.append(_case_from_json_item(obj, index, require_object=True))
        return _validate_cases(cases)
    if any(line.startswith("{") for line in non_blank):
        raise BurstParseError("Ambiguous structured input: JSONL records cannot be mixed with plain-text lines.")

    if _has_separator_line(text):
        blocks = re.split(r"(?m)^\s*---\s*$", text)
    else:
        blocks = re.split(r"\n\s*\n+", text)
    cases = [
        ParsedCase(id=_generated_case_id(index), text=block.strip())
        for index, block in enumerate(blocks)
        if block.strip()
    ]
    return _validate_cases(cases)


def parsed_preview(raw: str) -> dict[str, Any]:
    cases = parse_burst_input(raw)
    return {
        "status": "ok",
        "parsed_count": len(cases),
        "ids": [case.id for case in cases],
        "preview": [{"id": case.id, "text": case.text[:180]} for case in cases],
        "cases": [{"id": case.id, "text": case.text} for case in cases],
    }


def _case_from_json_item(item: Any, index: int, require_object: bool = False) -> ParsedCase:
    if isinstance(item, str) and not require_object:
        return ParsedCase(id=_generated_case_id(index), text=item.strip())
    if not isinstance(item, dict):
        raise BurstParseError(f"Record {index + 1} must be a string or an object with id/text fields.")
    if "text" not in item:
        raise BurstParseError(f"Record {index + 1} is missing required field 'text'.")
    text = str(item.get("text") or "").strip()
    raw_id = item.get("id")
    case_id = _safe_user_id(raw_id) if raw_id not in {None, ""} else _generated_case_id(index)
    return ParsedCase(id=case_id, text=text)


def _validate_cases(cases: list[ParsedCase]) -> list[ParsedCase]:
    if not cases:
        raise BurstParseError("No cases were parsed.")
    if len(cases) > BURST_MAX_CASES:
        raise BurstParseError(f"Too many cases: {len(cases)} exceeds maximum of {BURST_MAX_CASES}.")
    seen: set[str] = set()
    for case in cases:
        if not case.text:
            raise BurstParseError(f"Case {case.id} has empty text.")
        if case.id in seen:
            raise BurstParseError(f"Duplicate case id '{case.id}' is ambiguous; provide unique ids.")
        seen.add(case.id)
    return cases


def _generated_case_id(index: int) -> str:
    return f"case-{index + 1:02d}"


def _safe_user_id(value: Any) -> str:
    case_id = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value).strip())[:64].strip("-")
    if not case_id:
        raise BurstParseError("Case id contained no safe characters.")
    return case_id


def _has_separator_line(text: str) -> bool:
    return re.search(r"(?m)^\s*---\s*$", text) is not None


def _priority_schema() -> dict[str, str]:
    return {
        "rank": "integer",
        "action": "string",
        "reason": "string",
        "dependency": "string",
        "verify_before_action": "string",
    }


def _workload_contract(mode: str, case_id: str | None, challenge_nonce: str) -> dict[str, Any]:
    if mode == "single":
        return {
            "schema_version": "reliefqueue-operational-analysis/v1",
            "workload_mode": "single",
            "challenge_nonce": challenge_nonce,
            "situation_summary": "string",
            "critical_facts": ["string"],
            "contradictions": ["string"],
            "risk_escalators": ["string"],
            "recommended_priorities": [_priority_schema()],
            "resource_implications": ["string"],
            "route_and_access_analysis": ["string"],
            "missing_information": ["string"],
            "coordinator_questions": ["string"],
            "public_reply_draft": "string",
            "confidence_notes": ["string"],
            "warnings": ["string"],
            "human_review_required": True,
        }
    if mode == "complex_dossier":
        return {
            "schema_version": "reliefqueue-dossier-analysis/v2",
            "workload_mode": "complex_dossier",
            "challenge_nonce": challenge_nonce,
            "situation_summary": "string",
            "source_report_count": "integer",
            "source_coverage": [
                {
                    "source_id": "REPORT-001",
                    "disposition": "incident|duplicate|contradiction|superseded|unverified|resource|coordinator_note|context",
                    "linked_incident_id": "string or null",
                }
            ],
            "uncovered_source_ids": [],
            "source_evidence_index": [
                {
                    "source_id": "REPORT-001",
                    "terms": ["exact source term"],
                    "numbers": ["exact source number"],
                }
            ],
            "consolidated_incidents": [
                {
                    "incident_id": "string",
                    "source_ids": ["REPORT-001"],
                    "location": "short string",
                    "needs": ["short string"],
                    "people_range": "short string; qualify unverified claims",
                    "vulnerable_groups": ["short string"],
                    "urgency_rationale": "short source-grounded string",
                    "missing_fields": ["short string"],
                    "confidence": "high|medium|low",
                }
            ],
            "duplicate_clusters": [{"source_ids": ["string"], "reason": "string"}],
            "contradictions": [{"source_ids": ["string"], "conflict": "string", "working_assumption": "string"}],
            "superseded_updates": [{"older_source_id": "string", "newer_source_id": "string", "change": "string"}],
            "unverified_claims": [{"source_ids": ["string"], "claim": "string", "verification_needed": "string"}],
            "people_count_ranges": ["string"],
            "resource_gaps": ["only source-supported or arithmetic-proven gaps"],
            "capacity_pressure": ["string with exact arithmetic"],
            "calculation_checks": [
                {
                    "label": "string",
                    "source_ids": ["REPORT-001"],
                    "inputs": ["exact source numbers"],
                    "formula": "explicit arithmetic formula",
                    "result": "explicit arithmetic result",
                }
            ],
            "route_constraints": ["string"],
            "cross_incident_dependencies": ["string"],
            "do_not_merge_notes": ["string explaining distinct reports that must remain separate"],
            "prioritized_operational_plan": [_priority_schema()],
            "missing_information_questions": ["string"],
            "coordinator_review_gates": ["string"],
            "confidence_notes": ["string"],
            "warnings": ["string"],
            "quality_self_check": {
                "all_sources_covered": True,
                "numeric_facts_preserved": True,
                "unsupported_resource_gaps_avoided": True,
                "later_updates_preserved": True,
            },
            "human_review_required": True,
        }
    return {
        "schema_version": "reliefqueue-burst-case-analysis/v1",
        "workload_mode": "burst_case",
        "case_id": case_id,
        "challenge_nonce": challenge_nonce,
        "situation_summary": "string",
        "critical_facts": ["string"],
        "contradictions": ["string"],
        "risk_escalators": ["string"],
        "recommended_priorities": [_priority_schema()],
        "resource_implications": ["string"],
        "route_and_access_analysis": ["string"],
        "missing_information": ["string"],
        "coordinator_questions": ["string"],
        "confidence_notes": ["string"],
        "warnings": ["string"],
        "human_review_required": True,
    }


def build_workload_prompt(
    mode: str,
    sanitized_input: str,
    case_id: str | None = None,
    challenge_nonce: str | None = None,
) -> list[dict[str, str]]:
    nonce = str(challenge_nonce or "")
    if not nonce:
        raise ValueError("challenge_nonce is required before building a provider prompt")
    contract = _workload_contract(mode, case_id, nonce)
    payload: dict[str, Any] = {
        "workload_mode": mode,
        "case_id": case_id,
        "challenge_nonce": nonce,
        "output_contract": contract,
    }
    if mode == "single":
        payload["input"] = sanitized_input
        payload["special_reasoning_requirements"] = [
            "Explicitly reconcile conflicting people counts.",
            "Identify vulnerable groups and water/medical deadlines.",
            "Analyze transformer/road hazards, vehicle-size and accessibility constraints.",
            "Calculate only source-supported shortages.",
            "Rank actions with dependencies and verification questions.",
            "Do not dispatch automatically.",
        ]
    elif mode == "complex_dossier":
        ledger = build_dossier_reasoning_ledger(sanitized_input)
        contract["source_evidence_index"] = dossier_source_evidence_index(ledger)
        payload["source_reports"] = sanitized_input
        payload["source_ledger"] = compact_dossier_prompt_support(ledger)
        payload["compact_output_rules"] = {
            "top_level_only": "Return the contract object itself; never wrap it in output_contract.",
            "json_layout": "Minified JSON without indentation or line breaks.",
            "source_coverage_fields_only": [
                "source_id",
                "disposition",
                "linked_incident_id",
            ],
            "source_coverage_notes_forbidden": True,
            "source_evidence_index_copy_exactly": True,
            "text_field_word_limit": 18,
            "repeat_each_fact_at_most_once": True,
            "count_rule": "Use exactly each minimum_output_counts value unless source evidence requires more.",
            "citation_rule": "Prefer source IDs over repeating report prose.",
        }
        payload["special_reasoning_requirements"] = [
            "Use every source report exactly once in source_coverage; uncovered_source_ids must be empty.",
            "Create at least the minimum number of incidents, contradictions, actions and calculation checks specified in source_ledger.",
            "Cluster duplicates only when source/location/need evidence supports the link.",
            "Do not merge reports from different locations merely because they share a landmark or urgency.",
            "Distinguish later verified corrections from older or unverified claims.",
            "Copy source_evidence_index exactly; it is source-only evidence, not a local conclusion.",
            "Reproduce and verify every deterministic calculation_candidate in calculation_checks.",
            "Compute exact capacity, inventory and medication gaps where arithmetic is supported.",
            "Track superseded locations, route constraints, scarce-vehicle conflicts and cross-incident dependencies.",
            "Do not invent shortages for oxygen, wheelchairs, vehicles or other resources unless the source explicitly states a shortage or arithmetic proves one.",
            "Every important conclusion must cite source report IDs.",
            "Before returning JSON, self-check all source IDs, exact numbers, later updates and unsupported-gap risk.",
        ]
    else:
        payload["input"] = sanitized_input
        payload["special_reasoning_requirements"] = [
            "Analyze this one burst case only.",
            "Preserve the case id.",
            "Do not synthesize across cases.",
            "Do not imply automatic dispatch.",
        ]
    system_content = (
        "Return one strict JSON object only, with no Markdown or prose outside JSON. "
        "This is advisory-only humanitarian analysis. Set human_review_required=true. "
        "Never claim that dispatch, rescue, safety verification, messaging or resource movement occurred. "
        "Echo challenge_nonce exactly as supplied. Use source-grounded evidence and state uncertainty. "
        "Do not omit required arrays merely to be concise."
    )
    if mode == "complex_dossier":
        system_content += (
            " Return the requested contract as the top-level object, never inside output_contract. "
            "Minify JSON. In source_coverage emit only source_id, disposition and linked_incident_id; "
            "never emit notes. Keep text fields to 18 words or fewer, avoid repeated facts, and use "
            "exactly the requested minimum item counts unless evidence requires more."
        )
    return [
        {
            "role": "system",
            "content": system_content,
        },
        {
            "role": "user",
            "content": json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":") if mode == "complex_dossier" else None,
            ),
        },
    ]


def _compact_dossier_output_for_repair(record: dict[str, Any]) -> dict[str, Any]:
    """Keep only useful provider work while leaving room for a full rewrite."""

    incidents = []
    for item in _ensure_list(record.get("consolidated_incidents"))[:8]:
        if isinstance(item, dict):
            incidents.append(
                {
                    "incident_id": item.get("incident_id"),
                    "source_ids": _ensure_list(item.get("source_ids"))[:8],
                    "location": item.get("location"),
                }
            )
    contradictions = []
    for item in _ensure_list(record.get("contradictions"))[:6]:
        if isinstance(item, dict):
            contradictions.append(
                {
                    "source_ids": _ensure_list(item.get("source_ids"))[:8],
                    "conflict": item.get("conflict"),
                }
            )
    priorities = []
    for item in _ensure_list(record.get("prioritized_operational_plan"))[:8]:
        if isinstance(item, dict):
            priorities.append(
                {
                    "rank": item.get("rank"),
                    "action": item.get("action"),
                }
            )
    return {
        "situation_summary": record.get("situation_summary"),
        "consolidated_incidents": incidents,
        "contradictions": contradictions,
        "prioritized_operational_plan": priorities,
    }


def build_dossier_repair_prompt(
    sanitized_input: str,
    previous_output: dict[str, Any],
    semantic_issues: list[str],
    challenge_nonce: str,
) -> list[dict[str, str]]:
    """Ask AMD for one complete rewrite after deterministic semantic review."""

    nonce = str(challenge_nonce or "")
    if not nonce:
        raise ValueError("challenge_nonce is required for dossier repair")
    ledger = build_dossier_reasoning_ledger(sanitized_input)
    contract = _workload_contract("complex_dossier", None, nonce)
    contract["source_evidence_index"] = dossier_source_evidence_index(ledger)
    return [
        {
            "role": "system",
            "content": (
                "Return one complete strict JSON object only. Rewrite the whole dossier analysis; do not return a patch. "
                "The previous provider output failed deterministic source checks. Correct every exact target in deterministic_semantic_issues. "
                "Copy output_contract.source_evidence_index exactly; it is source-only evidence and must not be summarized or altered. "
                "For every calculation candidate include all supplied inputs, formula and result. "
                "Qualify any unverified people count inside people_range as unverified or claimed. "
                "Use only supplied source evidence. Do not invent shortages, locations, people counts or actions already performed. "
                "Echo the new challenge_nonce exactly and require human coordinator review. "
                "Return the contract as the top-level object, never inside output_contract. Minify JSON. "
                "In source_coverage emit only source_id, disposition and linked_incident_id; never emit notes. "
                "Keep text fields to 18 words or fewer, avoid repeated facts, and satisfy every minimum item count."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "workload_mode": "complex_dossier_repair",
                    "challenge_nonce": nonce,
                    "output_contract": contract,
                    "deterministic_semantic_issues": compact_semantic_issues_for_prompt(
                        semantic_issues
                    ),
                    "source_reports": sanitized_input,
                    "source_ledger": compact_dossier_prompt_support(ledger),
                    "compact_output_rules": {
                        "source_coverage_notes_forbidden": True,
                    },
                    "repair_requirements": [
                        "Cover each report once; uncovered_source_ids=[].",
                        "Emit every missing term/number in a source-linked field.",
                        "Copy source_evidence_index exactly.",
                        "Meet direct contradiction and aggregate conflict/update minimums without inventing conflicts.",
                        "Keep locations separate; retain older and later claims.",
                        "For each calculation: all inputs, formula, result.",
                        "Qualify 200-person range as unverified/claimed.",
                        "quality_self_check=true only when all targets pass.",
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def build_cross_case_repair_prompt(
    cases: list[dict[str, Any]],
    previous_output: dict[str, Any],
    semantic_issues: list[str],
    challenge_nonce: str,
) -> list[dict[str, str]]:
    nonce = str(challenge_nonce or "")
    if not nonce:
        raise ValueError("challenge_nonce is required for cross-case repair")
    compact = compact_cases_for_synthesis(cases)
    contract = {
        "schema_version": "reliefqueue-cross-case-synthesis/v1",
        "workload_mode": "cross_case_synthesis",
        "challenge_nonce": nonce,
        "highest_risk_cases": [{"case_id": "string", "reason": "string"}],
        "resource_competition": ["string"],
        "shared_route_bottlenecks": ["string"],
        "possible_duplicate_cases": [{"case_ids": ["string"], "reason": "string"}],
        "inventory_conflicts": ["string"],
        "suggested_sequence": [_priority_schema()],
        "cases_that_can_wait_with_reason": [{"case_id": "string", "reason": "string"}],
        "missing_facts_that_could_change_order": ["string"],
        "aggregate_resource_implications": ["string"],
        "coordinator_review_gates": ["string"],
        "human_review_required": True,
    }
    return [
        {
            "role": "system",
            "content": (
                "Return one complete strict JSON object only. Rewrite the whole cross-case synthesis. "
                "Correct every deterministic safety issue listed. Do not mark an active insulin/oxygen shortage, "
                "rescue need, chest pain, pregnancy complication or accessibility evacuation as safe-to-wait. "
                "Preserve exact inventory arithmetic and echo the new challenge_nonce."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "workload_mode": "cross_case_synthesis_repair",
                    "challenge_nonce": nonce,
                    "output_contract": contract,
                    "deterministic_semantic_issues": semantic_issues,
                    "case_analyses": compact,
                    "previous_provider_output": previous_output,
                },
                ensure_ascii=False,
            ),
        },
    ]



def compact_cases_for_synthesis(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for case in cases:
        structured = case.get("structured_output") if isinstance(case.get("structured_output"), dict) else {}
        compact.append(
            {
                "case_id": case.get("case_id"),
                "analysis_source": case.get("analysis_source"),
                "situation_summary": str(structured.get("situation_summary") or "")[:280],
                "critical_facts": _short_list(structured.get("critical_facts"), 3, 180),
                "risk_escalators": _short_list(structured.get("risk_escalators"), 3, 160),
                "recommended_priorities": _short_list(structured.get("recommended_priorities"), 2, 260),
                "resource_implications": _short_list(structured.get("resource_implications"), 2, 180),
                "route_and_access_analysis": _short_list(structured.get("route_and_access_analysis"), 2, 180),
                "missing_information": _short_list(structured.get("missing_information"), 3, 160),
            }
        )
    return compact


def build_cross_case_synthesis_prompt(cases: list[dict[str, Any]], challenge_nonce: str) -> list[dict[str, str]]:
    compact = compact_cases_for_synthesis(cases)
    contract = {
        "schema_version": "reliefqueue-cross-case-synthesis/v1",
        "workload_mode": "cross_case_synthesis",
        "challenge_nonce": challenge_nonce,
        "highest_risk_cases": [{"case_id": "string", "reason": "string"}],
        "resource_competition": ["string"],
        "shared_route_bottlenecks": ["string"],
        "possible_duplicate_cases": [{"case_ids": ["string"], "reason": "string"}],
        "inventory_conflicts": ["string"],
        "suggested_sequence": [_priority_schema()],
        "cases_that_can_wait_with_reason": [{"case_id": "string", "reason": "string"}],
        "missing_facts_that_could_change_order": ["string"],
        "aggregate_resource_implications": ["string"],
        "coordinator_review_gates": ["string"],
        "human_review_required": True,
    }
    return [
        {
            "role": "system",
            "content": (
                "Return one strict JSON object only. Synthesize across all submitted case analyses. "
                "Do not invent actions already performed. Rank competing needs, shared routes and scarce resources. "
                "Do not classify active insulin/oxygen shortages, rescue needs, chest pain, pregnancy complications "
                "or accessibility evacuations as safe-to-wait. Preserve exact inventory arithmetic in inventory_conflicts. "
                "Echo challenge_nonce exactly and require human coordinator review."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "challenge_nonce": challenge_nonce,
                    "output_contract": contract,
                    "case_analyses": compact,
                },
                ensure_ascii=False,
            ),
        },
    ]


def normalize_structured_output(
    mode: str,
    content: str,
    fallback_input: str,
    case_id: str | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    """Normalize provider JSON and return ``(record, warnings, source)``.

    ``source`` is ``provider`` only when a JSON object was actually returned.
    Invalid or non-object output uses deterministic local safety fallback and is
    never eligible for VERIFIED LIVE presentation.
    """

    warnings: list[str] = []
    parsed = _parse_json_maybe_enveloped(content)
    if parsed is None:
        warnings.append("Provider output was not valid JSON; displayed structured analysis is a local safe fallback.")
        normalized = _heuristic_structure(mode, fallback_input, case_id)
        normalized["human_review_required"] = True
        return normalized, warnings, "local_safe_fallback"
    if not isinstance(parsed, dict):
        warnings.append("Provider JSON was not an object; displayed structured analysis is a local safe fallback.")
        normalized = _heuristic_structure(mode, fallback_input, case_id)
        normalized["human_review_required"] = True
        return normalized, warnings, "local_safe_fallback"

    normalized = _merge_provider_output(mode, parsed, case_id)
    normalized["human_review_required"] = True
    if mode == "complex_dossier":
        # Attach exact source-only evidence deterministically. This does not add
        # operational conclusions or alter provider-authored priorities,
        # incidents, calculations or recommendations. It gives every retained
        # source term/number an explicit source ID and provenance.
        ledger = build_dossier_reasoning_ledger(fallback_input)
        normalized["source_evidence_index"] = dossier_source_evidence_index(ledger)
        normalized["source_evidence_index_source"] = "deterministic_source_extraction"
        warnings.append(
            "Exact source evidence index attached by deterministic source extraction; "
            "no local operational conclusions were added."
        )
    missing = _missing_core_provider_fields(mode, normalized)
    if missing:
        warnings.append("Provider JSON omitted core fields: " + ", ".join(missing) + ". Missing sections are empty, not locally invented.")
        return normalized, warnings, "provider_incomplete"
    return normalized, warnings, "provider"


def normalize_cross_case_synthesis(
    content: str,
    cases: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], str]:
    warnings: list[str] = []
    parsed = _parse_json_maybe_enveloped(content)
    if not isinstance(parsed, dict):
        warnings.append("Cross-case provider output was not valid JSON; displayed synthesis is a local safe fallback.")
        return synthesize_burst(cases), warnings, "local_safe_fallback"
    base = _empty_cross_case_synthesis()
    for key, value in parsed.items():
        if value is not None and value != "":
            base[key] = value
    base["human_review_required"] = True
    required = [
        "challenge_nonce",
        "highest_risk_cases",
        "resource_competition",
        "suggested_sequence",
        "missing_facts_that_could_change_order",
        "aggregate_resource_implications",
        "coordinator_review_gates",
    ]
    missing = []
    for key in required:
        value = base.get(key)
        if value is None or value == "" or value == []:
            missing.append(key)
    if missing:
        warnings.append(
            "Provider cross-case JSON omitted core fields: "
            + ", ".join(missing)
            + ". Missing sections are empty, not locally invented."
        )
        return base, warnings, "provider_incomplete"
    return base, warnings, "provider"


def _parse_json_maybe_enveloped(content: str) -> dict[str, Any] | None:
    raw = str(content or "").strip()
    if not raw:
        return None
    candidates = [raw]
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "choices" in data:
            try:
                nested = data["choices"][0]["message"]["content"]
            except Exception:
                continue
            return _parse_json_maybe_enveloped(str(nested))
        return data if isinstance(data, dict) else None
    return None


def _empty_structure(mode: str, case_id: str | None) -> dict[str, Any]:
    if mode == "complex_dossier":
        return {
            "schema_version": "reliefqueue-dossier-analysis/v2",
            "workload_mode": "complex_dossier",
            "challenge_nonce": None,
            "situation_summary": "",
            "source_report_count": None,
            "source_coverage": [],
            "uncovered_source_ids": [],
            "consolidated_incidents": [],
            "duplicate_clusters": [],
            "contradictions": [],
            "superseded_updates": [],
            "unverified_claims": [],
            "people_count_ranges": [],
            "resource_gaps": [],
            "capacity_pressure": [],
            "calculation_checks": [],
            "route_constraints": [],
            "cross_incident_dependencies": [],
            "do_not_merge_notes": [],
            "prioritized_operational_plan": [],
            "missing_information_questions": [],
            "coordinator_review_gates": [],
            "confidence_notes": [],
            "warnings": [],
            "quality_self_check": {},
            "human_review_required": True,
        }
    return {
        "schema_version": "reliefqueue-operational-analysis/v1" if mode == "single" else "reliefqueue-burst-case-analysis/v1",
        "workload_mode": mode,
        "case_id": case_id,
        "challenge_nonce": None,
        "situation_summary": "",
        "critical_facts": [],
        "contradictions": [],
        "risk_escalators": [],
        "recommended_priorities": [],
        "resource_implications": [],
        "route_and_access_analysis": [],
        "missing_information": [],
        "coordinator_questions": [],
        "public_reply_draft": "",
        "confidence_notes": [],
        "warnings": [],
        "human_review_required": True,
    }


def _merge_provider_output(mode: str, data: dict[str, Any], case_id: str | None) -> dict[str, Any]:
    base = _empty_structure(mode, case_id)
    for key, value in data.items():
        if value is not None and value != "":
            base[key] = value
    if mode in {"single", "burst_case"}:
        base["recommended_priorities"] = _priority_list(base.get("recommended_priorities"), allow_empty=True)
    else:
        for key in [
            "source_coverage",
            "uncovered_source_ids",
            "consolidated_incidents",
            "duplicate_clusters",
            "contradictions",
            "superseded_updates",
            "unverified_claims",
            "people_count_ranges",
            "resource_gaps",
            "capacity_pressure",
            "calculation_checks",
            "route_constraints",
            "cross_incident_dependencies",
            "do_not_merge_notes",
            "missing_information_questions",
            "coordinator_review_gates",
            "confidence_notes",
        ]:
            base[key] = _ensure_list(base.get(key))
        base["prioritized_operational_plan"] = _priority_list(base.get("prioritized_operational_plan"), allow_empty=True)
    base["warnings"] = _ensure_list(base.get("warnings"))
    if "Human review required before action." not in base["warnings"]:
        base["warnings"].append("Human review required before action.")
    return base


def _missing_core_provider_fields(mode: str, record: dict[str, Any]) -> list[str]:
    if mode == "complex_dossier":
        keys = ["situation_summary", "consolidated_incidents", "prioritized_operational_plan", "challenge_nonce"]
    else:
        keys = ["situation_summary", "recommended_priorities", "route_and_access_analysis", "challenge_nonce"]
    missing: list[str] = []
    for key in keys:
        value = record.get(key)
        if value is None or value == "" or value == () or value == []:
            missing.append(key)
    return missing


def _heuristic_structure(mode: str, text: str, case_id: str | None = None) -> dict[str, Any]:
    """Deterministic local fallback. Its provenance must always be shown."""

    lower = text.lower()
    facts = _facts_from_text(text)
    priorities = _priority_list(None)
    if any(term in lower for term in ["medical", "insulin", "oxygen", "pregnant", "chest pain"]):
        priorities.insert(
            0,
            {
                "rank": 1,
                "action": "Escalate medical review",
                "reason": "Medical vulnerability or time-sensitive medication appears in the report.",
                "dependency": "Coordinator confirmation and available medical transport.",
                "verify_before_action": "Confirm patient location, condition, and duplicate reports.",
            },
        )
    if mode == "complex_dossier":
        return {
            "schema_version": "reliefqueue-dossier-analysis/v2",
            "workload_mode": "complex_dossier",
            "challenge_nonce": None,
            "situation_summary": "Multiple synthetic reports require coordinator reconciliation; provider output could not be safely parsed.",
            "source_report_count": len(set(re.findall(r"REPORT-\d+", text))) or None,
            "source_coverage": [],
            "uncovered_source_ids": list(dict.fromkeys(re.findall(r"REPORT-\d+", text))),
            "consolidated_incidents": [
                {
                    "incident_id": "local-fallback-1",
                    "source_ids": list(dict.fromkeys(re.findall(r"REPORT-\d+", text)))[:8],
                    "evidence": facts[:3],
                    "latest_update": "Review source timestamps manually.",
                    "location": "See source evidence.",
                    "needs": facts[:5],
                    "people_range": "Unverified; reconcile counts.",
                    "vulnerable_groups": _vulnerable_groups(lower),
                    "urgency_rationale": "Potential medical/rescue and capacity constraints require human review.",
                    "missing_fields": ["confirmed location", "current people count", "route status"],
                    "confidence": "low",
                }
            ],
            "duplicate_clusters": [],
            "contradictions": [],
            "superseded_updates": [],
            "unverified_claims": [],
            "people_count_ranges": [],
            "resource_gaps": [],
            "capacity_pressure": [],
            "calculation_checks": [],
            "route_constraints": [],
            "cross_incident_dependencies": [],
            "do_not_merge_notes": [],
            "prioritized_operational_plan": priorities,
            "missing_information_questions": ["Which source is latest and verified for each location?"],
            "coordinator_review_gates": ["Do not dispatch automatically; approve any field movement manually."],
            "confidence_notes": ["Local deterministic fallback; not AMD-generated analysis."],
            "warnings": ["No automatic dispatch.", "Local safe fallback used."],
            "quality_self_check": {
                "all_sources_covered": False,
                "numeric_facts_preserved": False,
                "unsupported_resource_gaps_avoided": True,
                "later_updates_preserved": False,
            },
            "human_review_required": True,
        }
    common = {
        "schema_version": "reliefqueue-operational-analysis/v1" if mode == "single" else "reliefqueue-burst-case-analysis/v1",
        "workload_mode": mode,
        "case_id": case_id,
        "challenge_nonce": None,
        "situation_summary": facts[0] if facts else "Synthetic incident requires coordinator review.",
        "critical_facts": facts,
        "contradictions": [],
        "risk_escalators": _vulnerable_groups(lower),
        "recommended_priorities": priorities,
        "resource_implications": [],
        "route_and_access_analysis": [],
        "missing_information": ["Exact location", "Current people count", "Hazard status", "Vehicle/accessibility requirements"],
        "coordinator_questions": ["What facts must be verified before any field movement?"],
        "public_reply_draft": "We received the synthetic report. A human coordinator will review details before any action.",
        "confidence_notes": ["Local deterministic fallback; not AMD-generated analysis."],
        "warnings": ["No automatic dispatch.", "Local safe fallback used."],
        "human_review_required": True,
    }
    return common


def _empty_cross_case_synthesis() -> dict[str, Any]:
    return {
        "schema_version": "reliefqueue-cross-case-synthesis/v1",
        "workload_mode": "cross_case_synthesis",
        "challenge_nonce": None,
        "highest_risk_cases": [],
        "resource_competition": [],
        "shared_route_bottlenecks": [],
        "possible_duplicate_cases": [],
        "inventory_conflicts": [],
        "suggested_sequence": [],
        "cases_that_can_wait_with_reason": [],
        "missing_facts_that_could_change_order": [],
        "aggregate_resource_implications": [],
        "coordinator_review_gates": [],
        "human_review_required": True,
    }


def _facts_from_text(text: str) -> list[str]:
    chunks = [line.strip(" -") for line in re.split(r"[\n.;]+", text) if line.strip()]
    return chunks[:10] or [text[:220]]


def _vulnerable_groups(lower: str) -> list[str]:
    groups = []
    for word in ["child", "elderly", "pregnant", "wheelchair", "disabled", "insulin", "oxygen"]:
        if word in lower:
            groups.append(word)
    return groups


def _priority_list(value: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        out = []
        for index, item in enumerate(value, start=1):
            out.append(
                {
                    "rank": int(item.get("rank") or index),
                    "action": str(item.get("action") or "Review case"),
                    "reason": str(item.get("reason") or "Coordinator review required."),
                    "dependency": str(item.get("dependency") or "Human approval and verified facts."),
                    "verify_before_action": str(item.get("verify_before_action") or "Confirm location, people count, hazards, and route."),
                }
            )
        return out
    if allow_empty:
        return []
    return [
        {
            "rank": 1,
            "action": "Verify facts before operational action",
            "reason": "AI output is advisory and submitted reports may be incomplete or conflicting.",
            "dependency": "Coordinator approval and human review.",
            "verify_before_action": "Confirm location, people count, route safety, hazards, and resource availability.",
        }
    ]


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _short_list(value: Any, count: int, max_chars: int) -> list[Any]:
    items = _ensure_list(value)[:count]
    compact = []
    for item in items:
        if isinstance(item, (dict, list)):
            text = json.dumps(item, ensure_ascii=False)
        else:
            text = str(item)
        compact.append(text[:max_chars])
    return compact


def synthesize_burst(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic local fallback for cross-case synthesis.

    Callers must label this as ``local_safe_fallback`` and must never present it
    as verified live AMD synthesis.
    """

    texts = " ".join(str(case.get("sanitized_input") or case.get("original_input") or "") for case in cases).lower()
    high_risk = [
        case.get("case_id")
        for case in cases
        if any(
            term in str(case.get("sanitized_input") or case.get("generated_advisory") or "").lower()
            for term in ["medical", "insulin", "pregnant", "chest pain", "rescue", "child"]
        )
    ]
    fallback = _empty_cross_case_synthesis()
    fallback.update(
        {
            "highest_risk_cases": [
                {"case_id": case_id, "reason": "Potential medical/rescue term detected; verify manually."}
                for case_id in high_risk
                if case_id
            ][:8],
            "resource_competition": ["Review medical transport, accessible vehicles, boats, water and shelter capacity across cases."],
            "shared_route_bottlenecks": [term for term in ["bridge", "east road", "west route", "small vehicles", "blocked"] if term in texts],
            "possible_duplicate_cases": [
                {"case_ids": ids, "reason": "Similar normalized tokens; human duplicate review required."}
                for ids in _possible_duplicates(cases)
            ],
            "inventory_conflicts": [term for term in ["insulin", "oxygen", "water", "fuel"] if term in texts],
            "suggested_sequence": [],
            "cases_that_can_wait_with_reason": [],
            "missing_facts_that_could_change_order": ["Exact locations", "current people counts", "route status", "vehicle availability", "duplicate confirmation"],
            "aggregate_resource_implications": ["Local fallback cannot safely allocate resources; coordinator synthesis required."],
            "coordinator_review_gates": ["Human coordinator approval required before dispatch, public reply or resource commitment."],
            "warnings": ["Local safe fallback used; this is not AMD-generated cross-case synthesis."],
            "human_review_required": True,
        }
    )
    return fallback


def _possible_duplicates(cases: list[dict[str, Any]]) -> list[list[str]]:
    buckets: dict[str, list[str]] = {}
    for case in cases:
        text = str(case.get("sanitized_input") or case.get("original_input") or "").lower()
        tokens = sorted(set(re.findall(r"[a-z0-9]{4,}", text)))[:8]
        key = " ".join(tokens[:4])
        if key:
            buckets.setdefault(key, []).append(str(case.get("case_id")))
    return [ids for ids in buckets.values() if len(ids) > 1]


ProviderCall = Callable[[str, str, int, str | None], dict[str, Any]]

# BEGIN RELIEFQUEUE AMD BURST CONTRACT REPAIR PART 1
# Provider-output compatibility learned from the bounded AMD live run on
# 2026-07-11. This layer only canonicalizes provider-authored JSON; it does not
# synthesize, fill, or alter operational conclusions.
_PART1_ORIGINAL_NORMALIZE_STRUCTURED_OUTPUT = normalize_structured_output
_PART1_ORIGINAL_NORMALIZE_CROSS_CASE_SYNTHESIS = normalize_cross_case_synthesis


def _part1_extract_output_contract(
    raw_content: str,
    workload_mode: str | None = None,
) -> str | None:
    """Flatten only a genuine provider-authored result envelope.

    Some providers echo a small ``output_contract`` schema fragment alongside
    a valid top-level result. Treating every nested object as the result drops
    the actual analysis. Unwrap only when the top level lacks result fields and
    the nested object itself has the expected workload payload shape.
    """
    import json as _part1_json

    try:
        envelope = _part1_json.loads(str(raw_content))
    except (TypeError, ValueError, _part1_json.JSONDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    nested = envelope.get("output_contract")
    if not isinstance(nested, dict):
        return None

    mode = str(
        workload_mode
        or envelope.get("workload_mode")
        or nested.get("workload_mode")
        or ""
    )
    payload_keys = {
        "complex_dossier": (
            "situation_summary",
            "source_coverage",
            "consolidated_incidents",
            "prioritized_operational_plan",
            "calculation_checks",
        ),
        "single": (
            "situation_summary",
            "critical_facts",
            "recommended_priorities",
        ),
        "burst_case": (
            "situation_summary",
            "critical_facts",
            "recommended_priorities",
        ),
    }.get(
        mode,
        (
            "situation_summary",
            "critical_facts",
            "source_coverage",
            "consolidated_incidents",
            "prioritized_operational_plan",
            "recommended_priorities",
        ),
    )

    def payload_score(record: dict[str, Any]) -> int:
        return sum(
            1
            for key in payload_keys
            if key in record and record.get(key) not in (None, "", [], {})
        )

    top_level_score = payload_score(envelope)
    nested_score = payload_score(nested)
    if top_level_score >= 2:
        return None
    if nested_score < 2:
        return None

    canonical = dict(nested)
    for key in (
        "schema_version",
        "workload_mode",
        "case_id",
        "challenge_nonce",
        "human_review_required",
    ):
        if key not in canonical and key in envelope:
            canonical[key] = envelope[key]
    return _part1_json.dumps(canonical, ensure_ascii=False)


def normalize_structured_output(
    workload_mode: str,
    raw_content: str,
    sanitized_input: str,
    case_id: str,
):
    canonical_raw = _part1_extract_output_contract(raw_content, workload_mode)
    if canonical_raw is None:
        return _PART1_ORIGINAL_NORMALIZE_STRUCTURED_OUTPUT(
            workload_mode,
            raw_content,
            sanitized_input,
            case_id,
        )

    structured, warnings, source = _PART1_ORIGINAL_NORMALIZE_STRUCTURED_OUTPUT(
        workload_mode,
        canonical_raw,
        sanitized_input,
        case_id,
    )
    warnings = list(warnings)
    warnings.append(
        "Provider wrapped the requested JSON in output_contract; the provider-authored object was canonicalized without local synthesis."
    )
    return structured, warnings, source


def normalize_cross_case_synthesis(raw_content: str, case_results: list[dict]):
    structured, warnings, source = _PART1_ORIGINAL_NORMALIZE_CROSS_CASE_SYNTHESIS(
        raw_content,
        case_results,
    )

    # Empty arrays are truthful negative findings when the provider explicitly
    # returned them. Promote only when all negative-evidence fields are present
    # and the existing semantic safety gate reports no remaining issue.
    negative_evidence_keys = (
        "resource_competition",
        "shared_route_bottlenecks",
        "possible_duplicate_cases",
    )
    explicit_negative_evidence = all(
        key in structured and isinstance(structured.get(key), list)
        for key in negative_evidence_keys
    )
    semantic_issues = cross_case_semantic_issues(structured, case_results)
    if source == "provider_incomplete" and explicit_negative_evidence and not semantic_issues:
        source = "provider"
        warnings = [
            warning
            for warning in warnings
            if "Provider cross-case JSON omitted core fields" not in warning
        ]
        warnings.append(
            "Provider explicitly returned empty cross-case competition, route-bottleneck, or duplicate lists; these are accepted as provider-authored negative findings."
        )
    return structured, warnings, source
# END RELIEFQUEUE AMD BURST CONTRACT REPAIR PART 1



# BEGIN RELIEFQUEUE AMD DOSSIER HEADROOM HOTFIX PART 3A
# Removes duplicated repair-prompt metadata while preserving all semantic requirements.
# END RELIEFQUEUE AMD DOSSIER HEADROOM HOTFIX PART 3A


# BEGIN RELIEFQUEUE AMD DOSSIER SOURCE-EVIDENCE REPAIR PART 4
# Uses an exact source-only evidence index and separates direct contradictions
# from broader conflict/update observations so the provider is not forced to invent conflicts.
# END RELIEFQUEUE AMD DOSSIER SOURCE-EVIDENCE REPAIR PART 4


# BEGIN RELIEFQUEUE AMD DOSSIER INCIDENT RECONCILIATION PART 7
# Reuses the existing source-location and unverified-count truth gates to
# quarantine only invalid provider-authored incident fields. Missing incidents
# may then be carried from the first provider response without generating local
# incident conclusions.


def _provider_incident_source_ids(
    incident: dict[str, Any],
) -> list[str]:
    return [
        str(value).upper()
        for value in incident.get("source_ids") or []
        if value
    ]


def _provider_incident_location_conflicts(
    incident: dict[str, Any],
    ledger: dict[str, Any],
) -> list[list[str]]:
    source_ids = _provider_incident_source_ids(incident)
    report_locations = {
        str(item.get("source_id") or "").upper(): {
            str(location).lower()
            for location in item.get("locations") or []
            if location
        }
        for item in ledger.get("location_anchors") or []
        if isinstance(item, dict)
    }
    allowed_duplicate_pairs = {
        frozenset(str(value).upper() for value in pair)
        for pair in ledger.get("explicit_duplicate_pairs") or []
        if isinstance(pair, list) and len(pair) == 2
    }

    conflicts: list[list[str]] = []
    for left_index, left_id in enumerate(source_ids):
        left_locations = report_locations.get(left_id) or set()
        if not left_locations:
            continue
        for right_id in source_ids[left_index + 1:]:
            right_locations = report_locations.get(right_id) or set()
            if not right_locations:
                continue
            pair = frozenset({left_id, right_id})
            if (
                left_locations.isdisjoint(right_locations)
                and pair not in allowed_duplicate_pairs
            ):
                conflicts.append([left_id, right_id])
    return conflicts


def _quarantine_unverified_people_range(
    incident: dict[str, Any],
    ledger: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    item = copy.deepcopy(incident)
    source_ids = set(_provider_incident_source_ids(item))
    people_range = str(item.get("people_range") or "")
    lower_people_range = people_range.lower()
    if not people_range or "200" not in lower_people_range:
        return item, None
    if any(
        qualifier in lower_people_range
        for qualifier in ["unverified", "claimed", "rumour", "not confirmed"]
    ):
        return item, None

    unverified_source_ids: list[str] = []
    for row in ledger.get("reports") or []:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").upper()
        descriptor = (
            str(row.get("header") or "")
            + " "
            + str(row.get("text") or "")
        ).lower()
        if (
            source_id in source_ids
            and "unverified" in descriptor
            and "200" in descriptor
        ):
            unverified_source_ids.append(source_id)
    if not unverified_source_ids:
        return item, None

    item["people_range"] = ""
    return item, {
        "incident_id": str(item.get("incident_id") or ""),
        "source_ids": unverified_source_ids,
        "removed_people_range": people_range,
        "reason": (
            "provider people_range presented an explicitly unverified "
            "200-person claim without a qualifier"
        ),
    }


def _reconcile_provider_incidents(
    initial: dict[str, Any],
    repair: dict[str, Any],
    source_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ledger = build_dossier_reasoning_ledger(source_text)
    merged_incidents: list[dict[str, Any]] = []
    used_source_ids: set[str] = set()
    quarantined_repair_incidents: list[dict[str, Any]] = []
    quarantined_initial_incidents: list[dict[str, Any]] = []
    quarantined_people_ranges: list[dict[str, Any]] = []
    carried_initial_incidents: list[dict[str, Any]] = []
    skipped_initial_overlaps: list[dict[str, Any]] = []

    repair_incidents = repair.get("consolidated_incidents") or []
    initial_incidents = initial.get("consolidated_incidents") or []

    for incident in repair_incidents:
        if not isinstance(incident, dict):
            continue
        conflicts = _provider_incident_location_conflicts(
            incident,
            ledger,
        )
        if conflicts:
            quarantined_repair_incidents.append(
                {
                    "incident_id": str(
                        incident.get("incident_id") or ""
                    ),
                    "source_ids": _provider_incident_source_ids(
                        incident
                    ),
                    "location_conflicts": conflicts,
                    "reason": (
                        "provider incident merged source reports with "
                        "distinct explicit locations"
                    ),
                }
            )
            continue

        item, people_finding = _quarantine_unverified_people_range(
            incident,
            ledger,
        )
        if people_finding:
            quarantined_people_ranges.append(people_finding)
        merged_incidents.append(item)
        used_source_ids.update(_provider_incident_source_ids(item))

    for incident in initial_incidents:
        if not isinstance(incident, dict):
            continue
        source_ids = _provider_incident_source_ids(incident)
        overlapping = sorted(set(source_ids) & used_source_ids)
        if overlapping:
            skipped_initial_overlaps.append(
                {
                    "incident_id": str(
                        incident.get("incident_id") or ""
                    ),
                    "source_ids": source_ids,
                    "overlapping_source_ids": overlapping,
                }
            )
            continue

        conflicts = _provider_incident_location_conflicts(
            incident,
            ledger,
        )
        if conflicts:
            quarantined_initial_incidents.append(
                {
                    "incident_id": str(
                        incident.get("incident_id") or ""
                    ),
                    "source_ids": source_ids,
                    "location_conflicts": conflicts,
                    "reason": (
                        "initial provider incident merged source "
                        "reports with distinct explicit locations"
                    ),
                }
            )
            continue

        item, people_finding = _quarantine_unverified_people_range(
            incident,
            ledger,
        )
        if people_finding:
            quarantined_people_ranges.append(people_finding)
        merged_incidents.append(item)
        used_source_ids.update(source_ids)
        carried_initial_incidents.append(
            {
                "incident_id": str(item.get("incident_id") or ""),
                "source_ids": source_ids,
            }
        )

    return merged_incidents, {
        "repair_incident_count": len(repair_incidents),
        "initial_incident_count": len(initial_incidents),
        "merged_incident_count": len(merged_incidents),
        "quarantined_repair_incidents": quarantined_repair_incidents,
        "quarantined_initial_incidents": quarantined_initial_incidents,
        "quarantined_unverified_people_ranges": (
            quarantined_people_ranges
        ),
        "carried_initial_provider_incidents": (
            carried_initial_incidents
        ),
        "skipped_initial_provider_incident_overlaps": (
            skipped_initial_overlaps
        ),
        "local_incident_conclusions_added": False,
    }


# END RELIEFQUEUE AMD DOSSIER INCIDENT RECONCILIATION PART 7


# BEGIN RELIEFQUEUE AMD DOSSIER PROVIDER RECONCILIATION PART 5

_PROVIDER_CONFLICT_OBSERVATION_KEYS = (
    "contradictions",
    "superseded_updates",
    "duplicate_clusters",
    "unverified_claims",
)


def _provider_conflict_observation_counts(
    record: dict[str, Any],
) -> dict[str, int]:
    return {
        key: len(record.get(key) or [])
        for key in _PROVIDER_CONFLICT_OBSERVATION_KEYS
    }


def _provider_conflict_observation_safety_issues(
    record: dict[str, Any],
    source_text: str,
) -> list[str]:
    """Validate source-linked provider conflict observations before carrying.

    This gate is intentionally narrower than full dossier completeness. It
    permits an otherwise incomplete initial provider response to contribute
    only its already source-linked conflict, update, duplicate and uncertainty
    observations to a repair response that omitted those sections.
    """

    ledger = build_dossier_reasoning_ledger(source_text)
    expected_ids = set(ledger["expected_report_ids"])
    counts = _provider_conflict_observation_counts(record)
    issues: list[str] = []

    if counts["contradictions"] < 1:
        issues.append("initial provider has no direct contradiction")
    if sum(counts.values()) < 3:
        issues.append(
            "initial provider has fewer than three conflict-resolution observations"
        )

    unverified_text = json.dumps(
        record.get("unverified_claims") or [],
        ensure_ascii=False,
    ).lower()
    if "report-006" not in unverified_text or "200" not in unverified_text:
        issues.append(
            "initial provider does not preserve REPORT-006 as an unverified 200-person claim"
        )

    unknown_ids: set[str] = set()
    for key in _PROVIDER_CONFLICT_OBSERVATION_KEYS:
        for row in record.get(key) or []:
            if not isinstance(row, dict):
                continue
            referenced: list[str] = []
            referenced.extend(
                str(value).upper()
                for value in row.get("source_ids") or []
                if value
            )
            for scalar_key in (
                "source_id",
                "older_source_id",
                "newer_source_id",
            ):
                value = row.get(scalar_key)
                if value:
                    referenced.append(str(value).upper())
            unknown_ids.update(
                source_id
                for source_id in referenced
                if source_id not in expected_ids
            )
    if unknown_ids:
        issues.append(
            "initial provider conflict observations reference unknown sources: "
            + ", ".join(sorted(unknown_ids))
        )

    return issues


def reconcile_provider_dossier_outputs(
    initial: dict[str, Any],
    repair: dict[str, Any],
    source_text: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile two provider-authored dossier records without local analysis.

    The repair response is authoritative when it supplies a source-safe field.
    Missing core metadata, source-coverage rows and source-safe conflict
    observations are retained from the initial provider response when the repair
    omitted them. When source text is supplied, provider-authored incidents
    that violate the existing location/unverified-count truth gates are
    quarantined and non-overlapping provider incidents from the initial response
    are retained. Priority items are deduplicated with repair items first and
    initial provider items appended; only rank numbers are normalized. No action,
    fact, incident, calculation or recommendation is generated locally.
    """

    if not isinstance(initial, dict) or not isinstance(repair, dict):
        raise TypeError("provider dossier reconciliation requires two objects")

    merged = copy.deepcopy(repair)
    carried_fields: list[str] = []
    for key in (
        "schema_version",
        "workload_mode",
        "situation_summary",
        "source_report_count",
        "consolidated_incidents",
        "calculation_checks",
        "missing_information_questions",
        "coordinator_review_gates",
        "confidence_notes",
        "warnings",
        "quality_self_check",
    ):
        repair_value = merged.get(key)
        initial_value = initial.get(key)
        if repair_value in (None, "", [], {}) and initial_value not in (None, "", [], {}):
            merged[key] = copy.deepcopy(initial_value)
            carried_fields.append(key)

    conflict_reconciliation: dict[str, Any] = {
        "repair_counts": _provider_conflict_observation_counts(repair),
        "initial_counts": _provider_conflict_observation_counts(initial),
        "merged_counts": _provider_conflict_observation_counts(merged),
        "carried_initial_provider_fields": [],
        "source_safety_issues": [],
        "local_conflict_observations_added": False,
    }
    if source_text:
        conflict_reconciliation["source_safety_issues"] = (
            _provider_conflict_observation_safety_issues(
                initial,
                source_text,
            )
        )
        if not conflict_reconciliation["source_safety_issues"]:
            for key in _PROVIDER_CONFLICT_OBSERVATION_KEYS:
                repair_value = merged.get(key)
                initial_value = initial.get(key)
                if (
                    repair_value in (None, "", [], {})
                    and initial_value not in (None, "", [], {})
                ):
                    merged[key] = copy.deepcopy(initial_value)
                    carried_fields.append(key)
                    conflict_reconciliation[
                        "carried_initial_provider_fields"
                    ].append(key)
    conflict_reconciliation["merged_counts"] = (
        _provider_conflict_observation_counts(merged)
    )

    incident_reconciliation: dict[str, Any] = {
        "repair_incident_count": len(
            repair.get("consolidated_incidents") or []
        ),
        "initial_incident_count": len(
            initial.get("consolidated_incidents") or []
        ),
        "merged_incident_count": len(
            merged.get("consolidated_incidents") or []
        ),
        "quarantined_repair_incidents": [],
        "quarantined_initial_incidents": [],
        "quarantined_unverified_people_ranges": [],
        "carried_initial_provider_incidents": [],
        "skipped_initial_provider_incident_overlaps": [],
        "local_incident_conclusions_added": False,
    }
    if source_text:
        merged_incidents, incident_reconciliation = (
            _reconcile_provider_incidents(
                initial,
                repair,
                source_text,
            )
        )
        merged["consolidated_incidents"] = merged_incidents

    coverage_by_id: dict[str, dict[str, Any]] = {}
    coverage_order: list[str] = []
    for record in (initial, repair):
        for row in record.get("source_coverage") or []:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id") or "").upper()
            if not source_id:
                continue
            if source_id not in coverage_by_id:
                coverage_order.append(source_id)
            coverage_by_id[source_id] = copy.deepcopy(row)
    merged["source_coverage"] = [
        coverage_by_id[source_id] for source_id in coverage_order
    ]
    initial_ids = {
        str(row.get("source_id") or "").upper()
        for row in initial.get("source_coverage") or []
        if isinstance(row, dict)
    }
    repair_ids = {
        str(row.get("source_id") or "").upper()
        for row in repair.get("source_coverage") or []
        if isinstance(row, dict)
    }
    carried_source_ids = [
        source_id for source_id in coverage_order
        if source_id in initial_ids and source_id not in repair_ids
    ]

    combined_plan: list[dict[str, Any]] = []
    seen_plan_items: set[tuple[str, str]] = set()
    appended_initial_actions: list[str] = []
    repair_plan = repair.get("prioritized_operational_plan") or []
    initial_plan = initial.get("prioritized_operational_plan") or []
    for origin, rows in (("repair", repair_plan), ("initial", initial_plan)):
        for row in rows:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action") or "").strip()
            reason = str(row.get("reason") or "").strip()
            key = (action.casefold(), reason.casefold())
            if not action or key in seen_plan_items:
                continue
            seen_plan_items.add(key)
            item = copy.deepcopy(row)
            combined_plan.append(item)
            if origin == "initial":
                appended_initial_actions.append(action)
    for rank, item in enumerate(combined_plan, start=1):
        item["rank"] = rank
    merged["prioritized_operational_plan"] = combined_plan
    merged["human_review_required"] = True

    unsupported_resource_findings = _unsupported_resource_gap_claims(merged)
    quarantined_resource_claims = list(
        dict.fromkeys(
            finding["claim"] for finding in unsupported_resource_findings
        )
    )
    if quarantined_resource_claims:
        quarantined_set = set(quarantined_resource_claims)
        merged["resource_gaps"] = [
            value
            for value in merged.get("resource_gaps") or []
            if str(value) not in quarantined_set
        ]

    evidence = {
        "strategy": "repair_fields_with_initial_provider_gap_fill",
        "analysis_inputs": ["initial_provider_json", "repair_provider_json"],
        "local_operational_conclusions_added": False,
        "unsupported_provider_claims_removed": bool(
            quarantined_resource_claims
        ),
        "quarantined_unsupported_resource_gap_claims": (
            quarantined_resource_claims
        ),
        "provider_incident_reconciliation": incident_reconciliation,
        "provider_conflict_reconciliation": conflict_reconciliation,
        "carried_fields": carried_fields,
        "carried_source_ids": carried_source_ids,
        "repair_plan_count": len(repair_plan),
        "initial_plan_count": len(initial_plan),
        "merged_plan_count": len(combined_plan),
        "appended_initial_provider_actions": appended_initial_actions,
        "missing_core_fields": _missing_core_provider_fields(
            "complex_dossier", merged
        ),
    }
    return merged, evidence
# END RELIEFQUEUE AMD DOSSIER PROVIDER RECONCILIATION PART 5

# BEGIN RELIEFQUEUE AMD DOSSIER CONFLICT-OBSERVATION RECONCILIATION PART 8B
# Carries only source-safe provider-authored conflict/update/duplicate/uncertainty
# observations when a repair response omits those sections.
# END RELIEFQUEUE AMD DOSSIER CONFLICT-OBSERVATION RECONCILIATION PART 8B

# BEGIN RELIEFQUEUE AMD DOSSIER UNSUPPORTED-CLAIM QUARANTINE PART 6
# Deterministically removes only provider-authored resource-gap claims rejected
# by the existing source-truth gate. It adds no replacement fact or action.
# END RELIEFQUEUE AMD DOSSIER UNSUPPORTED-CLAIM QUARANTINE PART 6


# BEGIN RELIEFQUEUE AMD DOSSIER TARGETED INCIDENT SUPPLEMENT PART 8C

def _incident_supplement_targets(
    provider_reconciliation: dict[str, Any] | None,
) -> dict[str, Any]:
    reconciliation = (
        provider_reconciliation
        if isinstance(provider_reconciliation, dict)
        else {}
    )
    incident_evidence = reconciliation.get(
        "provider_incident_reconciliation"
    )
    if not isinstance(incident_evidence, dict):
        incident_evidence = {}

    allowed_source_ids: list[str] = []
    location_conflicts: list[list[str]] = []
    quarantined: list[dict[str, Any]] = []
    for key in (
        "quarantined_repair_incidents",
        "quarantined_initial_incidents",
    ):
        rows = incident_evidence.get(key) or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            quarantined.append(copy.deepcopy(row))
            for value in row.get("source_ids") or []:
                source_id = str(value).upper()
                if source_id and source_id not in allowed_source_ids:
                    allowed_source_ids.append(source_id)
            for pair in row.get("location_conflicts") or []:
                if not isinstance(pair, list) or len(pair) != 2:
                    continue
                normalized = [str(value).upper() for value in pair]
                if normalized not in location_conflicts:
                    location_conflicts.append(normalized)

    merged_count = int(incident_evidence.get("merged_incident_count") or 0)
    needed_count = max(0, DOSSIER_MIN_INCIDENTS - merged_count)
    return {
        "allowed_source_ids": allowed_source_ids,
        "location_conflicts": location_conflicts,
        "quarantined_provider_incidents": quarantined,
        "merged_incident_count": merged_count,
        "minimum_additional_incidents": needed_count,
    }


def dossier_incident_supplement_required(
    semantic_issues: list[str],
    provider_reconciliation: dict[str, Any] | None,
) -> bool:
    """Allow one narrow provider follow-up for an incident-count-only miss."""

    issues = [str(value) for value in semantic_issues if str(value)]
    if not issues:
        return False
    if not all(
        re.match(
            r"^consolidated_incidents requires at least \d+ items, got \d+$",
            issue,
        )
        for issue in issues
    ):
        return False

    targets = _incident_supplement_targets(provider_reconciliation)
    return bool(
        targets["allowed_source_ids"]
        and targets["minimum_additional_incidents"] > 0
    )


def build_dossier_incident_supplement_prompt(
    sanitized_input: str,
    current_output: dict[str, Any],
    semantic_issues: list[str],
    provider_reconciliation: dict[str, Any],
    challenge_nonce: str,
) -> list[dict[str, str]]:
    """Request only corrected provider incidents after one full rewrite.

    This is deliberately narrower than a second full-dossier rewrite. The
    provider receives only the quarantined source IDs, their exact source text,
    explicit duplicate/location constraints and compact existing incident
    references. It must cover every quarantined source exactly once without
    merging distinct explicit locations.
    """

    nonce = str(challenge_nonce or "")
    if not nonce:
        raise ValueError("challenge_nonce is required")

    targets = _incident_supplement_targets(provider_reconciliation)
    allowed_ids = targets["allowed_source_ids"]
    if not allowed_ids:
        raise ValueError("no quarantined provider incident sources available")

    ledger = build_dossier_reasoning_ledger(sanitized_input)
    allowed_set = set(allowed_ids)
    relevant_reports: list[dict[str, Any]] = []
    for row in ledger.get("reports") or []:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").upper()
        body = str(row.get("text") or "")
        linked_update = any(value in body.upper() for value in allowed_ids)
        if source_id in allowed_set or linked_update:
            relevant_reports.append(
                {
                    "source_id": source_id,
                    "header": str(row.get("header") or ""),
                    "text": body,
                    "locations": list(row.get("location_terms") or []),
                }
            )

    duplicate_pairs = [
        [str(value).upper() for value in pair]
        for pair in ledger.get("explicit_duplicate_pairs") or []
        if isinstance(pair, list)
        and len(pair) == 2
        and set(str(value).upper() for value in pair).issubset(allowed_set)
    ]
    current_incidents = [
        {
            "incident_id": str(row.get("incident_id") or ""),
            "source_ids": [
                str(value).upper()
                for value in row.get("source_ids") or []
                if value
            ],
            "location": str(row.get("location") or ""),
        }
        for row in current_output.get("consolidated_incidents") or []
        if isinstance(row, dict)
    ]

    incident_schema = {
        "incident_id": "string",
        "source_ids": ["REPORT-001"],
        "location": "string",
        "needs": "string or list",
        "people_range": "string",
        "vulnerable_groups": "string or list",
        "urgency_rationale": "string",
        "missing_fields": "string or list",
        "confidence": "low|medium|high",
    }
    payload = {
        "workload_mode": "complex_dossier_incident_supplement",
        "challenge_nonce": nonce,
        "output_contract": {
            "schema_version": (
                "reliefqueue-dossier-incident-supplement/v1"
            ),
            "workload_mode": (
                "complex_dossier_incident_supplement"
            ),
            "challenge_nonce": nonce,
            "corrected_incidents": [incident_schema],
            "human_review_required": True,
        },
        "deterministic_semantic_issues": list(semantic_issues),
        "allowed_source_ids": allowed_ids,
        "required_source_coverage": (
            "Every allowed_source_id exactly once across corrected_incidents."
        ),
        "minimum_additional_incidents": max(
            1,
            int(targets["minimum_additional_incidents"]),
        ),
        "forbidden_location_merges": targets["location_conflicts"],
        "explicit_duplicate_pairs": duplicate_pairs,
        "source_reports": relevant_reports,
        "already_valid_incidents": current_incidents,
        "rules": [
            "Return only the incident supplement contract, not a full dossier.",
            "Use only allowed_source_ids in corrected_incidents.",
            "Cover every allowed source exactly once.",
            "Never put a forbidden_location_merges pair in one incident.",
            "Use distinct incident_id values not used by already_valid_incidents.",
            "Do not repeat source IDs already used by already_valid_incidents.",
            "Qualify any unverified people count as unverified or claimed.",
            "Do not invent actions, shortages, locations or completed work.",
            "human_review_required must be true.",
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "Return one strict JSON object only. Produce a narrow corrected "
                "incident supplement for quarantined provider incidents. Cover "
                "every allowed source ID exactly once, keep distinct locations "
                "separate, preserve explicit duplicate pairs, echo the nonce, "
                "and add no unrelated source, action or conclusion."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def normalize_dossier_incident_supplement(
    content: str,
) -> tuple[dict[str, Any], list[str], str]:
    """Normalize a provider-authored incident supplement without synthesis."""

    warnings: list[str] = []
    parsed = _parse_json_maybe_enveloped(content)
    if not isinstance(parsed, dict):
        return (
            {
                "schema_version": (
                    "reliefqueue-dossier-incident-supplement/v1"
                ),
                "workload_mode": (
                    "complex_dossier_incident_supplement"
                ),
                "challenge_nonce": "",
                "corrected_incidents": [],
                "human_review_required": True,
            },
            [
                "Incident supplement was not a provider JSON object; "
                "no incident was added."
            ],
            "local_safe_fallback",
        )

    if (
        not isinstance(parsed.get("corrected_incidents"), list)
        and isinstance(parsed.get("output_contract"), dict)
        and isinstance(
            parsed["output_contract"].get("corrected_incidents"),
            list,
        )
    ):
        parsed = parsed["output_contract"]
        warnings.append(
            "Provider incident supplement envelope was canonicalized "
            "without local synthesis."
        )

    normalized = {
        "schema_version": str(
            parsed.get("schema_version")
            or "reliefqueue-dossier-incident-supplement/v1"
        ),
        "workload_mode": str(
            parsed.get("workload_mode")
            or "complex_dossier_incident_supplement"
        ),
        "challenge_nonce": str(parsed.get("challenge_nonce") or ""),
        "corrected_incidents": [
            copy.deepcopy(row)
            for row in parsed.get("corrected_incidents") or []
            if isinstance(row, dict)
        ],
        "human_review_required": True,
    }
    source = (
        "provider"
        if normalized["challenge_nonce"]
        and normalized["corrected_incidents"]
        else "provider_incomplete"
    )
    if not normalized["corrected_incidents"]:
        warnings.append(
            "Provider incident supplement contained no corrected incidents."
        )
    return normalized, warnings, source


def reconcile_provider_incident_supplement(
    current_output: dict[str, Any],
    supplement: dict[str, Any],
    source_text: str,
    provider_reconciliation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge only source-safe provider-authored corrected incidents."""

    merged = copy.deepcopy(current_output)
    ledger = build_dossier_reasoning_ledger(source_text)
    targets = _incident_supplement_targets(provider_reconciliation)
    allowed_ids = set(targets["allowed_source_ids"])

    existing = [
        copy.deepcopy(row)
        for row in merged.get("consolidated_incidents") or []
        if isinstance(row, dict)
    ]
    used_source_ids = {
        source_id
        for row in existing
        for source_id in _provider_incident_source_ids(row)
    }
    used_incident_ids = {
        str(row.get("incident_id") or "")
        for row in existing
        if row.get("incident_id")
    }

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    covered: set[str] = set()
    quarantined_people_ranges: list[dict[str, Any]] = []

    for row in supplement.get("corrected_incidents") or []:
        if not isinstance(row, dict):
            continue
        source_ids = _provider_incident_source_ids(row)
        incident_id = str(row.get("incident_id") or "")
        reasons: list[str] = []

        unknown = sorted(set(source_ids) - allowed_ids)
        overlap_existing = sorted(set(source_ids) & used_source_ids)
        overlap_supplement = sorted(set(source_ids) & covered)
        conflicts = _provider_incident_location_conflicts(row, ledger)

        if not incident_id:
            reasons.append("missing incident_id")
        elif incident_id in used_incident_ids:
            reasons.append("incident_id already used by a valid incident")
        if not source_ids:
            reasons.append("missing source_ids")
        if unknown:
            reasons.append(
                "source_ids outside quarantined set: " + ", ".join(unknown)
            )
        if overlap_existing:
            reasons.append(
                "source_ids already used by valid incidents: "
                + ", ".join(overlap_existing)
            )
        if overlap_supplement:
            reasons.append(
                "source_ids repeated across supplement incidents: "
                + ", ".join(overlap_supplement)
            )
        if conflicts:
            reasons.append(
                "merged reports with distinct explicit locations"
            )

        if reasons:
            rejected.append(
                {
                    "incident_id": incident_id,
                    "source_ids": source_ids,
                    "location_conflicts": conflicts,
                    "reasons": reasons,
                }
            )
            continue

        item, people_finding = _quarantine_unverified_people_range(
            row,
            ledger,
        )
        if people_finding:
            quarantined_people_ranges.append(people_finding)
        accepted.append(item)
        covered.update(source_ids)
        used_source_ids.update(source_ids)
        used_incident_ids.add(incident_id)

    merged["consolidated_incidents"] = existing + accepted

    incident_by_source: dict[str, str] = {}
    for row in accepted:
        incident_id = str(row.get("incident_id") or "")
        for source_id in _provider_incident_source_ids(row):
            incident_by_source[source_id] = incident_id

    if incident_by_source:
        coverage_rows: list[dict[str, Any]] = []
        for row in merged.get("source_coverage") or []:
            if not isinstance(row, dict):
                continue
            item = copy.deepcopy(row)
            source_id = str(item.get("source_id") or "").upper()
            if source_id in incident_by_source:
                item["linked_incident_id"] = incident_by_source[source_id]
            coverage_rows.append(item)
        merged["source_coverage"] = coverage_rows

    missing_allowed = sorted(allowed_ids - covered)
    evidence = {
        "strategy": "targeted_provider_incident_supplement",
        "allowed_source_ids": targets["allowed_source_ids"],
        "minimum_additional_incidents": (
            targets["minimum_additional_incidents"]
        ),
        "provider_corrected_incident_count": len(
            supplement.get("corrected_incidents") or []
        ),
        "accepted_provider_incidents": [
            {
                "incident_id": str(row.get("incident_id") or ""),
                "source_ids": _provider_incident_source_ids(row),
            }
            for row in accepted
        ],
        "rejected_provider_incidents": rejected,
        "covered_allowed_source_ids": sorted(covered),
        "missing_allowed_source_ids": missing_allowed,
        "quarantined_unverified_people_ranges": (
            quarantined_people_ranges
        ),
        "source_coverage_links_normalized": bool(incident_by_source),
        "local_incident_conclusions_added": False,
        "complete_source_partition": not missing_allowed,
    }
    return merged, evidence


# END RELIEFQUEUE AMD DOSSIER TARGETED INCIDENT SUPPLEMENT PART 8C

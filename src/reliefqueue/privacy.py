"""Public/private output boundaries."""

from __future__ import annotations

import re
from typing import Any


PUBLIC_CASE_FIELDS = [
    "case_id",
    "public_case_ref",
    "safe_summary",
    "urgency",
    "need_type",
    "people_count_bucket",
    "vulnerable_category_flags",
    "operation_zone_id",
    "zone_name_optional",
    "geo_confidence",
    "missing_fields_safe",
    "duplicate_cluster_id",
    "duplicate_cluster_size",
    "human_review_required",
    "public_status",
    "created_from_synthetic_fixture",
]

PUBLIC_VULNERABLE_FLAGS = {
    "child_present",
    "elderly_present",
    "medical_risk",
    "mobility_support_needed",
}

PRIVATE_FIELD_NAMES = {
    "raw_text_private",
    "reporter_name_private",
    "reporter_name_private_optional",
    "reporter_phone_private",
    "reporter_phone_private_optional",
    "media_note_private_optional",
    "private_address",
    "private address",
    "raw_transcript",
    "raw transcript",
    "raw_ocr_text",
    "ocr text",
    "worker_private_contact",
    "worker private contact",
    "internal_operator_note",
    "internal operator note",
    "api_key",
    "secret",
    "token",
}


def _people_count_bucket(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        count = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if count <= 1:
        return "1"
    if count <= 5:
        return "2-5"
    if count <= 10:
        return "6-10"
    if count <= 25:
        return "11-25"
    return "25+"


def _public_status(case: dict[str, Any]) -> str:
    if case.get("missing_fields"):
        return "info_missing"
    if case.get("assignment_ready"):
        return "queued"
    return "needs_review"


def redact_public_case(case: dict[str, Any]) -> dict[str, Any]:
    public = {
        "case_id": case.get("case_id"),
        "public_case_ref": f"public-{str(case.get('case_id') or 'unknown').replace('case-', '')}",
        "safe_summary": _strip_forbidden(str(case.get("safe_summary") or "")),
        "urgency": case.get("urgency"),
        "need_type": case.get("need_type"),
        "people_count_bucket": _people_count_bucket(case.get("people_count")),
        "vulnerable_category_flags": _public_vulnerable_flags(case),
        "operation_zone_id": case.get("operation_zone_id"),
        "zone_name_optional": case.get("zone_name_optional") or "",
        "geo_confidence": case.get("geo_confidence"),
        "missing_fields_safe": [field for field in case.get("missing_fields", []) if field != "contact_possible"],
        "duplicate_cluster_id": case.get("duplicate_cluster_id"),
        "duplicate_cluster_size": int(case.get("duplicate_cluster_size") or 1),
        "human_review_required": bool(case.get("human_review_required")),
        "public_status": _public_status(case),
        "created_from_synthetic_fixture": bool(case.get("created_from_synthetic_fixture")),
    }
    return {field: public.get(field) for field in PUBLIC_CASE_FIELDS}


def _public_vulnerable_flags(case: dict[str, Any]) -> list[str]:
    source = set(case.get("vulnerable_flags") or [])
    public: list[str] = []
    if "child" in source:
        public.append("child_present")
    if "elderly" in source:
        public.append("elderly_present")
    if case.get("need_type") == "medical" or {"pregnant", "injured"} & source:
        public.append("medical_risk")
    if {"disabled", "mobility"} & source:
        public.append("mobility_support_needed")
    return [flag for flag in public if flag in PUBLIC_VULNERABLE_FLAGS]


def _strip_forbidden(text: str) -> str:
    text = re.sub(r"\+?\d[\d\s-]{8,}\d", "[redacted-contact]", text)
    public_terms = {
        "medical_condition": "medical_risk",
        "pregnant": "medical_risk",
        "injured": "medical_risk",
        "disabled": "mobility_support_needed",
        "elderly": "elderly_present",
        "child": "child_present",
    }
    for private_term, public_term in public_terms.items():
        text = re.sub(rf"\b{re.escape(private_term)}\b", public_term, text, flags=re.IGNORECASE)
    for forbidden in [
        "Synthetic Asha",
        "Synthetic Ravi",
        "Synthetic Nurse",
        "Synthetic Mohan",
        "Synthetic Meena",
        "Synthetic Unknown",
    ]:
        text = text.replace(forbidden, "[redacted-name]")
    return text


def public_export_has_forbidden_content(rows: list[dict[str, Any]], forbidden_fields: list[str], forbidden_patterns: list[str]) -> list[str]:
    errors: list[str] = []
    allowed = set(PUBLIC_CASE_FIELDS)
    for row in rows:
        extra = set(row) - allowed
        if extra:
            errors.append(f"public row {row.get('case_id')} has non-allowlisted fields: {sorted(extra)}")
        missing = allowed - set(row)
        if missing:
            errors.append(f"public row {row.get('case_id')} is missing public fields: {sorted(missing)}")
        for field in forbidden_fields:
            if field in row:
                errors.append(f"public row {row.get('case_id')} contains forbidden field {field}")
        text = repr(row)
        for pattern in forbidden_patterns:
            if re.search(pattern, text):
                errors.append(f"public row {row.get('case_id')} matches forbidden pattern {pattern}")
    return errors

"""Deterministic language, need, urgency, and summary rules."""

from __future__ import annotations

import re
from typing import Any

from .models import normalize_text, unique_sorted


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "twenty": 20,
    "thirty": 30,
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "paanch": 5,
}


def detect_language(text: str) -> str:
    lowered = normalize_text(text)
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    hinglish_words = {"hai", "hain", "paani", "pani", "bhejo", "bachcha", "baccha", "mandir", "chahiye", "dadi", "hum", "log", "paas"}
    english_words = {"need", "rescue", "water", "people", "near", "urgent", "doctor"}
    tokens = set(lowered.split())
    if tokens & hinglish_words:
        return "hinglish"
    if tokens & english_words or re.search(r"[a-z]", lowered):
        return "en"
    return "unknown"


def detect_need_type(text: str) -> str:
    n = normalize_text(text)
    if any(word in n for word in ["information", "shelter open", "only need information"]):
        return "information_request"
    if any(word in n for word in ["food", "drinking water", "water packets", "clean drinking water", "dry food"]):
        return "food_water"
    medical_negated = "no immediate medical issue" in n or "have medicines but need" in n
    if not medical_negated and any(word in n for word in ["pregnant", "bleeding", "ambulance", "doctor", "medicine", "medical", "fever", "vomiting", "insulin", "injured", "bukhar", "bimar"]):
        return "medical"
    if any(word in n for word in ["rescue", "stuck", "trapped", "stranded", "phase", "boat", "बचाव", "फंसे"]):
        return "rescue"
    if any(word in n for word in ["evacuation", "evacuate", "move them", "truck support", "transport"]):
        return "evacuation"
    if any(word in n for word in ["food", "water", "drinking", "packets", "dry food"]):
        return "food_water"
    if any(word in n for word in ["shelter", "tarpaulin", "displaced", "camp"]):
        return "shelter"
    if any(word in n for word in ["cannot explain location", "location clearly"]):
        return "missing_location_info"
    return "unknown"


def extract_people_count(text: str) -> int | None:
    n = normalize_text(text)
    candidates: list[int] = []
    count_patterns = [
        r"\b(?:around|about|total)\s+(\d+)\b",
        r"\b(\d+)\s+(?:people|persons|person|log|adults|residents|households|displaced)\b",
    ]
    for pattern in count_patterns:
        candidates.extend(int(value) for value in re.findall(pattern, n))
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\s+(?:people|persons|person|log|adults|residents|children|child|bachche|dadi)\b", n):
            candidates.append(value)
    if not candidates:
        return None
    if "food packet" in n and len(candidates) == 1 and candidates[0] > 100:
        return None
    return max(candidates)


def detect_vulnerable_flags(text: str) -> list[str]:
    n = normalize_text(text)
    flags: list[str] = []
    if any(word in n for word in ["child", "children", "bachcha", "baccha", "bachche"]):
        flags.append("child")
    if any(word in n for word in ["elderly", "grandmother", "dadi", "बुजुर्ग"]):
        flags.append("elderly")
    if "pregnant" in n or "labor" in n:
        flags.append("pregnant")
    if "disabled" in n:
        flags.append("disabled")
    medical_negated = "no immediate medical issue" in n or "have medicines but need" in n
    if not medical_negated and any(word in n for word in ["fever", "vomiting", "bleeding", "insulin", "injured", "medicine", "medical", "bukhar", "bimar"]):
        flags.append("medical_condition")
    return unique_sorted(flags)


def urgency_for(text: str, need_type: str, missing_fields: list[str], vulnerable_flags: list[str]) -> tuple[str, list[str]]:
    n = normalize_text(text)
    reasons: list[str] = []
    if "location" in missing_fields or need_type == "unknown":
        reasons.append("needs human review for missing or unclear critical information")
        return "REVIEW", reasons
    if any(word in n for word in ["rumor", "not sure", "verify", "someone said", "may be stranded"]):
        reasons.append("unverified third-party report")
        return "REVIEW", reasons
    high_risk = any(word in n for word in ["rising", "severe", "urgent", "urgently", "now", "waist deep", "kamar", "too deep", "water entering", "boat rescue", "trapped", "stuck", "injured", "bleeding", "labor", "insulin", "battery is almost dead"])
    if need_type in {"rescue", "medical"} and (high_risk or vulnerable_flags):
        reasons.append(f"{need_type} need with high-risk wording or vulnerable people")
        return "RED", reasons
    if need_type in {"rescue", "medical"}:
        reasons.append(f"{need_type} need")
        return "AMBER", reasons
    if need_type in {"food_water", "shelter", "evacuation"}:
        reasons.append(f"{need_type} support requested")
        return "AMBER", reasons
    reasons.append("no immediate danger stated")
    return "GREEN", reasons


def required_skills(need_type: str, text: str, vulnerable_flags: list[str]) -> list[str]:
    n = normalize_text(text)
    skills: list[str] = []
    if need_type == "medical":
        skills.append("medical_first_response")
    if need_type == "rescue":
        skills.append("general_relief")
    if need_type == "food_water":
        skills.append("food_water_distribution")
    if need_type == "shelter":
        skills.append("shelter_support")
    if need_type == "evacuation" or "truck" in n or "transport" in n:
        skills.append("evacuation_support")
    flood_context = any(
        word in n
        for word in [
            "boat",
            "flood",
            "water is rising",
            "water rising",
            "water entering",
            "waist deep",
            "too deep",
            "paani",
            "pani",
            "जल",
            "पानी",
        ]
    )
    if flood_context:
        skills.append("flood_rescue")
    if "child" in vulnerable_flags:
        skills.append("child_support")
    if vulnerable_flags:
        skills.append("vulnerable_person_support")
    return unique_sorted(skills or ["general_relief"])


def safe_summary(case: dict[str, Any]) -> str:
    people = f"{case['people_count']} people" if case.get("people_count") else "people count unclear"
    flags = ", ".join(case.get("vulnerable_flags") or ["no vulnerable flag detected"])
    zone = case.get("operation_zone_id") or "unknown zone"
    clue = case.get("location_clue") or "location unclear"
    return f"{case['need_type']} request for {people}; flags: {flags}; area: {zone}; clue: {clue}."

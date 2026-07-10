"""Deterministic synthetic report expansion for batch demos."""

from __future__ import annotations

import copy
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .intake import load_jsonl, validate_reports
from .reports import write_jsonl


LOCATION_VARIANTS = {
    "School No. 3": ["School No. 3", "School 3", "near school number 3"],
    "School 3": ["School No. 3", "School 3", "near school number 3"],
    "Primary Health Centre Ward 3": ["Primary Health Centre Ward 3", "PHC gate Village 3", "Primary Health Centre Village 3"],
    "Primary Health Centre Village 3": ["Primary Health Centre Village 3", "PHC gate Village 3", "Primary Health Centre Ward 3"],
    "Community Hall Ward 2": ["Community Hall Ward 2", "near community hall ward two", "Ward 2 community hall"],
    "Relief Camp A": ["Relief Camp A", "relief camp ward 2", "Camp A Ward 2"],
    "Old Bus Stand": ["Old Bus Stand", "old bus stand road", "bus stand Ward 4"],
    "Main Bridge": ["Main Bridge", "near main bridge", "bridge side Ward 1"],
    "River Bank": ["River Bank", "river bank side", "near river bank"],
    "Hanuman Temple Village 3": ["Hanuman Temple Village 3", "Hanuman mandir Village 3", "temple side Village 3"],
    "Hanuman mandir": ["Hanuman Temple Village 3", "Hanuman mandir Village 3", "temple side Village 3"],
    "Clinic Road": ["Clinic Road", "near clinic road Ward 4", "clinic road lane"],
    "Clinic Road Ward 4": ["Clinic Road Ward 4", "near clinic road Ward 4", "clinic road lane"],
    "Warehouse Lane Ward 4": ["Warehouse Lane Ward 4", "warehouse lane", "Ward 4 warehouse lane"],
    "Warehouse Lane": ["Warehouse Lane", "warehouse lane Ward 4", "Ward 4 warehouse"],
    "Old Banyan Village 3": ["Old Banyan Village 3", "Banyan area Village 3", "old banyan side"],
    "Ward 1": ["Ward 1", "School No. 3 side Ward 1", "main bridge Ward 1"],
    "market": ["market back lane", "behind market", ""],
}

NEED_SNIPPETS = {
    "rescue": ["Need boat rescue.", "People are waiting above flood water.", "Water is too deep to walk."],
    "medical": ["Need doctor urgently.", "Medicine support is needed.", "Ambulance or medical help requested."],
    "food_water": ["Need clean drinking water and dry food.", "Food packets and water are needed.", "Need drinking water supply."],
    "shelter": ["Need shelter support tonight.", "Temporary shelter and tarpaulin needed.", "Displaced people need safe shelter."],
    "evacuation": ["Need evacuation support.", "Need transport support.", "Please help move people safely."],
    "information_request": ["Only asking for information.", "Please confirm safe shelter information.", "No immediate danger stated."],
    "unknown": ["Please review details.", "Situation unclear.", "Need coordinator follow-up."],
}

LANGUAGE_PREFIXES = {
    "en": ["", "Update: ", "Local report says "],
    "hinglish": ["", "Local update: ", "Hinglish note: "],
    "hi": ["", "स्थानीय सूचना: ", "हिंदी नोट: "],
}

VULNERABLE_SNIPPETS = {
    "child": " Includes one child.",
    "elderly": " Includes elderly people.",
    "pregnant": " Includes a pregnant person.",
    "disabled": " Includes a disabled person.",
    "medical_condition": " Medical condition mentioned.",
}


def expand_seed_reports(
    seed_reports: list[dict[str, Any]],
    *,
    count: int,
    seed: int,
    duplicate_probability: float = 0.14,
    missing_info_probability: float = 0.16,
) -> list[dict[str, Any]]:
    """Return a deterministic synthetic-only expansion of seed reports."""

    if count < 0:
        raise ValueError("count must be non-negative")
    rng = random.Random(seed)
    base_time = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    rows: list[dict[str, Any]] = []
    for index in range(count):
        source = copy.deepcopy(seed_reports[index % len(seed_reports)])
        duplicate_of = rows[rng.randrange(len(rows))] if rows and rng.random() < duplicate_probability else None
        row = copy.deepcopy(duplicate_of or source)
        row["report_id"] = f"batch-{count:03d}-{seed:04d}-{index + 1:06d}"
        row["received_at"] = (base_time + timedelta(minutes=index * 2 + rng.randrange(0, 4))).isoformat().replace("+00:00", "Z")
        row["source_channel"] = rng.choice(["sms", "whatsapp", "web", "social", "voice_transcript_mock", "image_ocr_mock"])
        row["language_hint_optional"] = _language_variant(row, rng)
        row["location_hint_optional"] = _location_variant(row, rng)
        row["text"] = _synthetic_text(row, index + 1, rng)
        if rng.random() < missing_info_probability:
            _apply_missing_info(row, rng)
        row["reporter_name_private_optional"] = f"Synthetic Batch Reporter {index + 1:06d}"
        if rng.random() < 0.12:
            row.pop("reporter_phone_private_optional", None)
        else:
            row["reporter_phone_private_optional"] = f"synthetic-contact-{index + 1:06d}"
        if row["source_channel"] == "image_ocr_mock":
            row["media_note_private_optional"] = "Synthetic mock OCR note only; no real image included."
        elif row["source_channel"] == "voice_transcript_mock":
            row["media_note_private_optional"] = "Synthetic mock voice transcript only; no real audio included."
        else:
            row.pop("media_note_private_optional", None)
        row["expected_debug_tags_optional"] = ["synthetic_batch", f"seed_{seed}", f"row_{index + 1:06d}"]
        rows.append(row)
    validate_reports(rows)
    return rows


def expand_seed_fixture_file(seed_path: Path, *, count: int, seed: int, out_path: Path) -> list[dict[str, Any]]:
    rows = expand_seed_reports(load_jsonl(seed_path), count=count, seed=seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, rows)
    return rows


def _language_variant(row: dict[str, Any], rng: random.Random) -> str:
    current = str(row.get("language_hint_optional") or "en")
    if rng.random() < 0.18:
        return rng.choice(["en", "hinglish", "hi"])
    return current if current in {"en", "hinglish", "hi"} else "en"


def _location_variant(row: dict[str, Any], rng: random.Random) -> str:
    original = str(row.get("location_hint_optional") or "")
    choices = LOCATION_VARIANTS.get(original)
    if not choices:
        return original
    return rng.choice(choices)


def _need_snippet(text: str, rng: random.Random) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["doctor", "medicine", "ambulance", "pregnant", "fever", "insulin"]):
        key = "medical"
    elif any(word in lowered for word in ["food", "water packets", "drinking water", "dry food"]):
        key = "food_water"
    elif any(word in lowered for word in ["shelter", "tarpaulin", "camp"]):
        key = "shelter"
    elif any(word in lowered for word in ["evacuation", "truck", "transport", "move them"]):
        key = "evacuation"
    elif "information" in lowered or "open" in lowered:
        key = "information_request"
    elif any(word in lowered for word in ["rescue", "boat", "stuck", "trapped", "stranded"]):
        key = "rescue"
    else:
        key = "unknown"
    return rng.choice(NEED_SNIPPETS[key])


def _synthetic_text(row: dict[str, Any], sequence: int, rng: random.Random) -> str:
    original = str(row.get("text") or "")
    language = str(row.get("language_hint_optional") or "en")
    prefix = rng.choice(LANGUAGE_PREFIXES.get(language, LANGUAGE_PREFIXES["en"]))
    location = str(row.get("location_hint_optional") or "location unclear")
    people_count = rng.choice([1, 2, 3, 4, 5, 6, 8, 12, 15, 20, 30])
    snippet = _need_snippet(original, rng)
    vulnerable = ""
    for marker, addition in VULNERABLE_SNIPPETS.items():
        if marker.replace("_", " ") in original.lower() or marker.split("_")[0] in original.lower():
            vulnerable += addition
    if not vulnerable and rng.random() < 0.22:
        vulnerable = rng.choice(list(VULNERABLE_SNIPPETS.values()))
    channel_note = ""
    if row.get("source_channel") == "voice_transcript_mock":
        channel_note = " Voice transcript:"
    elif row.get("source_channel") == "image_ocr_mock":
        channel_note = " OCR:"
    return f"{prefix}{channel_note} Synthetic batch report {sequence} near {location}. {snippet} Around {people_count} people.{vulnerable}".strip()


def _apply_missing_info(row: dict[str, Any], rng: random.Random) -> None:
    choice = rng.choice(["location", "people", "contact"])
    if choice == "location":
        row["location_hint_optional"] = ""
        row["text"] = "Synthetic batch report with unclear location. Need coordinator follow-up for location and situation details."
    elif choice == "people":
        row["text"] = str(row.get("text") or "").replace("Around ", "About some ")
        row["text"] = row["text"].replace(" people.", " people count unclear.")
    elif choice == "contact":
        row.pop("reporter_phone_private_optional", None)

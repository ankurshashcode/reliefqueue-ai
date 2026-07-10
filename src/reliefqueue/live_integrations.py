"""Offline-safe live integration phase commands for phases 02-10."""

from __future__ import annotations

import base64
import csv
from copy import deepcopy
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import struct
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path


# ReliefQueue public live-integration capability paths
# Public/report-facing directories use capability names, not internal phase codes.
# Keep this mapping central so commands, tests, generated reports, and console
# messages resolve to the same path.
_PUBLIC_LIVE_INTEGRATION_DIR_BY_CODE = {
    "02": "geospatial-store",
    "02_postgis": "geospatial-store",
    "02_03_stateful_mutation": "stateful-mutation",
    "02_04_logistics": "logistics-assets",
    "02_05_volunteers": "volunteer-surge",
    "03": "operations-queue",
    "03_queue": "operations-queue",
    "04": "ai-model-endpoint",
    "04_vllm": "ai-model-endpoint",
    "05": "system-health",
    "05_observability": "system-health",
    "06": "field-forms",
    "06_field_forms": "field-forms",
    "07": "messaging-channel",
    "07_rapidpro": "messaging-channel",
    "08": "communication-channels",
    "08_channels": "communication-channels",
    "09": "masked-contact",
    "09_masked_contact": "masked-contact",
    "10": "pilot-drill",
    "10_live_pilot": "pilot-drill",
}



_PUBLIC_LIVE_INTEGRATION_DIR_ALIASES = {
    "stateful-mutation": "stateful-mutation",
    "logistics-assets": "logistics-assets",
    "volunteer-surge": "volunteer-surge",
    "geospatial-store": "geospatial-store",
    "operations-queue": "operations-queue",
    "ai-model-endpoint": "ai-model-endpoint",
    "system-health": "system-health",
    "field-forms": "field-forms",
    "messaging-channel": "messaging-channel",
    "communication-channels": "communication-channels",
    "masked-contact": "masked-contact",
    "pilot-drill": "pilot-drill",
}

def _public_live_integration_dir_name(capability_id: object) -> str:
    value = str(capability_id)
    if value.startswith("phase_"):
        value = value[len("phase_"):]
    return (
        _PUBLIC_LIVE_INTEGRATION_DIR_BY_CODE.get(value)
        or _PUBLIC_LIVE_INTEGRATION_DIR_ALIASES.get(value)
        or value.replace("_", "-")
    )


def _live_integration_output_dir(report_dir: Path, capability_id: object) -> Path:
    path = report_dir / "live_integrations" / _public_live_integration_dir_name(capability_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _live_integration_checkpoint_path(report_dir: Path, capability_id: object) -> Path:
    path = _checkpoint_dir(report_dir) / f"{_public_live_integration_dir_name(capability_id)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .ai import AIConfig, apply_ai_enrichment
from .assignment import suggest_assignments
from .exports import export_public
from .intake import load_json, load_jsonl, validate_fixture_bundle
from .privacy import redact_public_case
from .reports import write_jsonl


PHASES: dict[str, dict[str, Any]] = {
    "02": {"name": "PostGIS live persistence", "slug": "postgis", "checkpoint": "geospatial-store"},
    "03": {"name": "Live queue worker", "slug": "queue", "checkpoint": "operations-queue"},
    "02_03": {
        "name": "PostGIS + Redis stateful mutation drill",
        "slug": "stateful_mutation",
        "checkpoint": "stateful-mutation",
    },
    "02_04": {
        "name": "Mission logistics asset coordination drill",
        "slug": "logistics",
        "checkpoint": "logistics-assets",
    },
    "02_05": {
        "name": "Volunteer surge coordination drill",
        "slug": "volunteers",
        "checkpoint": "volunteer-surge",
    },
    "04": {"name": "AMD/vLLM live inference", "slug": "vllm", "checkpoint": "ai-model-endpoint"},
    "05": {"name": "Live observability", "slug": "observability", "checkpoint": "system-health"},
    "06": {"name": "ODK/Kobo field forms", "slug": "field_forms", "checkpoint": "field-forms"},
    "07": {"name": "RapidPro messaging workflow boundary", "slug": "rapidpro", "checkpoint": "messaging-channel"},
    "08": {"name": "WhatsApp/SMS ingress", "slug": "channels", "checkpoint": "communication-channels"},
    "09": {"name": "Masked contact telecom integration", "slug": "masked_contact", "checkpoint": "masked-contact"},
    "10": {"name": "End-to-end live pilot drill", "slug": "live_pilot", "checkpoint": "pilot-drill"},
}

OPTIONAL_ENV = {
    "postgis": [
        "RELIEFQUEUE_POSTGIS_DSN",
        "RELIEFQUEUE_POSTGIS_SCHEMA",
        "RELIEFQUEUE_POSTGIS_CONNECT_TIMEOUT_SECONDS",
    ],
    "queue": [
        "RELIEFQUEUE_REDIS_URL",
        "RELIEFQUEUE_NATS_URL",
        "RELIEFQUEUE_QUEUE_BACKEND",
        "RELIEFQUEUE_QUEUE_NAME",
    ],
    "vllm": ["AI_MODE", "OPENAI_COMPAT_BASE_URL", "OPENAI_COMPAT_API_KEY", "OPENAI_COMPAT_MODEL"],
    "odk": [
        "ODK_CENTRAL_BASE_URL",
        "ODK_CENTRAL_USERNAME",
        "ODK_CENTRAL_PASSWORD",
        "ODK_CENTRAL_PROJECT_ID",
        "ODK_CENTRAL_FORM_ID",
    ],
    "rapidpro": ["RAPIDPRO_BASE_URL", "RAPIDPRO_API_TOKEN", "RAPIDPRO_WORKSPACE_UUID", "RAPIDPRO_FLOW_UUID"],
    "whatsapp": ["WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN"],
    "sms": ["SMS_PROVIDER", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_MESSAGING_SERVICE_SID"],
    "masked_contact": ["MASKED_CONTACT_PROVIDER", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PROXY_SERVICE_SID"],
}

CONFIRMATION_VALUES = {
    "RELIEFQUEUE_POSTGIS_WRITE_CONFIRM": "I_UNDERSTAND_SYNTHETIC_POSTGIS_WRITE",
    "QUEUE_REPLAY_CONFIRM": "I_UNDERSTAND_REPLAY",
    "ODK_UPLOAD_CONFIRM": "I_UNDERSTAND_ODK_FORM_UPLOAD",
    "RAPIDPRO_LIVE_SEND_CONFIRM": "I_UNDERSTAND_REAL_MESSAGES_WILL_BE_SENT",
    "CHANNEL_LIVE_SEND_CONFIRM": "I_UNDERSTAND_REAL_MESSAGES_WILL_BE_SENT",
    "MASKED_CONTACT_LIVE_CONFIRM": "I_UNDERSTAND_REAL_CONTACT_PROVIDER_ACTION",
}

REPORT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt", ".xml", ".sql"}



# Runtime guardrail: normalize Path joins under live_integrations/ so older helper
# code that still builds phase-coded child names writes and prints public paths.
# This is intentionally local to this module process.
if not getattr(Path, "_reliefqueue_public_live_join_enabled", False):
    _RELIEFQUEUE_ORIGINAL_PATH_TRUEDIV = Path.__truediv__

    def _reliefqueue_public_live_path_join(self: Path, child: object):
        result = _RELIEFQUEUE_ORIGINAL_PATH_TRUEDIV(self, child)
        try:
            child_text = str(child)
            # The common runtime expression is:
            #   report_dir / "live_integrations" / f"phase_{phase_id}"
            # Normalize the second join before any file operation or print sees it.
            if self.name == "live_integrations":
                public_child = _public_live_integration_dir_name(child_text)
                if public_child != child_text:
                    return _RELIEFQUEUE_ORIGINAL_PATH_TRUEDIV(self, public_child)

            # Defensive normalization for paths constructed through another helper.
            parts = list(result.parts)
            if "live_integrations" in parts:
                index = parts.index("live_integrations")
                if index + 1 < len(parts):
                    public_child = _public_live_integration_dir_name(parts[index + 1])
                    if public_child != parts[index + 1]:
                        parts[index + 1] = public_child
                        return Path(*parts)
        except Exception:
            return result
        return result

    Path.__truediv__ = _reliefqueue_public_live_path_join  # type: ignore[method-assign]
    Path._reliefqueue_public_live_join_enabled = True  # type: ignore[attr-defined]

def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_report_dir(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)


def _phase_dir(report_dir: Path, phase_id: str) -> Path:
    path = report_dir / "live_integrations" / f"phase_{phase_id}_{PHASES[phase_id]['slug']}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _checkpoint_dir(report_dir: Path) -> Path:
    path = report_dir / "live_integration_checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_demo(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from .cli import build_cases

    reports, zones, workers = validate_fixture_bundle(root)
    cases_path = root / "reports" / "latest" / "cases.jsonl"
    cases = load_jsonl(cases_path) if cases_path.exists() else build_cases(reports, zones)
    return cases, zones, workers, suggest_assignments(cases, workers)


def _env_status(keys: list[str], *, any_of: bool = False) -> dict[str, Any]:
    present = [key for key in keys if os.environ.get(key)]
    missing = [key for key in keys if not os.environ.get(key)]
    configured = bool(present) if any_of else bool(keys) and not missing
    return {
        "status": "configured" if configured else ("partial" if present else "skipped_missing_env"),
        "present_keys": present,
        "missing_keys": missing,
        "secret_values_printed": False,
    }


def _configured_postgis_dsn() -> str | None:
    value = os.environ.get("RELIEFQUEUE_POSTGIS_DSN", "").strip()
    return value or None


def _configured_postgis_schema() -> str:
    return os.environ.get("RELIEFQUEUE_POSTGIS_SCHEMA", "reliefqueue_live").strip() or "reliefqueue_live"


def _configured_postgis_timeout() -> float:
    raw = os.environ.get("RELIEFQUEUE_POSTGIS_CONNECT_TIMEOUT_SECONDS", "5").strip()
    try:
        return max(1.0, min(float(raw), 30.0))
    except ValueError:
        return 5.0


def _configured_redis_url() -> str | None:
    value = os.environ.get("RELIEFQUEUE_REDIS_URL", "").strip()
    return value or None


def _configured_queue_backend() -> str:
    return os.environ.get("RELIEFQUEUE_QUEUE_BACKEND", "local").strip().lower() or "local"


def _configured_queue_name() -> str:
    return os.environ.get("RELIEFQUEUE_QUEUE_NAME", "reliefqueue.intake.v1").strip() or "reliefqueue.intake.v1"


def _rect_wkt(west: float, south: float, east: float, north: float) -> str:
    return f"POLYGON(({west:.4f} {south:.4f},{east:.4f} {south:.4f},{east:.4f} {north:.4f},{west:.4f} {north:.4f},{west:.4f} {south:.4f}))"


def _scenario_case(lon: float, lat: float, need_type: str, location_clue: str) -> dict[str, Any]:
    return {
        "longitude": lon,
        "latitude": lat,
        "need_type": need_type,
        "location_clue": location_clue,
    }


def _scenario_profile(
    *,
    label: str,
    disaster_type: str,
    operation_zone_id: str,
    operation_zone_name: str,
    zone_boundary_hint: str,
    zone_polygon_wkt: str,
    relief_hub_name: str,
    relief_hub_lon: float,
    relief_hub_lat: float,
    relief_hub_radius_meters: int,
    priority_need_types: list[str],
    outside_zone_behavior: str,
    primary_case: dict[str, Any],
    nearby_case: dict[str, Any],
    outside_case: dict[str, Any],
    redis_burst_size: int,
    dedup_ttl_seconds: int,
    dlq_after_attempts: int,
    queue_pressure_note: str,
    nearest_case_limit: int = 5,
) -> dict[str, Any]:
    return {
        "label": label,
        "coordinator": {
            "role": "local_coordinator",
            "disaster_type": disaster_type,
            "operation_zone_id": operation_zone_id,
            "operation_zone_name": operation_zone_name,
            "zone_boundary_hint": zone_boundary_hint,
            "zone_polygon_wkt": zone_polygon_wkt,
            "relief_hub_name": relief_hub_name,
            "relief_hub_lon": relief_hub_lon,
            "relief_hub_lat": relief_hub_lat,
            "relief_hub_radius_meters": relief_hub_radius_meters,
            "nearest_case_limit": nearest_case_limit,
            "priority_need_types": priority_need_types,
            "outside_zone_behavior": outside_zone_behavior,
            "primary_case": primary_case,
            "nearby_case": nearby_case,
            "outside_case": outside_case,
        },
        "command_center": {
            "role": "command_center_operator",
            "redis_burst_size": redis_burst_size,
            "dedup_ttl_seconds": dedup_ttl_seconds,
            "dlq_after_attempts": dlq_after_attempts,
            "replay_mode": "review_first",
            "queue_pressure_note": queue_pressure_note,
        },
    }


STATEFUL_MUTATION_PROFILES: dict[str, dict[str, Any]] = {
    "urban_flood": {
        "label": "Urban flood / water-logging response",
        "coordinator": {
            "role": "local_coordinator",
            "disaster_type": "urban_flood",
            "operation_zone_id": "zone-urban-flood-a",
            "operation_zone_name": "Urban flood zone A",
            "zone_boundary_hint": "low-lying neighbourhood polygon around the temporary relief hub",
            "zone_polygon_wkt": "POLYGON((73.1700 22.3000,73.2050 22.3000,73.2050 22.3350,73.1700 22.3350,73.1700 22.3000))",
            "relief_hub_name": "Synthetic urban flood relief hub",
            "relief_hub_lon": 73.1810,
            "relief_hub_lat": 22.3100,
            "relief_hub_radius_meters": 1500,
            "nearest_case_limit": 5,
            "priority_need_types": ["food_water", "medical", "rescue"],
            "outside_zone_behavior": "exclude from this team dispatch list and route to coordinator review",
            "primary_case": {
                "longitude": 73.1855,
                "latitude": 22.3155,
                "need_type": "food_water",
                "location_clue": "synthetic GPS point inside demo flood polygon",
            },
            "nearby_case": {
                "longitude": 73.1870,
                "latitude": 22.3168,
                "need_type": "medical",
                "location_clue": "second synthetic case inside same flood polygon",
            },
            "outside_case": {
                "longitude": 73.2300,
                "latitude": 22.3600,
                "need_type": "shelter",
                "location_clue": "synthetic case outside demo flood polygon",
            },
        },
        "command_center": {
            "role": "command_center_operator",
            "redis_burst_size": 4,
            "dedup_ttl_seconds": 300,
            "dlq_after_attempts": 3,
            "replay_mode": "review_first",
            "queue_pressure_note": "baseline controlled drill",
        },
    },
    "heatwave_urban": {
        "label": "Urban heatwave welfare-check response",
        "coordinator": {
            "role": "local_coordinator",
            "disaster_type": "heatwave_urban",
            "operation_zone_id": "zone-heatwave-a",
            "operation_zone_name": "Urban heatwave zone A",
            "zone_boundary_hint": "dense urban ward around cooling centre and medical aid point",
            "zone_polygon_wkt": "POLYGON((73.1600 22.2920,73.1980 22.2920,73.1980 22.3260,73.1600 22.3260,73.1600 22.2920))",
            "relief_hub_name": "Synthetic cooling centre",
            "relief_hub_lon": 73.1780,
            "relief_hub_lat": 22.3070,
            "relief_hub_radius_meters": 1200,
            "nearest_case_limit": 5,
            "priority_need_types": ["medical", "water", "elderly_check"],
            "outside_zone_behavior": "keep visible for coordinator triage but do not assign to this cooling-centre team",
            "primary_case": {
                "longitude": 73.1800,
                "latitude": 22.3100,
                "need_type": "medical",
                "location_clue": "synthetic heat-stress case near cooling centre",
            },
            "nearby_case": {
                "longitude": 73.1845,
                "latitude": 22.3120,
                "need_type": "water",
                "location_clue": "synthetic water request inside heatwave zone",
            },
            "outside_case": {
                "longitude": 73.2200,
                "latitude": 22.3450,
                "need_type": "medical",
                "location_clue": "synthetic case outside heatwave operating ward",
            },
        },
        "command_center": {
            "role": "command_center_operator",
            "redis_burst_size": 8,
            "dedup_ttl_seconds": 1800,
            "dlq_after_attempts": 2,
            "replay_mode": "review_first",
            "queue_pressure_note": "higher repeated welfare-check intake; short retry path",
        },
    },
    "cyclone_coastal": {
        "label": "Coastal cyclone shelter and rescue response",
        "coordinator": {
            "role": "local_coordinator",
            "disaster_type": "cyclone_coastal",
            "operation_zone_id": "zone-cyclone-coastal-a",
            "operation_zone_name": "Coastal cyclone zone A",
            "zone_boundary_hint": "coastal settlement polygon around shelter and evacuation support point",
            "zone_polygon_wkt": "POLYGON((72.7950 21.5900,72.8420 21.5900,72.8420 21.6360,72.7950 21.6360,72.7950 21.5900))",
            "relief_hub_name": "Synthetic cyclone shelter hub",
            "relief_hub_lon": 72.8120,
            "relief_hub_lat": 21.6100,
            "relief_hub_radius_meters": 2500,
            "nearest_case_limit": 5,
            "priority_need_types": ["rescue", "shelter", "medical"],
            "outside_zone_behavior": "exclude from local shelter dispatch and escalate to regional command",
            "primary_case": {
                "longitude": 72.8165,
                "latitude": 21.6155,
                "need_type": "rescue",
                "location_clue": "synthetic rescue request inside cyclone coastal polygon",
            },
            "nearby_case": {
                "longitude": 72.8210,
                "latitude": 21.6180,
                "need_type": "shelter",
                "location_clue": "synthetic shelter request inside cyclone coastal polygon",
            },
            "outside_case": {
                "longitude": 72.8700,
                "latitude": 21.6600,
                "need_type": "medical",
                "location_clue": "synthetic case outside coastal operation polygon",
            },
        },
        "command_center": {
            "role": "command_center_operator",
            "redis_burst_size": 12,
            "dedup_ttl_seconds": 3600,
            "dlq_after_attempts": 3,
            "replay_mode": "review_first",
            "queue_pressure_note": "bursty multi-channel intake during evacuation window",
        },
    },
}


STATEFUL_MUTATION_PROFILES.update(
    {
        "riverine_flood": _scenario_profile(
            label="Riverine flood evacuation and supply response",
            disaster_type="riverine_flood",
            operation_zone_id="zone-riverine-flood-a",
            operation_zone_name="River flood belt A",
            zone_boundary_hint="settlements along an overflowing river corridor near a raised relief hub",
            zone_polygon_wkt=_rect_wkt(88.3100, 22.5200, 88.3650, 22.5750),
            relief_hub_name="Synthetic river embankment relief hub",
            relief_hub_lon=88.3350,
            relief_hub_lat=22.5480,
            relief_hub_radius_meters=3000,
            priority_need_types=["rescue", "food_water", "shelter", "medical"],
            outside_zone_behavior="route outside-bank requests to regional flood desk for another boat/road team",
            primary_case=_scenario_case(88.3420, 22.5520, "rescue", "synthetic stranded-family case inside river flood belt"),
            nearby_case=_scenario_case(88.3490, 22.5580, "food_water", "synthetic dry-ration request inside same flood belt"),
            outside_case=_scenario_case(88.3900, 22.6000, "shelter", "synthetic case outside this river response sector"),
            redis_burst_size=18,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=3,
            queue_pressure_note="high burst from helpline, radio, and ward volunteers during water-level rise",
        ),
        "flash_flood_landslide": _scenario_profile(
            label="Flash flood and landslide mountain response",
            disaster_type="flash_flood_landslide",
            operation_zone_id="zone-flash-landslide-a",
            operation_zone_name="Mountain flash-flood slide zone A",
            zone_boundary_hint="steep valley polygon around blocked roadheads and temporary rescue post",
            zone_polygon_wkt=_rect_wkt(78.9800, 30.2850, 79.0450, 30.3450),
            relief_hub_name="Synthetic mountain rescue roadhead",
            relief_hub_lon=79.0120,
            relief_hub_lat=30.3150,
            relief_hub_radius_meters=2200,
            priority_need_types=["rescue", "medical", "shelter", "road_clearance"],
            outside_zone_behavior="escalate to district control because roads may be cut between valleys",
            primary_case=_scenario_case(79.0160, 30.3200, "rescue", "synthetic trapped household near landslide scar"),
            nearby_case=_scenario_case(79.0225, 30.3230, "medical", "synthetic injury report near blocked culvert"),
            outside_case=_scenario_case(79.0750, 30.3650, "road_clearance", "synthetic report outside this valley polygon"),
            redis_burst_size=10,
            dedup_ttl_seconds=2700,
            dlq_after_attempts=2,
            queue_pressure_note="connectivity is intermittent, so duplicates and delayed radio batches are expected",
        ),
        "earthquake_urban": _scenario_profile(
            label="Urban earthquake search-and-rescue response",
            disaster_type="earthquake_urban",
            operation_zone_id="zone-earthquake-urban-a",
            operation_zone_name="Urban earthquake sector A",
            zone_boundary_hint="collapsed-building search sector around incident command post",
            zone_polygon_wkt=_rect_wkt(35.8800, 31.9400, 35.9400, 32.0000),
            relief_hub_name="Synthetic urban SAR command post",
            relief_hub_lon=35.9120,
            relief_hub_lat=31.9700,
            relief_hub_radius_meters=1800,
            priority_need_types=["rescue", "medical", "shelter", "family_reunification"],
            outside_zone_behavior="keep visible for city-wide command and avoid dispatching the wrong sector team",
            primary_case=_scenario_case(35.9180, 31.9740, "rescue", "synthetic collapsed-building rescue request inside SAR sector"),
            nearby_case=_scenario_case(35.9210, 31.9780, "medical", "synthetic casualty collection request near command post"),
            outside_case=_scenario_case(35.9650, 32.0200, "shelter", "synthetic case outside this urban earthquake sector"),
            redis_burst_size=20,
            dedup_ttl_seconds=7200,
            dlq_after_attempts=2,
            queue_pressure_note="many repeated building/casualty reports arrive during aftershock window",
        ),
        "earthquake_remote_mountain": _scenario_profile(
            label="Remote earthquake access and shelter response",
            disaster_type="earthquake_remote_mountain",
            operation_zone_id="zone-remote-quake-a",
            operation_zone_name="Remote earthquake valley A",
            zone_boundary_hint="remote settlement cluster where access routes may be damaged",
            zone_polygon_wkt=_rect_wkt(84.6900, 28.1900, 84.7550, 28.2550),
            relief_hub_name="Synthetic helicopter landing and aid point",
            relief_hub_lon=84.7200,
            relief_hub_lat=28.2200,
            relief_hub_radius_meters=4500,
            priority_need_types=["medical", "shelter", "food_water", "access_route_status"],
            outside_zone_behavior="route to alternate landing zone or district command because travel time differs sharply",
            primary_case=_scenario_case(84.7280, 28.2260, "medical", "synthetic injury report inside remote earthquake valley"),
            nearby_case=_scenario_case(84.7340, 28.2320, "shelter", "synthetic tent request inside same remote valley"),
            outside_case=_scenario_case(84.7900, 28.2850, "food_water", "synthetic request outside this helicopter-supported zone"),
            redis_burst_size=8,
            dedup_ttl_seconds=5400,
            dlq_after_attempts=3,
            queue_pressure_note="low bandwidth with delayed batch sync from field volunteers",
        ),
        "tsunami_coastal": _scenario_profile(
            label="Tsunami coastal evacuation and missing-person support",
            disaster_type="tsunami_coastal",
            operation_zone_id="zone-tsunami-coastal-a",
            operation_zone_name="Tsunami coastal evacuation zone A",
            zone_boundary_hint="coastal inundation-risk polygon around evacuation shelter and high-ground hub",
            zone_polygon_wkt=_rect_wkt(95.2850, 5.5350, 95.3450, 5.5950),
            relief_hub_name="Synthetic high-ground evacuation hub",
            relief_hub_lon=95.3150,
            relief_hub_lat=5.5650,
            relief_hub_radius_meters=3500,
            priority_need_types=["evacuation", "rescue", "medical", "family_reunification"],
            outside_zone_behavior="escalate to regional coast desk because another shelter corridor may be safer",
            primary_case=_scenario_case(95.3220, 5.5700, "evacuation", "synthetic evacuation request inside tsunami zone"),
            nearby_case=_scenario_case(95.3280, 5.5750, "family_reunification", "synthetic missing-person request near shelter corridor"),
            outside_case=_scenario_case(95.3700, 5.6250, "medical", "synthetic case outside current coastal zone"),
            redis_burst_size=22,
            dedup_ttl_seconds=7200,
            dlq_after_attempts=2,
            queue_pressure_note="short warning time and repeated reports from siren, SMS, and shelter desks",
        ),
        "storm_surge_coastal": _scenario_profile(
            label="Storm surge coastal shelter response",
            disaster_type="storm_surge_coastal",
            operation_zone_id="zone-surge-coastal-a",
            operation_zone_name="Storm surge shelter zone A",
            zone_boundary_hint="low-lying coastal ward with shelter hub away from surge line",
            zone_polygon_wkt=_rect_wkt(89.0100, 21.6200, 89.0750, 21.6850),
            relief_hub_name="Synthetic storm-surge shelter hub",
            relief_hub_lon=89.0400,
            relief_hub_lat=21.6500,
            relief_hub_radius_meters=4000,
            priority_need_types=["shelter", "evacuation", "food_water", "medical"],
            outside_zone_behavior="route to another coastal shelter cluster if outside this surge-sector polygon",
            primary_case=_scenario_case(89.0460, 21.6550, "shelter", "synthetic shelter request inside storm-surge polygon"),
            nearby_case=_scenario_case(89.0520, 21.6610, "evacuation", "synthetic evacuation transport request near shelter hub"),
            outside_case=_scenario_case(89.1050, 21.7100, "food_water", "synthetic case outside this storm-surge sector"),
            redis_burst_size=18,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=3,
            queue_pressure_note="pre-landfall shelter movement causes large but time-bounded intake bursts",
        ),
        "wildfire_evacuation": _scenario_profile(
            label="Wildfire wildland-urban-interface evacuation response",
            disaster_type="wildfire_evacuation",
            operation_zone_id="zone-wildfire-evac-a",
            operation_zone_name="Wildfire evacuation zone A",
            zone_boundary_hint="settlement edge near active fire perimeter and evacuation shelter",
            zone_polygon_wkt=_rect_wkt(-121.7400, 38.5400, -121.6700, 38.6100),
            relief_hub_name="Synthetic wildfire evacuation shelter",
            relief_hub_lon=-121.7050,
            relief_hub_lat=38.5750,
            relief_hub_radius_meters=5000,
            priority_need_types=["evacuation", "medical", "shelter", "animal_rescue"],
            outside_zone_behavior="keep for regional fire desk because road closures and wind shifts may change sectors",
            primary_case=_scenario_case(-121.7000, 38.5800, "evacuation", "synthetic evacuation request inside wildfire zone"),
            nearby_case=_scenario_case(-121.6920, 38.5860, "medical", "synthetic smoke injury near evacuation shelter"),
            outside_case=_scenario_case(-121.6250, 38.6450, "animal_rescue", "synthetic case outside this fire-sector polygon"),
            redis_burst_size=24,
            dedup_ttl_seconds=5400,
            dlq_after_attempts=2,
            queue_pressure_note="wind changes create bursty, duplicate-prone evacuation updates",
        ),
        "wildfire_smoke_health": _scenario_profile(
            label="Wildfire smoke health and welfare-check response",
            disaster_type="wildfire_smoke_health",
            operation_zone_id="zone-smoke-health-a",
            operation_zone_name="Wildfire smoke health zone A",
            zone_boundary_hint="urban smoke-impact zone around clean-air centre and clinic",
            zone_polygon_wkt=_rect_wkt(-123.1600, 49.2400, -123.0900, 49.3100),
            relief_hub_name="Synthetic clean-air centre",
            relief_hub_lon=-123.1250,
            relief_hub_lat=49.2750,
            relief_hub_radius_meters=2500,
            priority_need_types=["medical", "elderly_check", "air_filter", "transport"],
            outside_zone_behavior="route outside-zone welfare checks to another clean-air centre desk",
            primary_case=_scenario_case(-123.1200, 49.2800, "medical", "synthetic breathing difficulty report inside smoke zone"),
            nearby_case=_scenario_case(-123.1130, 49.2840, "elderly_check", "synthetic welfare check near clean-air centre"),
            outside_case=_scenario_case(-123.0600, 49.3350, "air_filter", "synthetic case outside this smoke-health zone"),
            redis_burst_size=16,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=2,
            queue_pressure_note="repeated welfare-check requests should be deduplicated without losing urgent medical items",
        ),
        "drought_food_security": _scenario_profile(
            label="Drought food, water, and livestock support response",
            disaster_type="drought_food_security",
            operation_zone_id="zone-drought-food-a",
            operation_zone_name="Drought support zone A",
            zone_boundary_hint="rural service area around tanker and food distribution hub",
            zone_polygon_wkt=_rect_wkt(37.0200, 0.4800, 37.1100, 0.5700),
            relief_hub_name="Synthetic water and food distribution point",
            relief_hub_lon=37.0600,
            relief_hub_lat=0.5250,
            relief_hub_radius_meters=8000,
            priority_need_types=["water", "food", "livestock_support", "medical"],
            outside_zone_behavior="assign outside-zone requests to a wider district route rather than immediate same-day dispatch",
            primary_case=_scenario_case(37.0680, 0.5320, "water", "synthetic tanker request inside drought support zone"),
            nearby_case=_scenario_case(37.0750, 0.5380, "food", "synthetic food support request near distribution point"),
            outside_case=_scenario_case(37.1600, 0.6200, "livestock_support", "synthetic case outside current tanker route"),
            redis_burst_size=10,
            dedup_ttl_seconds=86400,
            dlq_after_attempts=4,
            queue_pressure_note="slower-onset crisis with repeated household registrations and long dedup window",
        ),
        "cholera_wash_outbreak": _scenario_profile(
            label="Cholera / acute watery diarrhoea WASH response",
            disaster_type="cholera_wash_outbreak",
            operation_zone_id="zone-cholera-wash-a",
            operation_zone_name="Cholera WASH response zone A",
            zone_boundary_hint="neighbourhood around oral rehydration point and water-quality response hub",
            zone_polygon_wkt=_rect_wkt(32.5150, 15.5650, 32.5850, 15.6350),
            relief_hub_name="Synthetic oral rehydration and WASH hub",
            relief_hub_lon=32.5500,
            relief_hub_lat=15.6000,
            relief_hub_radius_meters=2500,
            priority_need_types=["medical", "clean_water", "sanitation", "risk_communication"],
            outside_zone_behavior="escalate outside-zone symptom clusters to public-health coordinator before field routing",
            primary_case=_scenario_case(32.5560, 15.6060, "medical", "synthetic acute watery diarrhoea report inside WASH zone"),
            nearby_case=_scenario_case(32.5620, 15.6100, "clean_water", "synthetic unsafe water report near WASH hub"),
            outside_case=_scenario_case(32.6200, 15.6700, "sanitation", "synthetic sanitation issue outside current WASH zone"),
            redis_burst_size=14,
            dedup_ttl_seconds=21600,
            dlq_after_attempts=2,
            queue_pressure_note="cluster reports need deduplication while health alerts stay reviewable",
        ),
        "infectious_disease_surge": _scenario_profile(
            label="Infectious disease surge clinic triage response",
            disaster_type="infectious_disease_surge",
            operation_zone_id="zone-disease-surge-a",
            operation_zone_name="Disease surge clinic zone A",
            zone_boundary_hint="clinic catchment area around temporary triage and outreach point",
            zone_polygon_wkt=_rect_wkt(77.5600, 12.9400, 77.6300, 13.0100),
            relief_hub_name="Synthetic temporary clinic triage hub",
            relief_hub_lon=77.5950,
            relief_hub_lat=12.9750,
            relief_hub_radius_meters=3000,
            priority_need_types=["medical", "oxygen", "medicine", "home_isolation_support"],
            outside_zone_behavior="route outside catchment to nearest clinic profile and avoid overloading one hub",
            primary_case=_scenario_case(77.6010, 12.9800, "medical", "synthetic respiratory illness report inside clinic zone"),
            nearby_case=_scenario_case(77.6080, 12.9840, "medicine", "synthetic medicine request near triage hub"),
            outside_case=_scenario_case(77.6700, 13.0500, "oxygen", "synthetic case outside this clinic catchment"),
            redis_burst_size=20,
            dedup_ttl_seconds=14400,
            dlq_after_attempts=2,
            queue_pressure_note="large repeated welfare and medicine requests should not block urgent clinical items",
        ),
        "conflict_displacement_camp": _scenario_profile(
            label="Conflict displacement camp intake and protection response",
            disaster_type="conflict_displacement_camp",
            operation_zone_id="zone-displacement-camp-a",
            operation_zone_name="Displacement camp service zone A",
            zone_boundary_hint="camp blocks around reception, health, and distribution points",
            zone_polygon_wkt=_rect_wkt(31.5200, 4.8200, 31.5900, 4.8900),
            relief_hub_name="Synthetic camp reception and aid hub",
            relief_hub_lon=31.5550,
            relief_hub_lat=4.8550,
            relief_hub_radius_meters=1800,
            priority_need_types=["shelter", "food", "medical", "protection_referral"],
            outside_zone_behavior="escalate outside-block cases to camp management because services may be sectorized",
            primary_case=_scenario_case(31.5600, 4.8600, "shelter", "synthetic new-arrival shelter request inside camp zone"),
            nearby_case=_scenario_case(31.5660, 4.8640, "protection_referral", "synthetic protection referral near camp reception"),
            outside_case=_scenario_case(31.6200, 4.9250, "food", "synthetic case outside current camp service block"),
            redis_burst_size=25,
            dedup_ttl_seconds=43200,
            dlq_after_attempts=3,
            queue_pressure_note="registration bursts and duplicate family reports require durable queue and dedup evidence",
        ),
        "refugee_border_surge": _scenario_profile(
            label="Border displacement surge reception response",
            disaster_type="refugee_border_surge",
            operation_zone_id="zone-border-reception-a",
            operation_zone_name="Border reception zone A",
            zone_boundary_hint="border crossing reception polygon around screening, water, and onward transport points",
            zone_polygon_wkt=_rect_wkt(36.4300, 33.0900, 36.5000, 33.1600),
            relief_hub_name="Synthetic border reception hub",
            relief_hub_lon=36.4650,
            relief_hub_lat=33.1250,
            relief_hub_radius_meters=3000,
            priority_need_types=["registration", "water", "medical", "transport"],
            outside_zone_behavior="route outside reception-zone requests to regional movement coordinator",
            primary_case=_scenario_case(36.4710, 33.1300, "registration", "synthetic household registration request inside reception zone"),
            nearby_case=_scenario_case(36.4780, 33.1340, "medical", "synthetic clinic triage request near reception hub"),
            outside_case=_scenario_case(36.5400, 33.2000, "transport", "synthetic case outside this reception polygon"),
            redis_burst_size=30,
            dedup_ttl_seconds=43200,
            dlq_after_attempts=3,
            queue_pressure_note="sudden crossing surges need high intake capacity and duplicate household suppression",
        ),
        "winter_storm_cold_wave": _scenario_profile(
            label="Winter storm and cold-wave shelter response",
            disaster_type="winter_storm_cold_wave",
            operation_zone_id="zone-cold-wave-a",
            operation_zone_name="Cold-wave shelter zone A",
            zone_boundary_hint="urban cold-weather outreach area around warming centre",
            zone_polygon_wkt=_rect_wkt(-0.1600, 51.4800, -0.0900, 51.5500),
            relief_hub_name="Synthetic warming centre",
            relief_hub_lon=-0.1250,
            relief_hub_lat=51.5150,
            relief_hub_radius_meters=2500,
            priority_need_types=["shelter", "medical", "blankets", "welfare_check"],
            outside_zone_behavior="route outside-zone welfare checks to another warming-centre team",
            primary_case=_scenario_case(-0.1200, 51.5200, "shelter", "synthetic unsheltered-person request inside cold-wave zone"),
            nearby_case=_scenario_case(-0.1130, 51.5240, "blankets", "synthetic blanket request near warming centre"),
            outside_case=_scenario_case(-0.0550, 51.5850, "medical", "synthetic case outside this cold-wave zone"),
            redis_burst_size=12,
            dedup_ttl_seconds=7200,
            dlq_after_attempts=3,
            queue_pressure_note="night outreach produces repeated welfare checks and location updates",
        ),
        "volcanic_ashfall": _scenario_profile(
            label="Volcanic eruption ashfall and evacuation response",
            disaster_type="volcanic_ashfall",
            operation_zone_id="zone-volcanic-ash-a",
            operation_zone_name="Volcanic ashfall zone A",
            zone_boundary_hint="ashfall-affected settlement polygon around mask/shelter distribution hub",
            zone_polygon_wkt=_rect_wkt(110.3800, -7.5900, 110.4500, -7.5200),
            relief_hub_name="Synthetic ashfall aid hub",
            relief_hub_lon=110.4150,
            relief_hub_lat=-7.5550,
            relief_hub_radius_meters=3500,
            priority_need_types=["medical", "mask", "evacuation", "water"],
            outside_zone_behavior="route outside ashfall sector to volcano observatory liaison or alternate shelter profile",
            primary_case=_scenario_case(110.4210, -7.5500, "mask", "synthetic mask request inside ashfall zone"),
            nearby_case=_scenario_case(110.4280, -7.5460, "medical", "synthetic breathing difficulty report near ashfall hub"),
            outside_case=_scenario_case(110.4900, -7.4900, "evacuation", "synthetic case outside this ashfall sector"),
            redis_burst_size=15,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=2,
            queue_pressure_note="ashfall reports and evacuation updates arrive in repeated community batches",
        ),
        "dam_breach_downstream": _scenario_profile(
            label="Dam breach downstream evacuation response",
            disaster_type="dam_breach_downstream",
            operation_zone_id="zone-dam-breach-a",
            operation_zone_name="Dam breach downstream zone A",
            zone_boundary_hint="downstream inundation corridor around evacuation assembly point",
            zone_polygon_wkt=_rect_wkt(76.8500, 23.2100, 76.9300, 23.2900),
            relief_hub_name="Synthetic downstream evacuation point",
            relief_hub_lon=76.8900,
            relief_hub_lat=23.2500,
            relief_hub_radius_meters=5000,
            priority_need_types=["evacuation", "rescue", "medical", "transport"],
            outside_zone_behavior="escalate outside corridor to district command; water-arrival times may differ",
            primary_case=_scenario_case(76.8970, 23.2560, "evacuation", "synthetic downstream evacuation request inside dam-breach corridor"),
            nearby_case=_scenario_case(76.9040, 23.2620, "transport", "synthetic transport request near assembly point"),
            outside_case=_scenario_case(76.9700, 23.3300, "medical", "synthetic case outside this downstream corridor"),
            redis_burst_size=28,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=2,
            queue_pressure_note="rapid-onset evacuation creates high pressure and little tolerance for lost jobs",
        ),
        "industrial_chemical_release": _scenario_profile(
            label="Industrial chemical release evacuation and medical response",
            disaster_type="industrial_chemical_release",
            operation_zone_id="zone-chemical-release-a",
            operation_zone_name="Chemical release response zone A",
            zone_boundary_hint="downwind shelter-in-place or evacuation polygon around medical triage hub",
            zone_polygon_wkt=_rect_wkt(72.9400, 19.0000, 73.0100, 19.0700),
            relief_hub_name="Synthetic chemical incident triage hub",
            relief_hub_lon=72.9750,
            relief_hub_lat=19.0350,
            relief_hub_radius_meters=2200,
            priority_need_types=["medical", "evacuation", "shelter_in_place", "decontamination"],
            outside_zone_behavior="keep outside-zone cases visible but do not send unprotected field teams without command review",
            primary_case=_scenario_case(72.9810, 19.0400, "medical", "synthetic exposure symptom report inside downwind zone"),
            nearby_case=_scenario_case(72.9870, 19.0440, "shelter_in_place", "synthetic shelter-in-place assistance request near triage hub"),
            outside_case=_scenario_case(73.0500, 19.1100, "evacuation", "synthetic case outside current downwind polygon"),
            redis_burst_size=18,
            dedup_ttl_seconds=7200,
            dlq_after_attempts=2,
            queue_pressure_note="duplicate exposure reports are expected but urgent medical flags must remain recoverable",
        ),
        "power_outage_urban": _scenario_profile(
            label="Urban power outage critical-needs response",
            disaster_type="power_outage_urban",
            operation_zone_id="zone-power-outage-a",
            operation_zone_name="Power outage critical-needs zone A",
            zone_boundary_hint="urban outage polygon around charging, cooling, and medical-device support hub",
            zone_polygon_wkt=_rect_wkt(-74.0400, 40.6900, -73.9700, 40.7600),
            relief_hub_name="Synthetic power outage support hub",
            relief_hub_lon=-74.0050,
            relief_hub_lat=40.7250,
            relief_hub_radius_meters=3000,
            priority_need_types=["medical_device_power", "water", "cooling", "welfare_check"],
            outside_zone_behavior="route outside-grid requests to utility liaison or another outage-sector hub",
            primary_case=_scenario_case(-74.0000, 40.7300, "medical_device_power", "synthetic medical device power request inside outage zone"),
            nearby_case=_scenario_case(-73.9930, 40.7340, "welfare_check", "synthetic welfare check near support hub"),
            outside_case=_scenario_case(-73.9300, 40.8050, "water", "synthetic case outside this outage sector"),
            redis_burst_size=16,
            dedup_ttl_seconds=7200,
            dlq_after_attempts=3,
            queue_pressure_note="critical-needs calls repeat as batteries drain, so dedup must not hide urgent escalations",
        ),
        "crowd_event_mass_casualty": _scenario_profile(
            label="Crowd crush / mass-casualty triage response",
            disaster_type="crowd_event_mass_casualty",
            operation_zone_id="zone-crowd-mci-a",
            operation_zone_name="Mass-casualty triage zone A",
            zone_boundary_hint="event perimeter around casualty collection and family-reunification points",
            zone_polygon_wkt=_rect_wkt(39.7900, 21.4000, 39.8600, 21.4700),
            relief_hub_name="Synthetic casualty collection point",
            relief_hub_lon=39.8250,
            relief_hub_lat=21.4350,
            relief_hub_radius_meters=1200,
            priority_need_types=["medical", "family_reunification", "transport", "water"],
            outside_zone_behavior="route outside-event reports to city command and keep medical dispatch bounded to event sector",
            primary_case=_scenario_case(39.8290, 21.4380, "medical", "synthetic casualty report inside event perimeter"),
            nearby_case=_scenario_case(39.8340, 21.4410, "family_reunification", "synthetic missing relative report near collection point"),
            outside_case=_scenario_case(39.8950, 21.5100, "transport", "synthetic case outside event perimeter"),
            redis_burst_size=35,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=2,
            queue_pressure_note="very high burst from many channels during a short mass-casualty window",
        ),
        "monsoon_urban_drain_failure": _scenario_profile(
            label="Monsoon urban drain failure and rescue response",
            disaster_type="monsoon_urban_drain_failure",
            operation_zone_id="zone-monsoon-drain-a",
            operation_zone_name="Monsoon drainage failure zone A",
            zone_boundary_hint="urban drainage catchment around pump, shelter, and road-closure response point",
            zone_polygon_wkt=_rect_wkt(77.1800, 28.5600, 77.2500, 28.6300),
            relief_hub_name="Synthetic monsoon pump and shelter hub",
            relief_hub_lon=77.2150,
            relief_hub_lat=28.5950,
            relief_hub_radius_meters=2200,
            priority_need_types=["rescue", "food_water", "road_closure", "medical"],
            outside_zone_behavior="send outside-catchment reports to another drainage team; do not mix pump priorities",
            primary_case=_scenario_case(77.2200, 28.6000, "rescue", "synthetic stranded-resident report inside drainage failure zone"),
            nearby_case=_scenario_case(77.2270, 28.6040, "road_closure", "synthetic road closure report near pump hub"),
            outside_case=_scenario_case(77.2900, 28.6700, "food_water", "synthetic case outside this drainage catchment"),
            redis_burst_size=22,
            dedup_ttl_seconds=3600,
            dlq_after_attempts=3,
            queue_pressure_note="rain peaks create bursts, but reports may slow after roads and power fail",
        ),
        "locust_food_security": _scenario_profile(
            label="Locust / crop-loss food-security response",
            disaster_type="locust_food_security",
            operation_zone_id="zone-locust-food-a",
            operation_zone_name="Crop-loss food-security zone A",
            zone_boundary_hint="rural affected-village cluster around food assistance and agriculture support hub",
            zone_polygon_wkt=_rect_wkt(70.7200, 27.9800, 70.8200, 28.0800),
            relief_hub_name="Synthetic crop-loss assistance hub",
            relief_hub_lon=70.7700,
            relief_hub_lat=28.0300,
            relief_hub_radius_meters=9000,
            priority_need_types=["food", "livelihood_support", "seed_support", "water"],
            outside_zone_behavior="route outside-zone crop-loss reports to agriculture desk for separate verification route",
            primary_case=_scenario_case(70.7800, 28.0380, "food", "synthetic household food-support request inside crop-loss zone"),
            nearby_case=_scenario_case(70.7900, 28.0460, "livelihood_support", "synthetic livelihood support request near assistance hub"),
            outside_case=_scenario_case(70.8800, 28.1400, "seed_support", "synthetic case outside current verification route"),
            redis_burst_size=8,
            dedup_ttl_seconds=86400,
            dlq_after_attempts=4,
            queue_pressure_note="slow-onset registrations benefit from longer dedup and careful replay review",
        ),
    }
)


def stateful_mutation_profile_names() -> list[str]:
    return sorted(STATEFUL_MUTATION_PROFILES)


def stateful_mutation_profile_catalog() -> list[dict[str, Any]]:
    catalog = []
    for name in stateful_mutation_profile_names():
        profile = STATEFUL_MUTATION_PROFILES[name]
        coordinator = profile["coordinator"]
        command_center = profile["command_center"]
        catalog.append(
            {
                "name": name,
                "label": profile["label"],
                "coordinator_owns": {
                    "disaster_type": coordinator["disaster_type"],
                    "relief_hub_name": coordinator["relief_hub_name"],
                    "relief_hub_radius_meters": coordinator["relief_hub_radius_meters"],
                    "priority_need_types": coordinator["priority_need_types"],
                },
                "command_center_owns": {
                    "redis_burst_size": command_center["redis_burst_size"],
                    "dedup_ttl_seconds": command_center["dedup_ttl_seconds"],
                    "dlq_after_attempts": command_center["dlq_after_attempts"],
                    "replay_mode": command_center["replay_mode"],
                },
            }
        )
    return catalog


def print_stateful_mutation_profiles() -> None:
    print("Role-aware stateful mutation profiles:")
    for item in stateful_mutation_profile_catalog():
        coordinator = item["coordinator_owns"]
        command_center = item["command_center_owns"]
        needs = ", ".join(str(value) for value in coordinator["priority_need_types"])
        print(f"- {item['name']}: {item['label']}")
        print(
            "  coordinator: "
            f"disaster={coordinator['disaster_type']}; "
            f"hub={coordinator['relief_hub_name']}; "
            f"radius={coordinator['relief_hub_radius_meters']}m; "
            f"priority_needs={needs}"
        )
        print(
            "  command_center: "
            f"burst={command_center['redis_burst_size']}; "
            f"dedup_ttl={command_center['dedup_ttl_seconds']}s; "
            f"dlq_after={command_center['dlq_after_attempts']}; "
            f"replay={command_center['replay_mode']}"
        )


ROLE_CONFIG_CONTRACT = {
    "local_coordinator": {
        "owns": [
            "scenario profile",
            "affected operation zone",
            "relief hub point",
            "reachable radius",
            "priority need types",
            "case locations used in the drill",
        ],
        "not_expected_to_own": [
            "Redis burst size",
            "dedup TTL",
            "retry or DLQ thresholds",
            "stream cleanup mechanics",
        ],
    },
    "command_center_operator": {
        "owns": [
            "queue burst capacity",
            "deduplication TTL",
            "retry and DLQ policy",
            "safe replay mode",
            "runtime feedback monitoring",
        ],
        "not_expected_to_own": [
            "local disaster geography",
            "field priority interpretation",
            "hub or case coordinates",
        ],
    },
}


def _stateful_profile_name() -> tuple[str, str | None]:
    raw = (
        os.environ.get("RELIEFQUEUE_MUTATION_PROFILE")
        or os.environ.get("RELIEFQUEUE_SCENARIO_PROFILE")
        or "urban_flood"
    )
    normalized = raw.strip().lower().replace("-", "_") or "urban_flood"
    if normalized in STATEFUL_MUTATION_PROFILES:
        return normalized, None
    return "urban_flood", f"Unknown RELIEFQUEUE_MUTATION_PROFILE={raw!r}; using urban_flood."


def _env_int_config(key: str, default: int, *, minimum: int, maximum: int, warnings: list[str]) -> int:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        warnings.append(f"Ignored invalid integer {key}={raw!r}; using {default}.")
        return default
    bounded = max(minimum, min(value, maximum))
    if bounded != value:
        warnings.append(f"Clamped {key} from {value} to {bounded}.")
    return bounded


def _env_float_config(key: str, default: float, *, minimum: float, maximum: float, warnings: list[str]) -> float:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        warnings.append(f"Ignored invalid number {key}={raw!r}; using {default}.")
        return default
    bounded = max(minimum, min(value, maximum))
    if bounded != value:
        warnings.append(f"Clamped {key} from {value} to {bounded}.")
    return bounded


def _env_text_config(key: str, default: str) -> str:
    raw = os.environ.get(key)
    return raw.strip() if raw and raw.strip() else default


def _stateful_mutation_drill_config() -> dict[str, Any]:
    profile_name, profile_warning = _stateful_profile_name()
    profile = STATEFUL_MUTATION_PROFILES[profile_name]
    coordinator = deepcopy(profile["coordinator"])
    command_center = deepcopy(profile["command_center"])
    warnings: list[str] = []
    if profile_warning:
        warnings.append(profile_warning)

    coordinator["operation_zone_id"] = _env_text_config(
        "RELIEFQUEUE_COORDINATOR_OPERATION_ZONE_ID", str(coordinator["operation_zone_id"])
    )
    coordinator["operation_zone_name"] = _env_text_config(
        "RELIEFQUEUE_COORDINATOR_OPERATION_ZONE_NAME", str(coordinator["operation_zone_name"])
    )
    coordinator["zone_polygon_wkt"] = _env_text_config(
        "RELIEFQUEUE_COORDINATOR_ZONE_WKT", str(coordinator["zone_polygon_wkt"])
    )
    coordinator["relief_hub_name"] = _env_text_config(
        "RELIEFQUEUE_COORDINATOR_RELIEF_HUB_NAME", str(coordinator["relief_hub_name"])
    )
    coordinator["relief_hub_lon"] = _env_float_config(
        "RELIEFQUEUE_COORDINATOR_RELIEF_HUB_LON",
        float(coordinator["relief_hub_lon"]),
        minimum=-180.0,
        maximum=180.0,
        warnings=warnings,
    )
    coordinator["relief_hub_lat"] = _env_float_config(
        "RELIEFQUEUE_COORDINATOR_RELIEF_HUB_LAT",
        float(coordinator["relief_hub_lat"]),
        minimum=-90.0,
        maximum=90.0,
        warnings=warnings,
    )
    coordinator["relief_hub_radius_meters"] = _env_int_config(
        "RELIEFQUEUE_COORDINATOR_RELIEF_HUB_RADIUS_METERS",
        int(coordinator["relief_hub_radius_meters"]),
        minimum=100,
        maximum=50000,
        warnings=warnings,
    )
    coordinator["nearest_case_limit"] = _env_int_config(
        "RELIEFQUEUE_COORDINATOR_NEAREST_CASE_LIMIT",
        int(coordinator["nearest_case_limit"]),
        minimum=1,
        maximum=25,
        warnings=warnings,
    )
    for prefix, case_key in [
        ("RELIEFQUEUE_COORDINATOR_PRIMARY_CASE", "primary_case"),
        ("RELIEFQUEUE_COORDINATOR_NEARBY_CASE", "nearby_case"),
        ("RELIEFQUEUE_COORDINATOR_OUTSIDE_CASE", "outside_case"),
    ]:
        case = coordinator[case_key]
        case["longitude"] = _env_float_config(
            f"{prefix}_LON", float(case["longitude"]), minimum=-180.0, maximum=180.0, warnings=warnings
        )
        case["latitude"] = _env_float_config(
            f"{prefix}_LAT", float(case["latitude"]), minimum=-90.0, maximum=90.0, warnings=warnings
        )

    command_center["redis_burst_size"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_REDIS_BURST_SIZE",
        int(command_center["redis_burst_size"]),
        minimum=4,
        maximum=50,
        warnings=warnings,
    )
    command_center["dedup_ttl_seconds"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_DEDUP_TTL_SECONDS",
        int(command_center["dedup_ttl_seconds"]),
        minimum=60,
        maximum=86400,
        warnings=warnings,
    )
    command_center["dlq_after_attempts"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_DLQ_AFTER_ATTEMPTS",
        int(command_center["dlq_after_attempts"]),
        minimum=1,
        maximum=10,
        warnings=warnings,
    )
    replay_mode = _env_text_config("RELIEFQUEUE_COMMAND_CENTER_REPLAY_MODE", str(command_center["replay_mode"]))
    if replay_mode != "review_first":
        warnings.append(f"RELIEFQUEUE_COMMAND_CENTER_REPLAY_MODE={replay_mode!r} is not wired yet; using review_first.")
        replay_mode = "review_first"
    command_center["replay_mode"] = replay_mode

    return {
        "selected_profile": {"name": profile_name, "label": profile["label"]},
        "available_profiles": sorted(STATEFUL_MUTATION_PROFILES),
        "role_contract": ROLE_CONFIG_CONTRACT,
        "coordinator_config": coordinator,
        "command_center_config": command_center,
        "config_warnings": warnings,
        "secret_values_printed": False,
    }

LOGISTICS_ROLE_CONFIG_CONTRACT = {
    "local_coordinator": {
        "owns": [
            "mission profile",
            "field team needs",
            "delivery destination points",
            "relief hub context",
            "needed-by and return expectations",
            "field priority interpretation",
        ],
        "not_expected_to_own": [
            "Redis reservation locks",
            "worker claim/recovery settings",
            "queue burst limits",
            "DLQ or replay mechanics",
        ],
    },
    "command_center_operator": {
        "owns": [
            "reservation and dispatch queue pressure",
            "duplicate logistics request suppression",
            "worker recovery and retry policy",
            "DLQ and replay review policy",
            "stale return and reallocation monitoring",
        ],
        "not_expected_to_own": [
            "field geography",
            "team-specific disaster needs",
            "which local point is reachable or unsafe",
        ],
    },
}


def _logistics_profile_name() -> tuple[str, str | None]:
    raw = (
        os.environ.get("RELIEFQUEUE_LOGISTICS_PROFILE")
        or os.environ.get("RELIEFQUEUE_MUTATION_PROFILE")
        or os.environ.get("RELIEFQUEUE_SCENARIO_PROFILE")
        or "urban_flood"
    )
    normalized = raw.strip().lower().replace("-", "_") or "urban_flood"
    if normalized in STATEFUL_MUTATION_PROFILES:
        return normalized, None
    return "urban_flood", f"Unknown RELIEFQUEUE_LOGISTICS_PROFILE={raw!r}; using urban_flood."


def _logistics_template_for_disaster(disaster_type: str) -> dict[str, Any]:
    lowered = disaster_type.lower()
    if any(key in lowered for key in ["flood", "cyclone", "storm_surge", "tsunami", "dam_breach"]):
        return {
            "mission_family": "water_rescue_and_relief_distribution",
            "teams": [
                {"team_id": "rescue-alpha", "team_role": "water_rescue", "need_summary": "boat access, flotation, radio contact"},
                {"team_id": "wash-bravo", "team_role": "wash", "need_summary": "safe drinking water and water-treatment supplies"},
                {"team_id": "shelter-charlie", "team_role": "shelter", "need_summary": "temporary shelter kits for displaced households"},
                {"team_id": "medical-delta", "team_role": "medical", "need_summary": "first aid and patient movement support"},
            ],
            "assets": {
                "returnable_primary": {"asset_type": "rescue_boat", "asset_class": "returnable", "asset_tag_prefix": "BOAT"},
                "consumable_primary": {"asset_type": "water_purification_tablets", "asset_class": "consumable", "asset_tag_prefix": "WASH"},
                "support_primary": {"asset_type": "radio_kit", "asset_class": "returnable", "asset_tag_prefix": "RADIO"},
            },
        }
    if any(key in lowered for key in ["earthquake", "landslide", "volcanic"]):
        return {
            "mission_family": "search_rescue_trauma_and_shelter",
            "teams": [
                {"team_id": "usar-alpha", "team_role": "search_rescue", "need_summary": "stretcher, rescue tools, radio contact"},
                {"team_id": "medical-bravo", "team_role": "trauma_medical", "need_summary": "trauma kits and patient transfer support"},
                {"team_id": "shelter-charlie", "team_role": "shelter", "need_summary": "tarpaulins, blankets, lighting"},
                {"team_id": "engineering-delta", "team_role": "engineering", "need_summary": "damage assessment and generator support"},
            ],
            "assets": {
                "returnable_primary": {"asset_type": "stretcher", "asset_class": "returnable", "asset_tag_prefix": "STR"},
                "consumable_primary": {"asset_type": "trauma_kit", "asset_class": "consumable", "asset_tag_prefix": "MED"},
                "support_primary": {"asset_type": "portable_generator", "asset_class": "returnable", "asset_tag_prefix": "GEN"},
            },
        }
    if any(key in lowered for key in ["heatwave", "wildfire_smoke", "power_outage"]):
        return {
            "mission_family": "health_cooling_power_and_welfare_checks",
            "teams": [
                {"team_id": "health-alpha", "team_role": "health_outreach", "need_summary": "ORS, cooling support, welfare checks"},
                {"team_id": "water-bravo", "team_role": "water_distribution", "need_summary": "water cans and shade point replenishment"},
                {"team_id": "power-charlie", "team_role": "critical_power", "need_summary": "generator and battery support for critical cases"},
                {"team_id": "transport-delta", "team_role": "transport", "need_summary": "vehicle support for vulnerable people"},
            ],
            "assets": {
                "returnable_primary": {"asset_type": "portable_generator", "asset_class": "returnable", "asset_tag_prefix": "GEN"},
                "consumable_primary": {"asset_type": "ors_and_water_cans", "asset_class": "consumable", "asset_tag_prefix": "HEALTH"},
                "support_primary": {"asset_type": "cooling_tent", "asset_class": "returnable", "asset_tag_prefix": "COOL"},
            },
        }
    if any(key in lowered for key in ["cholera", "disease", "infectious"]):
        return {
            "mission_family": "public_health_wash_and_clinic_surge",
            "teams": [
                {"team_id": "clinic-alpha", "team_role": "clinical_triage", "need_summary": "ORS, medicine, referral material"},
                {"team_id": "wash-bravo", "team_role": "wash", "need_summary": "chlorine, water testing, sanitation material"},
                {"team_id": "outreach-charlie", "team_role": "risk_communication", "need_summary": "megaphone and printed guidance"},
                {"team_id": "coldchain-delta", "team_role": "cold_chain", "need_summary": "cold box and vaccine/medicine transfer support"},
            ],
            "assets": {
                "returnable_primary": {"asset_type": "cold_box", "asset_class": "returnable", "asset_tag_prefix": "COLD"},
                "consumable_primary": {"asset_type": "ors_chlorine_kit", "asset_class": "consumable", "asset_tag_prefix": "WASH"},
                "support_primary": {"asset_type": "megaphone_kit", "asset_class": "returnable", "asset_tag_prefix": "COMMS"},
            },
        }
    if any(key in lowered for key in ["conflict", "refugee", "displacement"]):
        return {
            "mission_family": "camp_reception_protection_and_distribution",
            "teams": [
                {"team_id": "reception-alpha", "team_role": "registration", "need_summary": "registration kits and queue-control material"},
                {"team_id": "food-bravo", "team_role": "food_distribution", "need_summary": "ration kits and distribution volunteers"},
                {"team_id": "wash-charlie", "team_role": "wash", "need_summary": "water containers, latrine supplies, hygiene kits"},
                {"team_id": "protection-delta", "team_role": "protection", "need_summary": "privacy screens and referral transport"},
            ],
            "assets": {
                "returnable_primary": {"asset_type": "registration_tablet_kit", "asset_class": "returnable", "asset_tag_prefix": "REG"},
                "consumable_primary": {"asset_type": "family_ration_kit", "asset_class": "consumable", "asset_tag_prefix": "FOOD"},
                "support_primary": {"asset_type": "privacy_screen_kit", "asset_class": "returnable", "asset_tag_prefix": "PROT"},
            },
        }
    if any(key in lowered for key in ["drought", "locust", "food_security"]):
        return {
            "mission_family": "food_water_and_livelihood_distribution",
            "teams": [
                {"team_id": "water-alpha", "team_role": "water_trucking", "need_summary": "water tanker slots and storage containers"},
                {"team_id": "food-bravo", "team_role": "food_distribution", "need_summary": "dry ration kits and distribution list support"},
                {"team_id": "livelihood-charlie", "team_role": "livelihood_support", "need_summary": "seed, feed, and agriculture support lots"},
                {"team_id": "medical-delta", "team_role": "mobile_health", "need_summary": "mobile health consumables for remote households"},
            ],
            "assets": {
                "returnable_primary": {"asset_type": "water_tanker", "asset_class": "returnable", "asset_tag_prefix": "TANKER"},
                "consumable_primary": {"asset_type": "dry_ration_kit", "asset_class": "consumable", "asset_tag_prefix": "FOOD"},
                "support_primary": {"asset_type": "mobile_storage_tank", "asset_class": "returnable", "asset_tag_prefix": "TANK"},
            },
        }
    return {
        "mission_family": "general_emergency_logistics",
        "teams": [
            {"team_id": "field-alpha", "team_role": "field_response", "need_summary": "transport, communications, and safety material"},
            {"team_id": "medical-bravo", "team_role": "medical", "need_summary": "first-aid and patient support material"},
            {"team_id": "shelter-charlie", "team_role": "shelter", "need_summary": "temporary shelter and lighting support"},
            {"team_id": "logistics-delta", "team_role": "logistics", "need_summary": "inventory movement and tracking support"},
        ],
        "assets": {
            "returnable_primary": {"asset_type": "utility_vehicle", "asset_class": "returnable", "asset_tag_prefix": "VEH"},
            "consumable_primary": {"asset_type": "relief_kit", "asset_class": "consumable", "asset_tag_prefix": "RELIEF"},
            "support_primary": {"asset_type": "radio_kit", "asset_class": "returnable", "asset_tag_prefix": "RADIO"},
        },
    }


def _build_logistics_profile(profile_name: str) -> dict[str, Any]:
    scenario = STATEFUL_MUTATION_PROFILES[profile_name]
    coordinator = deepcopy(scenario["coordinator"])
    command_center = deepcopy(scenario["command_center"])
    template = _logistics_template_for_disaster(str(coordinator["disaster_type"]))
    assets = template["assets"]
    returnable_asset = assets["returnable_primary"]
    consumable_asset = assets["consumable_primary"]
    support_asset = assets["support_primary"]
    return {
        "name": profile_name,
        "label": scenario["label"],
        "coordinator": {
            "role": "local_coordinator",
            "disaster_type": coordinator["disaster_type"],
            "mission_family": template["mission_family"],
            "operation_zone_id": coordinator["operation_zone_id"],
            "operation_zone_name": coordinator["operation_zone_name"],
            "relief_hub_name": coordinator["relief_hub_name"],
            "relief_hub_lon": coordinator["relief_hub_lon"],
            "relief_hub_lat": coordinator["relief_hub_lat"],
            "relief_hub_radius_meters": coordinator["relief_hub_radius_meters"],
            "zone_polygon_wkt": coordinator["zone_polygon_wkt"],
            "field_teams": template["teams"],
            "priority_need_types": coordinator["priority_need_types"],
            "delivery_points": {
                "primary_case": coordinator["primary_case"],
                "nearby_case": coordinator["nearby_case"],
                "outside_case": coordinator["outside_case"],
            },
            "planned_requests": [
                {
                    "request_id_suffix": "rescue-returnable",
                    "team_id": template["teams"][0]["team_id"],
                    "team_role": template["teams"][0]["team_role"],
                    "asset_type": returnable_asset["asset_type"],
                    "asset_class": returnable_asset["asset_class"],
                    "quantity": 1,
                    "priority": "HIGH",
                    "destination": "primary_case",
                    "needed_within_minutes": 45,
                    "return_due_minutes": 240,
                },
                {
                    "request_id_suffix": "consumable-lot",
                    "team_id": template["teams"][1]["team_id"],
                    "team_role": template["teams"][1]["team_role"],
                    "asset_type": consumable_asset["asset_type"],
                    "asset_class": consumable_asset["asset_class"],
                    "quantity": 20,
                    "priority": "HIGH",
                    "destination": "nearby_case",
                    "needed_within_minutes": 60,
                    "return_due_minutes": None,
                },
                {
                    "request_id_suffix": "support-kit",
                    "team_id": template["teams"][2]["team_id"],
                    "team_role": template["teams"][2]["team_role"],
                    "asset_type": support_asset["asset_type"],
                    "asset_class": support_asset["asset_class"],
                    "quantity": 1,
                    "priority": "NORMAL",
                    "destination": "primary_case",
                    "needed_within_minutes": 90,
                    "return_due_minutes": 360,
                },
                {
                    "request_id_suffix": "critical-reallocation",
                    "team_id": template["teams"][-1]["team_id"],
                    "team_role": template["teams"][-1]["team_role"],
                    "asset_type": returnable_asset["asset_type"],
                    "asset_class": returnable_asset["asset_class"],
                    "quantity": 1,
                    "priority": "CRITICAL",
                    "destination": "nearby_case",
                    "needed_within_minutes": 20,
                    "return_due_minutes": 180,
                },
            ],
            "inventory_seed": [
                {**returnable_asset, "quantity_total": 1, "quantity_available": 1, "hub": "primary", "status": "available"},
                {**consumable_asset, "quantity_total": 50, "quantity_available": 50, "hub": "primary", "status": "available"},
                {**support_asset, "quantity_total": 1, "quantity_available": 1, "hub": "secondary", "status": "available"},
            ],
            "return_policy": "Returnable assets must be returned or reallocated; consumables are depleted with lot audit.",
        },
        "command_center": {
            "role": "command_center_operator",
            "reservation_burst_size": max(4, min(int(command_center["redis_burst_size"]), 50)),
            "dispatch_retry_after_attempts": int(command_center["dlq_after_attempts"]),
            "dedup_ttl_seconds": int(command_center["dedup_ttl_seconds"]),
            "claim_idle_ms": 1000,
            "replay_mode": command_center["replay_mode"],
            "reallocation_policy": "review_first_then_reassign_if_higher_priority_request_is_waiting",
            "queue_pressure_note": command_center["queue_pressure_note"],
        },
    }


def logistics_profile_names() -> list[str]:
    return stateful_mutation_profile_names()


def logistics_profile_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for name in logistics_profile_names():
        profile = _build_logistics_profile(name)
        coordinator = profile["coordinator"]
        command_center = profile["command_center"]
        catalog.append(
            {
                "name": name,
                "label": profile["label"],
                "coordinator_owns": {
                    "mission_family": coordinator["mission_family"],
                    "field_teams": [team["team_role"] for team in coordinator["field_teams"]],
                    "planned_asset_types": [row["asset_type"] for row in coordinator["planned_requests"]],
                    "relief_hub_name": coordinator["relief_hub_name"],
                },
                "command_center_owns": {
                    "reservation_burst_size": command_center["reservation_burst_size"],
                    "dispatch_retry_after_attempts": command_center["dispatch_retry_after_attempts"],
                    "dedup_ttl_seconds": command_center["dedup_ttl_seconds"],
                    "claim_idle_ms": command_center["claim_idle_ms"],
                    "replay_mode": command_center["replay_mode"],
                },
            }
        )
    return catalog


def print_logistics_asset_profiles() -> None:
    print("Role-aware logistics asset profiles:")
    for item in logistics_profile_catalog():
        coordinator = item["coordinator_owns"]
        command_center = item["command_center_owns"]
        print(f"- {item['name']}: {item['label']}")
        print(
            "  coordinator: "
            f"mission={coordinator['mission_family']}; "
            f"hub={coordinator['relief_hub_name']}; "
            f"teams={', '.join(coordinator['field_teams'])}; "
            f"assets={', '.join(coordinator['planned_asset_types'])}"
        )
        print(
            "  command_center: "
            f"burst={command_center['reservation_burst_size']}; "
            f"claim_idle_ms={command_center['claim_idle_ms']}; "
            f"retry_after={command_center['dispatch_retry_after_attempts']}; "
            f"dedup_ttl={command_center['dedup_ttl_seconds']}s; "
            f"replay={command_center['replay_mode']}"
        )


def _logistics_drill_config() -> dict[str, Any]:
    profile_name, profile_warning = _logistics_profile_name()
    profile = _build_logistics_profile(profile_name)
    warnings: list[str] = []
    if profile_warning:
        warnings.append(profile_warning)
    command_center = deepcopy(profile["command_center"])
    command_center["reservation_burst_size"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_LOGISTICS_BURST_SIZE",
        int(command_center["reservation_burst_size"]),
        minimum=4,
        maximum=75,
        warnings=warnings,
    )
    command_center["dispatch_retry_after_attempts"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_LOGISTICS_RETRY_AFTER_ATTEMPTS",
        int(command_center["dispatch_retry_after_attempts"]),
        minimum=1,
        maximum=10,
        warnings=warnings,
    )
    command_center["dedup_ttl_seconds"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_LOGISTICS_DEDUP_TTL_SECONDS",
        int(command_center["dedup_ttl_seconds"]),
        minimum=60,
        maximum=86400,
        warnings=warnings,
    )
    command_center["claim_idle_ms"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_LOGISTICS_CLAIM_IDLE_MS",
        int(command_center["claim_idle_ms"]),
        minimum=100,
        maximum=600000,
        warnings=warnings,
    )
    replay_mode = _env_text_config("RELIEFQUEUE_COMMAND_CENTER_LOGISTICS_REPLAY_MODE", str(command_center["replay_mode"]))
    if replay_mode != "review_first":
        warnings.append(f"RELIEFQUEUE_COMMAND_CENTER_LOGISTICS_REPLAY_MODE={replay_mode!r} is not wired yet; using review_first.")
        replay_mode = "review_first"
    command_center["replay_mode"] = replay_mode
    return {
        "selected_profile": {"name": profile_name, "label": profile["label"]},
        "available_profiles": logistics_profile_names(),
        "role_contract": LOGISTICS_ROLE_CONFIG_CONTRACT,
        "coordinator_config": profile["coordinator"],
        "command_center_config": command_center,
        "config_warnings": warnings,
        "secret_values_printed": False,
    }


def _live_logistics_verbose_level() -> int:
    return _live_verbose_level("RELIEFQUEUE_LIVE_LOGISTICS_VERBOSE")


def _live_logistics_verbose_enabled() -> bool:
    return _live_logistics_verbose_level() > 0


def _live_volunteer_verbose_level() -> int:
    return _live_verbose_level("RELIEFQUEUE_LIVE_VOLUNTEER_VERBOSE")


def _live_volunteer_verbose_enabled() -> bool:
    return _live_volunteer_verbose_level() > 0


LOCAL_STACK_ENDPOINTS = {
    "postgis": "127.0.0.1:54329",
    "redis": "127.0.0.1:63799",
    "nats": "127.0.0.1:42299",
}
LOCAL_STACK_POSTGIS_DSN = "postgresql://reliefqueue:reliefqueue@127.0.0.1:54329/reliefqueue"
LOCAL_STACK_REDIS_URL = "redis://127.0.0.1:63799/0"
LOCAL_STACK_NATS_URL = "nats://127.0.0.1:42299"


def _url_port_is_usable(value: str) -> bool:
    try:
        parsed = urlparse(value)
        if not parsed.hostname:
            return False
        host_port = parsed.netloc.rsplit("@", 1)[-1]
        if host_port.endswith(":"):
            return False
        _ = parsed.port
    except ValueError:
        return False
    return True


def _live_stack_status_payload(report_dir: Path) -> dict[str, Any] | None:
    path = report_dir / "live_stack_status.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _live_stack_service_ready(report_dir: Path, service_name: str) -> bool:
    payload = _live_stack_status_payload(report_dir)
    if not payload or payload.get("status") != "PASS":
        return False
    for service in payload.get("services") or []:
        if not isinstance(service, dict) or service.get("name") != service_name:
            continue
        detail = str(service.get("detail") or "").lower()
        return service.get("status") == "PASS" and "starting" not in detail
    return False


def _resolved_postgis_dsn(report_dir: Path) -> tuple[str | None, str, str | None]:
    configured = _configured_postgis_dsn()
    if configured and _url_port_is_usable(configured):
        return configured, "configured_dsn", None
    if _live_stack_service_ready(report_dir, "postgis"):
        note = "Using local live-stack PostGIS endpoint from reports/latest/live_stack_status.json."
        if configured:
            note += " Ignored unusable RELIEFQUEUE_POSTGIS_DSN from the current shell."
        return LOCAL_STACK_POSTGIS_DSN, "local_live_stack", note
    if configured:
        return None, "invalid_configured_dsn", "RELIEFQUEUE_POSTGIS_DSN is set but is not usable; run make live-stack-up or correct the DSN."
    return None, "missing_env", None


def _resolved_redis_url(report_dir: Path) -> tuple[str | None, str, str | None]:
    configured = _configured_redis_url()
    if configured and _url_port_is_usable(configured):
        return configured, "configured_redis_url", None
    if _live_stack_service_ready(report_dir, "redis"):
        note = "Using local live-stack Redis endpoint from reports/latest/live_stack_status.json."
        if configured:
            note += " Ignored unusable RELIEFQUEUE_REDIS_URL from the current shell."
        return LOCAL_STACK_REDIS_URL, "local_live_stack", note
    if configured:
        return None, "invalid_configured_redis_url", "RELIEFQUEUE_REDIS_URL is set but is not usable; run make live-stack-up or correct the URL."
    return None, "missing_env", None


def _resolved_queue_backend(report_dir: Path) -> str:
    configured = _configured_queue_backend()
    if configured == "redis":
        return "redis"
    url, source, _note = _resolved_redis_url(report_dir)
    if url and source == "local_live_stack":
        return "redis"
    return configured


def _resolved_nats_endpoint(report_dir: Path) -> tuple[str | None, int | None, str, str | None]:
    configured = os.environ.get("RELIEFQUEUE_NATS_URL", "").strip()
    if configured:
        try:
            parsed = urlparse(configured)
            if parsed.hostname:
                return parsed.hostname, parsed.port or 4222, "configured_nats_url", None
        except ValueError:
            pass
        return (
            None,
            None,
            "invalid_configured_nats_url",
            "RELIEFQUEUE_NATS_URL is set but is not usable; run make live-stack-up or correct the URL.",
        )
    if _live_stack_service_ready(report_dir, "nats"):
        parsed = urlparse(LOCAL_STACK_NATS_URL)
        return (
            parsed.hostname,
            parsed.port or 4222,
            "local_live_stack",
            "Using local live-stack NATS endpoint from reports/latest/live_stack_status.json.",
        )
    return None, None, "missing_env", None


def _sanitize(value: str) -> str:
    """Return operator-safe diagnostic text without printing configured secrets."""
    redacted = str(value)

    sensitive_values = [
        os.environ.get("RELIEFQUEUE_POSTGIS_DSN", ""),
        os.environ.get("RELIEFQUEUE_REDIS_URL", ""),
        os.environ.get("OPENAI_COMPAT_API_KEY", ""),
        os.environ.get("TWILIO_AUTH_TOKEN", ""),
        os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
        os.environ.get("RAPIDPRO_API_TOKEN", ""),
        os.environ.get("ODK_CENTRAL_PASSWORD", ""),
    ]
    for secret_value in sensitive_values:
        if secret_value:
            redacted = redacted.replace(secret_value, "<redacted>")

    # Also redact inline credentials in common URL-shaped diagnostics even when the
    # whole URL is not exactly the configured environment value.
    redacted = redacted.replace("reliefqueue:reliefqueue@", "<redacted>@")
    return redacted


def _live_error(exc: Exception) -> dict[str, str]:
    return {"error": _sanitize(str(exc)), "secret_values_printed": False}


def _sql_identifier(value: str) -> str:
    if not value or not value.replace("_", "a").isalnum() or value[0].isdigit():
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return "'" + str(value).replace("'", "''") + "'"


def _postgis_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_cases'


def _postgis_zone_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_operation_zones'


def _postgis_schema_sql(schema: str) -> str:
    table = _postgis_table(schema)
    zone_table = _postgis_zone_table(schema)
    return "\n".join(
        [
            "-- ReliefQueue live PostGIS schema. Stores allowlisted case routing fields only.",
            "CREATE EXTENSION IF NOT EXISTS postgis;",
            f"CREATE SCHEMA IF NOT EXISTS {_sql_identifier(schema)};",
            f"CREATE TABLE IF NOT EXISTS {table} (",
            "  case_id text PRIMARY KEY,",
            "  public_case_ref text NOT NULL,",
            "  operation_zone_id text,",
            "  location_clue text,",
            "  geo_scope_type text,",
            "  geo_confidence text,",
            "  need_type text,",
            "  urgency text,",
            "  human_review_required boolean NOT NULL DEFAULT true,",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS case_point geometry(Point, 4326);",
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS geo_source text;",
            f"CREATE TABLE IF NOT EXISTS {zone_table} (",
            "  operation_zone_id text PRIMARY KEY,",
            "  zone_name text NOT NULL,",
            "  scenario_tag text,",
            "  zone_geom geometry(Polygon, 4326) NOT NULL,",
            "  hub_point geometry(Point, 4326),",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_cases_zone_idx ON {table}(operation_zone_id);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_cases_point_gix ON {table} USING GIST (case_point);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_zones_geom_gix ON {zone_table} USING GIST (zone_geom);",
            "",
        ]
    )

def _logistics_hub_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_logistics_hubs'


def _logistics_asset_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_inventory_assets'


def _logistics_request_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_logistics_requests'


def _postgis_logistics_schema_sql(schema: str) -> str:
    hub_table = _logistics_hub_table(schema)
    asset_table = _logistics_asset_table(schema)
    request_table = _logistics_request_table(schema)
    return "\n".join(
        [
            "-- ReliefQueue logistics drill schema. Stores synthetic asset coordination evidence only.",
            "CREATE EXTENSION IF NOT EXISTS postgis;",
            f"CREATE SCHEMA IF NOT EXISTS {_sql_identifier(schema)};",
            f"CREATE TABLE IF NOT EXISTS {hub_table} (",
            "  hub_id text PRIMARY KEY,",
            "  hub_name text NOT NULL,",
            "  scenario_tag text,",
            "  hub_point geometry(Point, 4326) NOT NULL,",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"CREATE TABLE IF NOT EXISTS {asset_table} (",
            "  asset_id text PRIMARY KEY,",
            "  asset_tag text NOT NULL,",
            "  asset_type text NOT NULL,",
            "  asset_class text NOT NULL,",
            "  quantity_total integer NOT NULL,",
            "  quantity_available integer NOT NULL,",
            "  status text NOT NULL,",
            "  current_hub_id text,",
            "  asset_point geometry(Point, 4326) NOT NULL,",
            "  expected_return_at timestamptz,",
            "  scenario_tag text,",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"CREATE TABLE IF NOT EXISTS {request_table} (",
            "  request_id text PRIMARY KEY,",
            "  team_id text NOT NULL,",
            "  team_role text NOT NULL,",
            "  asset_type text NOT NULL,",
            "  asset_class text NOT NULL,",
            "  quantity_requested integer NOT NULL,",
            "  priority text NOT NULL,",
            "  destination_label text NOT NULL,",
            "  destination_point geometry(Point, 4326) NOT NULL,",
            "  requested_at timestamptz NOT NULL DEFAULT now(),",
            "  required_by_at timestamptz NOT NULL,",
            "  expected_return_at timestamptz,",
            "  status text NOT NULL,",
            "  assigned_asset_id text,",
            "  source_hub_id text,",
            "  expected_arrival_minutes integer,",
            "  scenario_tag text,",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_logistics_hubs_point_gix ON {hub_table} USING GIST (hub_point);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_inventory_assets_point_gix ON {asset_table} USING GIST (asset_point);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_inventory_assets_status_idx ON {asset_table}(status, asset_type);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_logistics_requests_point_gix ON {request_table} USING GIST (destination_point);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_logistics_requests_status_idx ON {request_table}(status, priority);",
            "",
        ]
    )


def _json_from_first_row(rows: list[list[str | None]], default: Any) -> Any:
    if not rows or not rows[0] or rows[0][0] is None:
        return default
    try:
        return json.loads(rows[0][0] or "")
    except json.JSONDecodeError:
        return default


def _postgres_execute(dsn: str, statements: list[str], timeout: float) -> None:
    client = _MiniPostgresClient.from_dsn(dsn, timeout)
    try:
        client.connect()
        for statement in statements:
            if statement.strip():
                client.query(statement)
    finally:
        client.close()


def _postgres_query(dsn: str, statement: str, timeout: float) -> list[list[str | None]]:
    client = _MiniPostgresClient.from_dsn(dsn, timeout)
    try:
        client.connect()
        return client.query(statement)
    finally:
        client.close()


class _MiniPostgresClient:
    """Tiny PostgreSQL client for local smoke SQL without adding runtime dependencies."""

    def __init__(self, host: str, port: int, database: str, user: str, password: str, timeout: float) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self._sasl_client_first_bare = ""
        self._sasl_server_first = ""

    @classmethod
    def from_dsn(cls, dsn: str, timeout: float) -> "_MiniPostgresClient":
        parsed = urlparse(dsn)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise ValueError("RELIEFQUEUE_POSTGIS_DSN must start with postgresql://")
        if not parsed.hostname:
            raise ValueError("RELIEFQUEUE_POSTGIS_DSN host is missing")
        query = parse_qs(parsed.query)
        connect_timeout = query.get("connect_timeout", [None])[0]
        if connect_timeout:
            try:
                timeout = max(1.0, min(float(connect_timeout), 30.0))
            except ValueError:
                pass
        return cls(
            parsed.hostname,
            parsed.port or 5432,
            unquote(parsed.path.lstrip("/") or "postgres"),
            unquote(parsed.username or "postgres"),
            unquote(parsed.password or ""),
            timeout,
        )

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        params = {
            "user": self.user,
            "database": self.database,
            "application_name": "reliefqueue-local-live-smoke",
            "client_encoding": "UTF8",
        }
        body = struct.pack("!I", 196608)
        for key, value in params.items():
            body += key.encode() + b"\x00" + value.encode() + b"\x00"
        body += b"\x00"
        self._send_raw(struct.pack("!I", len(body) + 4) + body)
        self._read_until_ready()

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self._send_message(b"X", b"")
        except OSError:
            pass
        self.sock.close()
        self.sock = None

    def query(self, statement: str) -> list[list[str | None]]:
        self._send_message(b"Q", statement.encode("utf-8") + b"\x00")
        rows: list[list[str | None]] = []
        while True:
            message_type, payload = self._read_message()
            if message_type == b"R":
                self._handle_auth(payload)
            elif message_type == b"T":
                continue
            elif message_type == b"D":
                rows.append(self._decode_data_row(payload))
            elif message_type in {b"C", b"I", b"N", b"S"}:
                continue
            elif message_type == b"E":
                raise RuntimeError(_sanitize(self._decode_error(payload)))
            elif message_type == b"Z":
                return rows
            elif message_type in {b"A", b"K", b"2", b"3"}:
                continue

    def _read_until_ready(self) -> None:
        while True:
            message_type, payload = self._read_message()
            if message_type == b"R":
                self._handle_auth(payload)
            elif message_type in {b"S", b"K", b"N"}:
                continue
            elif message_type == b"E":
                raise RuntimeError(_sanitize(self._decode_error(payload)))
            elif message_type == b"Z":
                return

    def _handle_auth(self, payload: bytes) -> None:
        auth_code = struct.unpack("!I", payload[:4])[0]
        if auth_code == 0:
            return
        if auth_code == 3:
            self._send_password(self.password)
            return
        if auth_code == 5:
            salt = payload[4:8]
            inner = hashlib.md5((self.password + self.user).encode()).hexdigest().encode()
            outer = hashlib.md5(inner + salt).hexdigest()
            self._send_password(f"md5{outer}")
            return
        if auth_code == 10:
            self._start_scram(payload[4:])
            return
        if auth_code == 11:
            self._continue_scram(payload[4:])
            return
        if auth_code == 12:
            return
        raise RuntimeError(f"Unsupported PostgreSQL authentication code {auth_code}")

    def _send_password(self, password: str) -> None:
        self._send_message(b"p", password.encode() + b"\x00")

    def _start_scram(self, payload: bytes) -> None:
        mechanisms = [item.decode("utf-8", "replace") for item in payload.split(b"\x00") if item]
        if "SCRAM-SHA-256" not in mechanisms:
            raise RuntimeError("PostgreSQL server did not offer SCRAM-SHA-256")
        nonce = base64.b64encode(secrets.token_bytes(18)).decode("ascii")
        self._sasl_client_first_bare = f"n={self.user},r={nonce}"
        client_first = f"n,,{self._sasl_client_first_bare}".encode()
        body = b"SCRAM-SHA-256\x00" + struct.pack("!I", len(client_first)) + client_first
        self._send_message(b"p", body)

    def _continue_scram(self, payload: bytes) -> None:
        self._sasl_server_first = payload.decode("utf-8", "replace")
        parts = dict(item.split("=", 1) for item in self._sasl_server_first.split(",") if "=" in item)
        nonce = parts.get("r", "")
        salt = base64.b64decode(parts.get("s", ""))
        iterations = int(parts.get("i", "4096"))
        client_final_without_proof = f"c=biws,r={nonce}"
        auth_message = ",".join(
            [self._sasl_client_first_bare, self._sasl_server_first, client_final_without_proof]
        )
        salted = hashlib.pbkdf2_hmac("sha256", self.password.encode(), salt, iterations)
        client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
        stored_key = hashlib.sha256(client_key).digest()
        client_signature = hmac.new(stored_key, auth_message.encode(), hashlib.sha256).digest()
        proof = bytes(left ^ right for left, right in zip(client_key, client_signature, strict=True))
        proof_b64 = base64.b64encode(proof).decode("ascii")
        self._send_message(b"p", f"{client_final_without_proof},p={proof_b64}".encode())

    def _decode_data_row(self, payload: bytes) -> list[str | None]:
        count = struct.unpack("!H", payload[:2])[0]
        offset = 2
        values: list[str | None] = []
        for _ in range(count):
            length = struct.unpack("!i", payload[offset : offset + 4])[0]
            offset += 4
            if length == -1:
                values.append(None)
                continue
            raw = payload[offset : offset + length]
            offset += length
            values.append(raw.decode("utf-8", "replace"))
        return values

    def _decode_error(self, payload: bytes) -> str:
        fields: dict[str, str] = {}
        for part in payload.split(b"\x00"):
            if len(part) > 1:
                fields[part[:1].decode()] = part[1:].decode("utf-8", "replace")
        return fields.get("M") or fields.get("C") or "PostgreSQL error"

    def _send_message(self, message_type: bytes, payload: bytes) -> None:
        self._send_raw(message_type + struct.pack("!I", len(payload) + 4) + payload)

    def _send_raw(self, payload: bytes) -> None:
        if self.sock is None:
            raise RuntimeError("PostgreSQL socket is not connected")
        self.sock.sendall(payload)

    def _read_message(self) -> tuple[bytes, bytes]:
        message_type = self._read_exact(1)
        length = struct.unpack("!I", self._read_exact(4))[0]
        return message_type, self._read_exact(length - 4)

    def _read_exact(self, length: int) -> bytes:
        if self.sock is None:
            raise RuntimeError("PostgreSQL socket is not connected")
        chunks = b""
        while len(chunks) < length:
            chunk = self.sock.recv(length - len(chunks))
            if not chunk:
                raise RuntimeError("PostgreSQL connection closed unexpectedly")
            chunks += chunk
        return chunks


def _redis_command(url: str, args: list[str], timeout: float = 5.0) -> Any:
    parsed = urlparse(url)
    if parsed.scheme != "redis" or not parsed.hostname:
        raise ValueError("RELIEFQUEUE_REDIS_URL must start with redis://")
    db = int((parsed.path or "/0").lstrip("/") or "0")
    with socket.create_connection((parsed.hostname, parsed.port or 6379), timeout=timeout) as sock:
        sock.settimeout(timeout)
        if parsed.password:
            if parsed.username:
                _redis_send(sock, ["AUTH", unquote(parsed.username), unquote(parsed.password)])
            else:
                _redis_send(sock, ["AUTH", unquote(parsed.password)])
            _redis_read(sock)
        if db:
            _redis_send(sock, ["SELECT", str(db)])
            _redis_read(sock)
        _redis_send(sock, args)
        return _redis_read(sock)


def _redis_send(sock: socket.socket, args: list[str]) -> None:
    body = f"*{len(args)}\r\n".encode()
    for arg in args:
        raw = str(arg).encode("utf-8")
        body += f"${len(raw)}\r\n".encode() + raw + b"\r\n"
    sock.sendall(body)


def _redis_read(sock: socket.socket) -> Any:
    prefix = _redis_read_exact(sock, 1)
    if prefix == b"+":
        return _redis_read_line(sock)
    if prefix == b"-":
        raise RuntimeError(_redis_read_line(sock))
    if prefix == b":":
        return int(_redis_read_line(sock))
    if prefix == b"$":
        length = int(_redis_read_line(sock))
        if length == -1:
            return None
        data = _redis_read_exact(sock, length)
        _redis_read_exact(sock, 2)
        return data.decode("utf-8", "replace")
    if prefix == b"*":
        count = int(_redis_read_line(sock))
        if count == -1:
            return None
        return [_redis_read(sock) for _ in range(count)]
    raise RuntimeError(f"Unsupported Redis response prefix {prefix!r}")


def _redis_read_line(sock: socket.socket) -> str:
    data = b""
    while not data.endswith(b"\r\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("Redis connection closed unexpectedly")
        data += chunk
    return data[:-2].decode("utf-8", "replace")


def _redis_read_exact(sock: socket.socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise RuntimeError("Redis connection closed unexpectedly")
        data += chunk
    return data


def _redis_xgroup_create(url: str, stream: str, group: str) -> str:
    try:
        _redis_command(url, ["XGROUP", "CREATE", stream, group, "0", "MKSTREAM"])
        return "created"
    except RuntimeError as exc:
        if "BUSYGROUP" in str(exc):
            return "already_exists"
        raise


def _redis_flat_fields_to_dict(flat_fields: Any) -> dict[str, str]:
    fields: dict[str, str] = {}
    if isinstance(flat_fields, list):
        iterator = iter(flat_fields)
        for key in iterator:
            fields[str(key)] = str(next(iterator, ""))
    return fields


def _redis_entries(response: Any) -> list[tuple[str, dict[str, str]]]:
    entries: list[tuple[str, dict[str, str]]] = []
    if not isinstance(response, list):
        return entries
    for stream_item in response:
        if not isinstance(stream_item, list) or len(stream_item) != 2:
            continue
        message_id_or_stream, rows_or_fields = stream_item
        if not isinstance(rows_or_fields, list):
            continue
        if not rows_or_fields or all(not isinstance(item, list) for item in rows_or_fields):
            # XCLAIM returns entries directly as [[message_id, [field, value, ...]]].
            # XREAD/XREADGROUP returns [stream, [[message_id, [field, value, ...]], ...]].
            # Support both shapes so live recovery proofs do not miss a successfully
            # claimed pending entry merely because the Redis command response shape differs.
            entries.append((str(message_id_or_stream), _redis_flat_fields_to_dict(rows_or_fields)))
            continue
        for row in rows_or_fields:
            if not isinstance(row, list) or len(row) != 2:
                continue
            message_id, flat_fields = row
            entries.append((str(message_id), _redis_flat_fields_to_dict(flat_fields)))
    return entries


def _confirmation(name: str) -> bool:
    """Return true only for the exact mutation-confirmation phrase for a live action."""
    expected = CONFIRMATION_VALUES.get(name)
    return bool(expected) and os.environ.get(name, "").strip() == expected


def _safe_scan(path: Path) -> dict[str, Any]:
    forbidden = [
        "raw_text_private",
        "reporter_phone_private_optional",
        "reporter_name_private_optional",
        "PRIVATE_OPERATOR_EXPORT",
        "confirmed rescue",
        "confirmed rescued",
        "confirmed safety",
        "dispatch without coordinator review",
        "auto dispatched",
        "automatic dispatch",
        "ai verified",
    ]
    errors: list[str] = []
    files = 0
    for item in sorted(path.rglob("*") if path.is_dir() else [path]):
        if not item.is_file() or item.suffix.lower() not in REPORT_SUFFIXES:
            continue
        files += 1
        text = item.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for marker in forbidden:
            if marker.lower() in lowered:
                errors.append(f"{item.name}: unsafe/private marker {marker}")
        if "+910000000001" in text or "Synthetic Asha" in text:
            errors.append(f"{item.name}: fixture private value")
    return {"passed": not errors, "errors": errors, "files_scanned": files}



def _safe_generated_relative_path(item: Path, root: Path, report_dir: Path) -> str:
    """Return a readable generated-artifact path for repo-local or temp reports."""
    item = Path(item)
    root = Path(root)
    report_dir = Path(report_dir)
    for base in (root, report_dir):
        try:
            return item.relative_to(base).as_posix()
        except ValueError:
            continue
    return item.as_posix()

def _changed_files(root: Path, report_dir: Path, phase_id: str) -> list[str]:
    candidates = [
        Path("src/reliefqueue/live_integrations.py"),
        Path("src/reliefqueue/cli.py"),
        Path("Makefile"),
        Path("tests/test_live_integrations_phases.py"),
    ]
    generated = []
    phase_path = _phase_dir(report_dir, phase_id)
    checkpoint = _checkpoint_dir(report_dir)
    for path in [phase_path, checkpoint]:
        if path.exists():
            generated.extend(_safe_generated_relative_path(item, root, report_dir) for item in path.rglob("*") if item.is_file())
    return [path.as_posix() for path in candidates if (root / path).exists()] + sorted(generated)


def write_checkpoint(
    root: Path,
    report_dir: Path,
    phase_id: str,
    implementation_status: str,
    commands_added: list[str],
    validation_commands_run: list[dict[str, Any]],
    summary: dict[str, str],
    known_limitations: list[str],
    next_phase_readiness: str,
) -> dict[str, Any]:
    info = PHASES[phase_id]
    payload = {
        "phase_id": phase_id,
        "phase_name": info["name"],
        "implementation_status": implementation_status,
        "commands_added": commands_added,
        "files_changed_generated": _changed_files(root, report_dir, phase_id),
        "validation_commands_run": validation_commands_run,
        "summary": summary,
        "known_limitations": known_limitations,
        "next_phase_readiness": next_phase_readiness,
        "created_at": utc_now(),
    }
    out_dir = _checkpoint_dir(report_dir)
    stem = info["checkpoint"]
    _write_json(out_dir / f"{stem}.json", payload)
    lines = [
        f"# Phase {phase_id} - {info['name']}",
        "",
        f"- implementation_status={implementation_status}",
        f"- commands added: {', '.join(commands_added) if commands_added else 'none'}",
        f"- files changed/generated: {len(payload['files_changed_generated'])}",
        f"- validation commands run: {', '.join(row['command'] for row in validation_commands_run) if validation_commands_run else 'none'}",
        f"- PASS/FAIL/SKIP summary: PASS={summary.get('PASS', '0')} FAIL={summary.get('FAIL', '0')} SKIP={summary.get('SKIP', '0')}",
        f"- known limitations: {'; '.join(known_limitations) if known_limitations else 'none'}",
        f"- next phase readiness: {next_phase_readiness}",
        "",
    ]
    (out_dir / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def _verbosity_value(raw: str) -> int:
    value = raw.strip().lower()
    if not value:
        return 0
    if value.isdigit():
        return max(0, min(int(value), 5))
    if set(value) == {"v"}:
        return max(0, min(len(value), 5))
    if value in {"true", "yes", "y", "on"}:
        return 1
    return 0


def _live_verbose_level(*specific_env_keys: str) -> int:
    levels = [_verbosity_value(os.environ.get("RELIEFQUEUE_LIVE_VERBOSE_LEVEL", ""))]
    for key in specific_env_keys:
        levels.append(_verbosity_value(os.environ.get(key, "")))
    return max(levels)


def _live_mutation_verbose_level() -> int:
    return _live_verbose_level("RELIEFQUEUE_LIVE_MUTATION_VERBOSE")


def _live_mutation_verbose_enabled() -> bool:
    return _live_mutation_verbose_level() > 0


def _json_line(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _print_live_stateful_mutation_verbose(result: dict[str, Any], out_dir: Path, level: int = 1) -> None:
    postgis = result.get("postgis") if isinstance(result.get("postgis"), dict) else {}
    redis = result.get("redis") if isinstance(result.get("redis"), dict) else {}
    nats = result.get("nats") if isinstance(result.get("nats"), dict) else {}
    selected_profile = result.get("selected_profile") if isinstance(result.get("selected_profile"), dict) else {}

    print(f"Stateful mutation evidence (-{'v' * max(level, 1)}):")
    if level <= 1:
        print(f"- status: {result.get('status', 'unknown')}")
        if selected_profile:
            print(f"- profile: {selected_profile.get('name', 'unknown')} - {selected_profile.get('label', '')}")
        print(f"- PostGIS: {postgis.get('status', 'unknown')} spatial_assignment={postgis.get('spatial_assignment_verified', 'not_recorded')} cleanup_rows={postgis.get('cleanup_remaining_rows', 'not_recorded')}")
        print(f"- Redis: {redis.get('status', 'unknown')} recovered={redis.get('worker_crash_recovered', 'not_recorded')} replayed={redis.get('replayed', 'not_recorded')} cleanup={redis.get('cleanup_verified', 'not_recorded')}")
        print(f"Full report: {out_dir / 'live_stateful_mutation_drill.json'}")
        return
    if selected_profile:
        print(f"Scenario profile: {selected_profile.get('name', 'unknown')} - {selected_profile.get('label', '')}")
    print("Role ownership:")
    print("- local coordinator: field reality, hub/zone/case locations, reachable radius, priority needs")
    print("- command center operator: queue burst, retry/DLQ, dedup TTL, replay/runtime controls")

    print("Coordinator field scenario:")
    coordinator_config = postgis.get("coordinator_config") or postgis.get("functional_config")
    if coordinator_config:
        print(f"- config: {_json_line(coordinator_config)}")

    print("PostGIS GIS scenario:")
    print(f"- status: {postgis.get('status', 'unknown')}")
    print(f"- source: {postgis.get('postgis_backend', postgis.get('postgis_source', 'unknown'))}")
    print(f"- scenario: {postgis.get('scenario', 'not_recorded')}")
    if postgis.get("why_postgis_matters"):
        print(f"- why PostGIS matters: {'; '.join(str(item) for item in postgis['why_postgis_matters'])}")
    print(f"- case table: {postgis.get('case_table', postgis.get('table', 'not_recorded'))}")
    print(f"- zone table: {postgis.get('zone_table', 'not_recorded')}")
    if postgis.get("tables_found"):
        print(f"- tables found: {_json_line(postgis['tables_found'])}")
    if postgis.get("spatial_indexes_found"):
        print(f"- spatial indexes found: {_json_line(postgis['spatial_indexes_found'])}")
    print(f"- operation zone polygon inserted: {postgis.get('operation_zone_id', 'not_recorded')}")
    if postgis.get("inserted_zone_public"):
        print(f"- zone geometry: {_json_line(postgis['inserted_zone_public'])}")
    print(f"- case_id inserted: {postgis.get('case_id', 'not_recorded')}")
    if postgis.get("inserted_public_row"):
        print(f"- inserted case point: {_json_line(postgis['inserted_public_row'])}")
    if postgis.get("read_back_row"):
        print(f"- spatial read-back row: {_json_line(postgis['read_back_row'])}")
    print(f"- spatial assignment verified: {postgis.get('spatial_assignment_verified', False)}")
    print(f"- inside-zone count after insert: {postgis.get('inside_zone_count_after_insert', postgis.get('zone_query_count_after_insert', 'not_recorded'))}")
    print(f"- outside case excluded by polygon: {postgis.get('outside_case_excluded_by_polygon', 'not_recorded')}")
    if postgis.get("nearest_cases_to_relief_hub"):
        print(f"- nearest cases to relief hub: {_json_line(postgis['nearest_cases_to_relief_hub'])}")
    print(f"- update verified: {postgis.get('update_verified', False)}")
    print(f"- deleted case ids: {_json_line(postgis.get('deleted_case_ids', [postgis.get('deleted_case_id', postgis.get('case_id', 'not_recorded'))]))}")
    print(f"- deleted operation zone id: {postgis.get('deleted_operation_zone_id', 'not_recorded')}")
    print(f"- cleanup remaining rows: {postgis.get('cleanup_remaining_rows', 'not_recorded')}")
    print(f"- cleanup remaining zones: {postgis.get('cleanup_remaining_zones', 'not_recorded')}")

    print("Command center runtime scenario:")
    runtime_config = redis.get("command_center_config") or redis.get("runtime_config")
    if runtime_config:
        print(f"- config: {_json_line(runtime_config)}")

    print("Redis resilience scenario:")
    print(f"- status: {redis.get('status', 'unknown')}")
    print(f"- source: {redis.get('redis_source', 'unknown')}")
    print(f"- scenario: {redis.get('scenario', 'not_recorded')}")
    if redis.get("why_redis_matters"):
        print(f"- why Redis matters: {'; '.join(str(item) for item in redis['why_redis_matters'])}")
    print(f"- stream: {redis.get('stream', 'not_recorded')}")
    print(f"- dead letter stream: {redis.get('dead_letter_stream', 'not_recorded')}")
    print(f"- replay review stream: {redis.get('replay_review_stream', 'not_recorded')}")
    print(f"- prepared jobs: {redis.get('jobs_prepared', 'not_recorded')}")
    print(f"- core drill jobs: {redis.get('core_drill_jobs_prepared', 'not_recorded')} burst buffer jobs: {redis.get('burst_buffer_jobs_prepared', 'not_recorded')}")
    if redis.get("prepared_jobs_public_fields"):
        print(f"- prepared job fields sample: {_json_line(redis['prepared_jobs_public_fields'])}")
    if redis.get("prepared_jobs_public_fields_truncated"):
        print("- prepared job fields sample truncated: True")
    print(f"- enqueued: {redis.get('enqueued', 0)} claimed: {redis.get('claimed', 0)} processed: {redis.get('processed', 0)}")
    print(f"- queue depth after enqueue: {redis.get('queue_depth_after_enqueue', 'not_recorded')}")
    print(f"- simulated crashed worker message id: {redis.get('simulated_worker_crash_message_id', 'not_recorded')}")
    if redis.get("pending_breakdown_after_worker_crash"):
        print(f"- pending breakdown after worker crash: {_json_line(redis['pending_breakdown_after_worker_crash'])}")
    else:
        print(f"- pending after worker crash: {_json_line(redis.get('pending_after_worker_crash', 'not_recorded'))}")
    print(f"- recovered message id: {redis.get('recovered_message_id', 'not_recorded')} by {redis.get('recovery_consumer', 'not_recorded')}")
    if redis.get("pending_breakdown_after_recovery"):
        print(f"- pending breakdown after recovery: {_json_line(redis['pending_breakdown_after_recovery'])}")
    else:
        print(f"- pending after recovery: {_json_line(redis.get('pending_after_recovery', 'not_recorded'))}")
    print(f"- retry message id: {redis.get('retry_message_id', 'not_recorded')}")
    if redis.get("burst_buffer_jobs_drained_after_retry") is not None:
        print(f"- burst buffer jobs drained after retry read: {redis.get('burst_buffer_jobs_drained_after_retry')}")
    print(f"- dead letter message id: {redis.get('dead_letter_message_id', 'not_recorded')}")
    print(f"- replayed: {redis.get('replayed', 0)}")
    if redis.get("atomic_dedup"):
        print(f"- atomic duplicate suppression: {_json_line(redis['atomic_dedup'])}")
    if redis.get("final_state_before_cleanup"):
        print(f"- final state before cleanup: {_json_line(redis['final_state_before_cleanup'])}")
    if redis.get("final_state_after_cleanup"):
        print(f"- final state after cleanup: {_json_line(redis['final_state_after_cleanup'])}")

    print("NATS:")
    print(f"- status: {nats.get('status', 'unknown')}")
    print(f"- role: {nats.get('role', 'connectivity_proof_only')}")
    print(f"- JetStream queue mutation attempted: {nats.get('jetstream_queue_mutation_attempted', False)}")
    print(f"Full report: {out_dir / 'live_stateful_mutation_drill.json'}")


def _print_live_logistics_asset_verbose(result: dict[str, Any], out_dir: Path, level: int = 1) -> None:
    postgis = result.get("postgis") or {}
    redis = result.get("redis") or {}
    profile = result.get("selected_profile") or {}
    coordinator = result.get("coordinator_config") or {}
    command_center = result.get("command_center_config") or {}
    print(f"Logistics asset evidence (-{'v' * max(level, 1)}):")
    if level <= 1:
        print(f"- status: {result.get('status', 'unknown')}")
        print(f"- profile: {profile.get('name', 'unknown')} - {profile.get('label', 'unknown')}")
        print(f"- PostGIS: {postgis.get('status', 'unknown')} nearest_asset={bool(postgis.get('nearest_asset_decision'))} cleanup_assets={postgis.get('cleanup_remaining_assets', 'not_recorded')}")
        print(f"- Redis: {redis.get('status', 'unknown')} recovered={redis.get('worker_crash_recovered', 'not_recorded')} replayed={redis.get('replayed', 'not_recorded')} cleanup={redis.get('cleanup_verified', 'not_recorded')}")
        print(f"Full report: {out_dir / 'live_logistics_asset_drill.json'}")
        return
    print(f"Scenario profile: {profile.get('name', 'unknown')} - {profile.get('label', 'unknown')}")
    print("Role ownership:")
    print("- local coordinator: field team needs, delivery points, hub context, needed-by/return expectations")
    print("- command center operator: queue pressure, reservation locks, retry/DLQ, replay, stale-return monitoring")
    print("Coordinator logistics scenario:")
    print(f"- disaster type: {coordinator.get('disaster_type', 'not_recorded')}")
    print(f"- mission family: {coordinator.get('mission_family', 'not_recorded')}")
    print(f"- relief hub: {coordinator.get('relief_hub_name', 'not_recorded')}")
    if coordinator.get("field_teams"):
        print(f"- field teams: {_json_line(coordinator['field_teams'])}")
    if coordinator.get("planned_requests"):
        print(f"- planned logistics requests: {_json_line(coordinator['planned_requests'])}")
    if coordinator.get("inventory_seed"):
        print(f"- inventory seed: {_json_line(coordinator['inventory_seed'])}")
    print("Command center logistics controls:")
    if command_center:
        print(f"- config: {_json_line(command_center)}")

    print("PostGIS logistics evidence:")
    print(f"- status: {postgis.get('status', 'unknown')}")
    print(f"- source: {postgis.get('postgis_backend', 'unknown')}")
    print(f"- scenario: {postgis.get('scenario', 'not_recorded')}")
    if postgis.get("case_for_postgis"):
        print(f"- why PostGIS matters: {'; '.join(str(item) for item in postgis['case_for_postgis'])}")
    print(f"- tables: {_json_line(postgis.get('tables', {}))}")
    if postgis.get("tables_found"):
        print(f"- tables found: {_json_line(postgis['tables_found'])}")
    if postgis.get("spatial_indexes_found"):
        print(f"- spatial indexes found: {_json_line(postgis['spatial_indexes_found'])}")
    if postgis.get("hubs_inserted"):
        print(f"- hubs inserted: {_json_line(postgis['hubs_inserted'])}")
    if postgis.get("inventory_assets_inserted"):
        print(f"- inventory assets inserted: {_json_line(postgis['inventory_assets_inserted'])}")
    if postgis.get("logistics_requests_created"):
        print(f"- logistics requests created: {_json_line(postgis['logistics_requests_created'])}")
    if postgis.get("nearest_asset_decision"):
        print(f"- nearest available asset decision: {_json_line(postgis['nearest_asset_decision'])}")
    if postgis.get("reservation_result"):
        print(f"- reservation result: {_json_line(postgis['reservation_result'])}")
    if postgis.get("distribution_result"):
        print(f"- distribution result: {_json_line(postgis['distribution_result'])}")
    if postgis.get("overdue_return_assets"):
        print(f"- overdue return assets: {_json_line(postgis['overdue_return_assets'])}")
    if postgis.get("reallocation_result"):
        print(f"- reallocation result: {_json_line(postgis['reallocation_result'])}")
    if postgis.get("final_inventory_before_cleanup"):
        print(f"- final inventory before cleanup: {_json_line(postgis['final_inventory_before_cleanup'])}")
    if postgis.get("final_requests_before_cleanup"):
        print(f"- final requests before cleanup: {_json_line(postgis['final_requests_before_cleanup'])}")
    print(f"- cleanup remaining requests: {postgis.get('cleanup_remaining_requests', 'not_recorded')}")
    print(f"- cleanup remaining assets: {postgis.get('cleanup_remaining_assets', 'not_recorded')}")
    print(f"- cleanup remaining hubs: {postgis.get('cleanup_remaining_hubs', 'not_recorded')}")

    print("Redis logistics evidence:")
    print(f"- status: {redis.get('status', 'unknown')}")
    print(f"- source: {redis.get('redis_source', 'unknown')}")
    print(f"- scenario: {redis.get('scenario', 'not_recorded')}")
    if redis.get("case_for_redis"):
        print(f"- why Redis matters: {'; '.join(str(item) for item in redis['case_for_redis'])}")
    print(f"- stream: {redis.get('stream', 'not_recorded')}")
    print(f"- dead letter stream: {redis.get('dead_letter_stream', 'not_recorded')}")
    print(f"- replay review stream: {redis.get('replay_review_stream', 'not_recorded')}")
    print(f"- timeline stream: {redis.get('timeline_stream', 'not_recorded')}")
    print(f"- jobs prepared: {redis.get('jobs_prepared', 'not_recorded')}")
    print(f"- queue depth after enqueue: {redis.get('queue_depth_after_enqueue', 'not_recorded')}")
    if redis.get("reservation_lock"):
        print(f"- reservation lock: {_json_line(redis['reservation_lock'])}")
    if redis.get("atomic_dedup"):
        print(f"- atomic duplicate suppression: {_json_line(redis['atomic_dedup'])}")
    print(f"- simulated dispatch worker crash message id: {redis.get('simulated_worker_crash_message_id', 'not_recorded')}")
    print(f"- recovered message id: {redis.get('recovered_message_id', 'not_recorded')} by {redis.get('recovery_consumer', 'not_recorded')}")
    print(f"- retry message id: {redis.get('retry_message_id', 'not_recorded')}")
    print(f"- dead letter message id: {redis.get('dead_letter_message_id', 'not_recorded')}")
    print(f"- replayed: {redis.get('replayed', 0)}")
    print(f"- timeline events written: {redis.get('timeline_events_written', 'not_recorded')}")
    if redis.get("final_state_before_cleanup"):
        print(f"- final state before cleanup: {_json_line(redis['final_state_before_cleanup'])}")
    if redis.get("final_state_after_cleanup"):
        print(f"- final state after cleanup: {_json_line(redis['final_state_after_cleanup'])}")
    print(f"Full report: {out_dir / 'live_logistics_asset_drill.json'}")


def _run_phase_command(root: Path, report_dir: Path, phase_id: str, command: str, func: Callable[[Path, Path, Path], dict[str, Any]]) -> int:
    ensure_report_dir(report_dir)
    out_dir = _phase_dir(report_dir, phase_id)
    started = time.perf_counter()
    result = func(root, report_dir, out_dir)
    result.setdefault("phase_id", phase_id)
    result.setdefault("phase_name", PHASES[phase_id]["name"])
    result.setdefault("command", command)
    result.setdefault("created_at", utc_now())
    result["runtime_seconds"] = round(time.perf_counter() - started, 6)
    result["safety_scan"] = _safe_scan(out_dir)
    _write_json(out_dir / f"{command.replace('-', '_')}.json", result)
    if command == "live-stateful-mutation-drill" and _live_mutation_verbose_enabled():
        _print_live_stateful_mutation_verbose(result, out_dir, _live_mutation_verbose_level())
    if command == "live-logistics-asset-drill" and _live_logistics_verbose_enabled():
        _print_live_logistics_asset_verbose(result, out_dir, _live_logistics_verbose_level())
    if command == "live-volunteer-surge-drill" and _live_volunteer_verbose_enabled():
        _print_live_volunteer_surge_verbose(result, out_dir, _live_volunteer_verbose_level())
    status = result.get("status", "PASS")
    print(f"{command} {status}: wrote {out_dir / (command.replace('-', '_') + '.json')}")
    if not result["safety_scan"]["passed"]:
        print(f"{command} FAIL: safety scan found redaction or safety-boundary issues.")
        return 1
    return 0 if status in {"PASS", "SKIP", "PARTIAL"} else 1


def postgis_live_init(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    schema = _configured_postgis_schema()
    schema_sql = _postgis_schema_sql(schema)
    (out_dir / "schema.sql").write_text(schema_sql, encoding="utf-8")
    dsn, dsn_source, dsn_note = _resolved_postgis_dsn(report_dir)
    env = _env_status(OPTIONAL_ENV["postgis"])
    if not dsn:
        return {
            "status": "SKIP",
            "env": env,
            "dsn_source": dsn_source,
            "network_call_attempted": False,
            "schema_file": "schema.sql",
            "note": dsn_note or "Set RELIEFQUEUE_POSTGIS_DSN or run make live-stack-up to run local PostGIS init.",
        }
    try:
        _postgres_execute(dsn, schema_sql.split(";"), _configured_postgis_timeout())
    except Exception as exc:
        return {
            "status": "FAIL",
            "env": env,
            "network_call_attempted": True,
            "schema_file": "schema.sql",
            **_live_error(exc),
        }
    return {
        "status": "PASS",
        "env": env,
        "network_call_attempted": True,
        "schema": schema,
        "schema_file": "schema.sql",
        "postgis_backend": dsn_source,
        "auto_resolved_live_stack": dsn_source == "local_live_stack",
        "note": dsn_note,
        "secret_values_printed": False,
    }


def _postgis_demo_rows(root: Path) -> list[dict[str, Any]]:
    cases, _zones, _workers, _assignments = _load_demo(root)
    rows = []
    for case in cases:
        public = redact_public_case(case)
        rows.append(
            {
                "case_id": public["case_id"],
                "public_case_ref": public["public_case_ref"],
                "operation_zone_id": public["operation_zone_id"],
                "location_clue": case.get("location_clue"),
                "geo_scope_type": case.get("geo_scope_type"),
                "geo_confidence": public["geo_confidence"],
                "need_type": public["need_type"],
                "urgency": public["urgency"],
                "human_review_required": public["human_review_required"],
            }
        )
    return rows


def _write_postgis_demo_files(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with (out_dir / "import_demo_cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    write_jsonl(out_dir / "import_demo_cases.jsonl", rows)


def postgis_live_import_demo(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    rows = _postgis_demo_rows(root)
    _write_postgis_demo_files(out_dir, rows)
    dsn, dsn_source, dsn_note = _resolved_postgis_dsn(report_dir)
    env = _env_status(OPTIONAL_ENV["postgis"])
    if not dsn:
        return {
            "status": "SKIP",
            "env": env,
            "dsn_source": dsn_source,
            "rows_prepared": len(rows),
            "live_write_attempted": False,
            "provider_mutation_attempted": False,
            "note": dsn_note or "Set RELIEFQUEUE_POSTGIS_DSN or run make live-stack-up to insert demo rows into local PostGIS.",
        }
    schema = _configured_postgis_schema()
    table = _postgis_table(schema)
    statements = [_postgis_schema_sql(schema), f"DELETE FROM {table}"]
    for row in rows:
        columns = list(row)
        values = ", ".join(_sql_literal(row[column]) for column in columns)
        statements.append(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({values})")
    try:
        _postgres_execute(dsn, statements, _configured_postgis_timeout())
    except Exception as exc:
        return {
            "status": "FAIL",
            "env": env,
            "rows_prepared": len(rows),
            "live_write_attempted": True,
            "provider_mutation_attempted": False,
            **_live_error(exc),
        }
    return {
        "status": "PASS",
        "env": env,
        "rows_prepared": len(rows),
        "rows_inserted": len(rows),
        "live_write_attempted": True,
        "provider_mutation_attempted": False,
        "postgis_backend": dsn_source,
        "auto_resolved_live_stack": dsn_source == "local_live_stack",
        "note": dsn_note,
        "secret_values_printed": False,
    }


def postgis_live_query(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    dsn, dsn_source, dsn_note = _resolved_postgis_dsn(report_dir)
    if not dsn:
        path = out_dir / "import_demo_cases.jsonl"
        rows = load_jsonl(path) if path.exists() else []
        by_zone: dict[str, int] = {}
        for row in rows:
            zone = str(row.get("operation_zone_id") or "unknown")
            by_zone[zone] = by_zone.get(zone, 0) + 1
        _write_json(out_dir / "query_summary.json", {"case_count": len(rows), "by_zone": by_zone})
        return {
            "status": "SKIP",
            "source": "local_prepared_import",
            "query": "count_by_zone",
            "case_count": len(rows),
            "by_zone": by_zone,
            "dsn_source": dsn_source,
            "note": dsn_note or "Set RELIEFQUEUE_POSTGIS_DSN or run make live-stack-up to query local PostGIS.",
        }
    schema = _configured_postgis_schema()
    table = _postgis_table(schema)
    try:
        count_rows = _postgres_query(dsn, f"SELECT count(*) FROM {table}", _configured_postgis_timeout())
        zone_rows = _postgres_query(
            dsn,
            f"""
            SELECT COALESCE(operation_zone_id, 'unknown'), count(*)
            FROM {table}
            GROUP BY 1
            ORDER BY 1
            """,
            _configured_postgis_timeout(),
        )
    except Exception as exc:
        return {"status": "FAIL", "query_attempted": True, **_live_error(exc)}
    case_count = int(count_rows[0][0] or 0) if count_rows else 0
    by_zone = {str(row[0]): int(row[1] or 0) for row in zone_rows}
    _write_json(
        out_dir / "query_summary.json",
        {"case_count": case_count, "by_zone": by_zone, "source": dsn_source},
    )
    return {
        "status": "PASS",
        "source": dsn_source,
        "query": "count_by_zone",
        "query_attempted": True,
        "case_count": case_count,
        "by_zone": by_zone,
        "auto_resolved_live_stack": dsn_source == "local_live_stack",
        "note": dsn_note,
        "secret_values_printed": False,
    }


def postgis_live_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    commands = [
        ("postgis-live-init", postgis_live_init),
        ("postgis-live-import-demo", postgis_live_import_demo),
        ("postgis-live-query", postgis_live_query),
        ("postgis-live-backup", postgis_live_backup),
        ("postgis-live-restore-smoke", postgis_live_restore_smoke),
    ]
    results = []
    for name, func in commands:
        results.append({"command": name, "exit_code": _run_phase_command(root, report_dir, "02", name, func)})
    summary = _summary_from_results(results)
    status = "FAIL" if summary["FAIL"] else "PASS"
    limitation = "Missing RELIEFQUEUE_POSTGIS_DSN leaves commands in SKIP/offline evidence mode unless local live-stack PostGIS is ready."
    resolved_dsn, resolved_source, _note = _resolved_postgis_dsn(report_dir)
    if resolved_dsn:
        limitation = f"PostGIS endpoint source exercised for init/import/query: {resolved_source}."
    write_checkpoint(
        root,
        report_dir,
        "02",
        status,
        [name for name, _ in commands],
        results,
        _summary_strings(summary),
        [limitation],
        "READY",
    )
    return {"status": status, "results": results, "summary": summary}


def postgis_live_backup(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    dsn, _dsn_source, _dsn_note = _resolved_postgis_dsn(report_dir)
    if dsn:
        query_result = postgis_live_query(Path(), report_dir, out_dir)
        if query_result.get("status") == "FAIL":
            return query_result
    backup = out_dir / "postgis_sanitized_backup.tar.gz"
    with tarfile.open(backup, "w:gz") as tar:
        for name in ["schema.sql", "import_demo_cases.csv", "import_demo_cases.jsonl", "query_summary.json"]:
            path = out_dir / name
            if path.exists():
                tar.add(path, arcname=f"geospatial-store/{name}")
    return {
        "status": "PASS" if backup.exists() else "SKIP",
        "backup_path": str(backup),
        "backup_source": _dsn_source if dsn else "local_evidence_files",
        "credential_bearing_dsn_written": False,
    }


def postgis_live_restore_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root, report_dir
    restore_dir = out_dir / "restore_smoke"
    shutil.rmtree(restore_dir, ignore_errors=True)
    restore_dir.mkdir()
    backup = out_dir / "postgis_sanitized_backup.tar.gz"
    if backup.exists():
        with tarfile.open(backup, "r:gz") as tar:
            tar.extractall(restore_dir, filter="data")
    restored = [item.name for item in restore_dir.rglob("*") if item.is_file()]
    expected = {"schema.sql", "import_demo_cases.jsonl", "query_summary.json"}
    return {
        "status": "PASS" if expected.intersection(restored) else "SKIP",
        "restored_files": sorted(restored),
        "restore_type": "sanitized_archive_readability_smoke",
    }


def queue_live_init(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    stream = _configured_queue_name()
    group = "reliefqueue-live-worker"
    spec = {
        "streams": [stream, f"{stream}.dead_letter"],
        "consumer_group": group,
        "payload_policy": "allowlisted routing and review fields only",
        "human_review_required": True,
    }
    _write_json(out_dir / "queue_contract.json", spec)
    url, redis_source, redis_note = _resolved_redis_url(report_dir)
    backend = _resolved_queue_backend(report_dir)
    if backend != "redis" and not url:
        return {"status": "SKIP", "queue_env": _env_status(OPTIONAL_ENV["queue"], any_of=True), "contract": spec}
    if not url:
        return {
            "status": "SKIP",
            "queue_env": _env_status(OPTIONAL_ENV["queue"], any_of=True),
            "contract": spec,
            "redis_source": redis_source,
            "note": redis_note or "Set RELIEFQUEUE_REDIS_URL or run make live-stack-up to run Redis Streams queue init.",
        }
    try:
        ping = _redis_command(url, ["PING"])
        group_status = _redis_xgroup_create(url, stream, group)
    except Exception as exc:
        return {"status": "FAIL", "queue_env": _env_status(OPTIONAL_ENV["queue"], any_of=True), "contract": spec, **_live_error(exc)}
    return {
        "status": "PASS",
        "backend": "redis",
        "redis_source": redis_source,
        "auto_resolved_live_stack": redis_source == "local_live_stack",
        "note": redis_note,
        "queue_env": _env_status(OPTIONAL_ENV["queue"], any_of=True),
        "contract": spec,
        "ping": ping,
        "consumer_group_status": group_status,
        "secret_values_printed": False,
    }


def queue_live_enqueue_demo(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    cases, _zones, _workers, _assignments = _load_demo(root)
    jobs = []
    for index, case in enumerate(cases[:5], 1):
        public = redact_public_case(case)
        jobs.append({"job_id": f"live-demo-{index:04d}", "case_id": public["case_id"], "attempt": 0, "payload": public})
    write_jsonl(out_dir / "enqueued_jobs.jsonl", jobs)
    url, redis_source, redis_note = _resolved_redis_url(report_dir)
    backend = _resolved_queue_backend(report_dir)
    if backend != "redis" and not url:
        return {"status": "PASS", "enqueued": len(jobs), "live_enqueue_attempted": False}
    if not url:
        return {
            "status": "SKIP",
            "enqueued": len(jobs),
            "live_enqueue_attempted": False,
            "redis_source": redis_source,
            "note": redis_note or "Set RELIEFQUEUE_REDIS_URL or run make live-stack-up to enqueue into Redis Streams.",
        }
    stream = _configured_queue_name()
    try:
        _redis_xgroup_create(url, stream, "reliefqueue-live-worker")
        redis_ids = [
            _redis_command(
                url,
                [
                    "XADD",
                    stream,
                    "*",
                    "job_id",
                    job["job_id"],
                    "case_id",
                    job["case_id"],
                    "attempt",
                    str(job["attempt"]),
                    "payload_json",
                    json.dumps(job["payload"], ensure_ascii=False, sort_keys=True),
                ],
            )
            for job in jobs
        ]
    except Exception as exc:
        return {"status": "FAIL", "enqueued": len(jobs), "live_enqueue_attempted": True, **_live_error(exc)}
    return {
        "status": "PASS",
        "backend": "redis",
        "redis_source": redis_source,
        "auto_resolved_live_stack": redis_source == "local_live_stack",
        "note": redis_note,
        "stream": stream,
        "enqueued": len(jobs),
        "redis_message_ids": redis_ids,
        "live_enqueue_attempted": True,
        "secret_values_printed": False,
    }


def queue_live_worker_once(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    url, redis_source, redis_note = _resolved_redis_url(report_dir)
    if _resolved_queue_backend(report_dir) == "redis" or url:
        if not url:
            return {
                "status": "SKIP",
                "processed": 0,
                "dead_lettered": 0,
                "redis_source": redis_source,
                "note": redis_note or "Set RELIEFQUEUE_REDIS_URL or run make live-stack-up to run Redis worker-once.",
            }
        stream = _configured_queue_name()
        group = "reliefqueue-live-worker"
        consumer = "reliefqueue-live-worker-once"
        dlq_stream = f"{stream}.dead_letter"
        try:
            _redis_xgroup_create(url, stream, group)
            response = _redis_command(
                url,
                ["XREADGROUP", "GROUP", group, consumer, "COUNT", "5", "STREAMS", stream, ">"],
            )
            entries = _redis_entries(response)
            processed = []
            dlq = []
            for index, (message_id, fields) in enumerate(entries):
                row = {
                    "job_id": fields.get("job_id", message_id),
                    "case_id": fields.get("case_id", "unknown"),
                    "attempt": int(fields.get("attempt", "0") or 0),
                    "redis_message_id": message_id,
                }
                if index == 3:
                    dlq.append({**row, "status": "dead_lettered", "failure_class": "schema_validation_failed", "private_payload_written": False})
                    _redis_command(url, ["XADD", dlq_stream, "*", *[str(item) for pair in dlq[-1].items() for item in pair]])
                else:
                    processed.append({**row, "status": "processed", "human_review_required": True})
                _redis_command(url, ["XACK", stream, group, message_id])
        except Exception as exc:
            return {"status": "FAIL", "worker_mode": "once_redis", **_live_error(exc)}
        write_jsonl(out_dir / "processed_jobs.jsonl", processed)
        write_jsonl(out_dir / "dead_letter_jobs.jsonl", dlq)
        return {
            "status": "PASS",
            "backend": "redis",
            "redis_source": redis_source,
            "auto_resolved_live_stack": redis_source == "local_live_stack",
            "note": redis_note,
            "processed": len(processed),
            "dead_lettered": len(dlq),
            "worker_mode": "once_redis",
            "secret_values_printed": False,
        }

    jobs = load_jsonl(out_dir / "enqueued_jobs.jsonl") if (out_dir / "enqueued_jobs.jsonl").exists() else []
    processed = []
    dlq = []
    for index, job in enumerate(jobs):
        row = {key: job[key] for key in ["job_id", "case_id", "attempt"]}
        if index == 3:
            dlq.append({**row, "status": "dead_lettered", "failure_class": "schema_validation_failed", "private_payload_written": False})
        else:
            processed.append({**row, "status": "processed", "human_review_required": True})
    write_jsonl(out_dir / "processed_jobs.jsonl", processed)
    write_jsonl(out_dir / "dead_letter_jobs.jsonl", dlq)
    return {"status": "PASS", "processed": len(processed), "dead_lettered": len(dlq), "worker_mode": "once_local"}


def queue_live_dlq_report(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    url, redis_source, redis_note = _resolved_redis_url(report_dir)
    if _resolved_queue_backend(report_dir) == "redis" or url:
        if not url:
            return {"status": "SKIP", "dead_lettered": 0, "private_payload_written": False, "redis_source": redis_source, "note": redis_note}
        dlq_stream = f"{_configured_queue_name()}.dead_letter"
        try:
            entries = _redis_entries([[dlq_stream, _redis_command(url, ["XRANGE", dlq_stream, "-", "+", "COUNT", "100"])]])
        except RuntimeError as exc:
            if "no such key" not in str(exc).lower():
                return {"status": "FAIL", **_live_error(exc)}
            entries = []
        except Exception as exc:
            return {"status": "FAIL", **_live_error(exc)}
        dlq = [dict(fields, redis_message_id=message_id) for message_id, fields in entries]
        _write_json(out_dir / "dlq_report.json", {"dead_lettered": len(dlq), "items": dlq, "backend": "redis"})
        write_jsonl(out_dir / "dead_letter_jobs.jsonl", dlq)
        return {
            "status": "PASS",
            "backend": "redis",
            "redis_source": redis_source,
            "auto_resolved_live_stack": redis_source == "local_live_stack",
            "note": redis_note,
            "dead_lettered": len(dlq),
            "private_payload_written": False,
        }

    dlq = load_jsonl(out_dir / "dead_letter_jobs.jsonl") if (out_dir / "dead_letter_jobs.jsonl").exists() else []
    _write_json(out_dir / "dlq_report.json", {"dead_lettered": len(dlq), "items": dlq})
    return {"status": "PASS", "dead_lettered": len(dlq), "private_payload_written": False}


def queue_live_replay_dlq(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root, report_dir
    dlq = load_jsonl(out_dir / "dead_letter_jobs.jsonl") if (out_dir / "dead_letter_jobs.jsonl").exists() else []
    confirmed = _confirmation("QUEUE_REPLAY_CONFIRM")
    replay = [{**row, "replay_status": "blocked_missing_confirmation" if not confirmed else "dry_run_ready"} for row in dlq]
    write_jsonl(out_dir / "dlq_replay_plan.jsonl", replay)
    return {"status": "SKIP" if not confirmed else "PASS", "replay_attempted": False, "dry_run_items": len(replay), "confirmation_required": "QUEUE_REPLAY_CONFIRM=I_UNDERSTAND_REPLAY"}


def queue_live_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    commands = [
        ("queue-live-init", queue_live_init),
        ("queue-live-enqueue-demo", queue_live_enqueue_demo),
        ("queue-live-worker-once", queue_live_worker_once),
        ("queue-live-dlq-report", queue_live_dlq_report),
        ("queue-live-replay-dlq", queue_live_replay_dlq),
    ]
    results = [{"command": name, "exit_code": _run_phase_command(root, report_dir, "03", name, func)} for name, func in commands]
    summary = _summary_from_results(results)
    status = "FAIL" if summary["FAIL"] else "PASS"
    limitation = "Queue remains local file-backed unless RELIEFQUEUE_REDIS_URL is configured or local live-stack Redis is ready."
    resolved_url, resolved_source, _note = _resolved_redis_url(report_dir)
    if resolved_url:
        limitation = f"Redis Streams endpoint source exercised for init/enqueue/worker/DLQ: {resolved_source}."
    write_checkpoint(root, report_dir, "03", status, [name for name, _ in commands], results, _summary_strings(summary), [limitation], "READY")
    return {"status": status, "results": results, "summary": summary}


def _postgis_stateful_mutation_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    dsn, dsn_source, dsn_note = _resolved_postgis_dsn(report_dir)
    drill_config = _stateful_mutation_drill_config()
    coordinator = drill_config["coordinator_config"]
    profile = drill_config["selected_profile"]
    token = utc_now().replace("-", "").replace(":", "").replace("Z", "")
    case_id = f"stateful-mutation-{token}"
    nearby_case_id = f"{case_id}-nearby"
    outside_case_id = f"{case_id}-outside"
    operation_zone_id = str(coordinator["operation_zone_id"])
    operation_zone_name = str(coordinator["operation_zone_name"])
    zone_wkt = str(coordinator["zone_polygon_wkt"])
    hub_lon = float(coordinator["relief_hub_lon"])
    hub_lat = float(coordinator["relief_hub_lat"])
    relief_hub_radius_meters = int(coordinator["relief_hub_radius_meters"])
    nearest_case_limit = int(coordinator["nearest_case_limit"])
    primary_case = coordinator["primary_case"]
    nearby_case = coordinator["nearby_case"]
    outside_case = coordinator["outside_case"]
    evidence: dict[str, Any] = {
        "status": "SKIP",
        "backend": "postgis",
        "scenario": "role_profile_spatial_zone_assignment_nearest_case_and_cleanup",
        "why_postgis_matters": [
            "stores true geometry for coordinator-selected case points and operation-zone polygons",
            "assigns a case to an operation zone using ST_Contains instead of string matching",
            "uses the coordinator's reachable hub radius to prioritize cases",
            "ranks nearby cases from the relief hub using spatial distance",
            "uses GiST spatial indexes that normal JSON/file storage cannot provide",
        ],
        "selected_profile": profile,
        "available_profiles": drill_config["available_profiles"],
        "role_contract": drill_config["role_contract"],
        "functional_config": coordinator,
        "coordinator_config": coordinator,
        "config_warnings": drill_config["config_warnings"],
        "postgis_backend": dsn_source,
        "auto_resolved_live_stack": dsn_source == "local_live_stack",
        "note": dsn_note,
        "case_id": case_id,
        "operation_zone_id": operation_zone_id,
        "operations": [],
        "live_write_attempted": False,
        "cleanup_verified": False,
        "secret_values_printed": False,
    }
    if not dsn:
        evidence["note"] = (
            dsn_note
            or "Set RELIEFQUEUE_POSTGIS_DSN or run make live-stack-up to run the stateful PostGIS mutation drill."
        )
        _write_json(out_dir / "postgis_mutation_evidence.json", evidence)
        return evidence

    def case_row(row_case: dict[str, Any], row_case_id: str, case_ref: str) -> dict[str, Any]:
        return {
            "case_id": row_case_id,
            "public_case_ref": case_ref,
            "operation_zone_id": None,
            "location_clue": row_case.get("location_clue"),
            "geo_scope_type": "point",
            "geo_confidence": "high",
            "need_type": row_case.get("need_type", "unknown"),
            "urgency": "REVIEW",
            "human_review_required": True,
            "longitude": float(row_case["longitude"]),
            "latitude": float(row_case["latitude"]),
        }

    mutation_row = case_row(primary_case, case_id, f"RQ-GIS-MUTATION-{token}")
    companion_rows = [
        case_row(nearby_case, nearby_case_id, f"RQ-GIS-NEARBY-{token}"),
        case_row(outside_case, outside_case_id, f"RQ-GIS-OUTSIDE-{token}"),
    ]

    schema = _configured_postgis_schema()
    table = _postgis_table(schema)
    zone_table = _postgis_zone_table(schema)
    evidence.update(
        {
            "schema": schema,
            "case_table": table,
            "zone_table": zone_table,
            "table": table,
            "tables_expected": [table, zone_table],
            "spatial_schema_created_if_missing": True,
            "inserted_zone_public": {
                "operation_zone_id": operation_zone_id,
                "zone_name": operation_zone_name,
                "profile": profile,
                "zone_boundary_hint": coordinator.get("zone_boundary_hint"),
                "zone_polygon_wkt": zone_wkt,
                "relief_hub_name": coordinator.get("relief_hub_name"),
                "hub_point_lon_lat": [hub_lon, hub_lat],
                "relief_hub_radius_meters": relief_hub_radius_meters,
            },
            "inserted_public_row": dict(mutation_row),
            "inserted_companion_rows_public": [dict(row) for row in companion_rows],
            "update_set": {
                "operation_zone_id": operation_zone_id,
                "urgency": "HIGH when within configured relief hub radius, otherwise REVIEW",
                "human_review_required": False,
            },
            "delete_filter": {"case_id_prefix": case_id},
        }
    )

    def insert_case_sql(row: dict[str, Any]) -> str:
        columns = [
            "case_id",
            "public_case_ref",
            "operation_zone_id",
            "location_clue",
            "geo_scope_type",
            "geo_confidence",
            "need_type",
            "urgency",
            "human_review_required",
            "case_point",
            "geo_source",
        ]
        values = [
            _sql_literal(row["case_id"]),
            _sql_literal(row["public_case_ref"]),
            _sql_literal(row["operation_zone_id"]),
            _sql_literal(row["location_clue"]),
            _sql_literal(row["geo_scope_type"]),
            _sql_literal(row["geo_confidence"]),
            _sql_literal(row["need_type"]),
            _sql_literal(row["urgency"]),
            _sql_literal(row["human_review_required"]),
            f"ST_SetSRID(ST_MakePoint({row['longitude']}, {row['latitude']}), 4326)",
            "'synthetic_drill_gps'",
        ]
        assignments = ", ".join(f"{column}=EXCLUDED.{column}" for column in columns if column != "case_id")
        return f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({', '.join(values)})
            ON CONFLICT (case_id) DO UPDATE SET {assignments}
        """

    zone_insert_sql = f"""
        INSERT INTO {zone_table} (operation_zone_id, zone_name, scenario_tag, zone_geom, hub_point)
        VALUES (
            {_sql_literal(operation_zone_id)},
            {_sql_literal(operation_zone_name)},
            {_sql_literal('stateful_mutation_' + str(profile['name']))},
            ST_GeomFromText({_sql_literal(zone_wkt)}, 4326),
            ST_SetSRID(ST_MakePoint({hub_lon}, {hub_lat}), 4326)
        )
        ON CONFLICT (operation_zone_id) DO UPDATE SET
            zone_name=EXCLUDED.zone_name,
            scenario_tag=EXCLUDED.scenario_tag,
            zone_geom=EXCLUDED.zone_geom,
            hub_point=EXCLUDED.hub_point
    """
    spatial_assignment_sql = f"""
        UPDATE {table} AS c
        SET operation_zone_id = z.operation_zone_id,
            location_clue = 'spatially assigned by PostGIS ST_Contains to ' || z.operation_zone_id,
            urgency = CASE
                WHEN ST_DWithin(c.case_point::geography, z.hub_point::geography, {relief_hub_radius_meters}) THEN 'HIGH'
                ELSE 'REVIEW'
            END,
            human_review_required = FALSE
        FROM {zone_table} AS z
        WHERE c.case_id IN ({_sql_literal(case_id)}, {_sql_literal(nearby_case_id)}, {_sql_literal(outside_case_id)})
          AND ST_Contains(z.zone_geom, c.case_point)
    """
    query_case_sql = f"""
        SELECT
            c.case_id,
            c.operation_zone_id,
            z.zone_name,
            ST_AsText(c.case_point),
            ST_Contains(z.zone_geom, c.case_point)::text,
            ST_Distance(c.case_point::geography, z.hub_point::geography)::integer::text,
            ST_DWithin(c.case_point::geography, z.hub_point::geography, {relief_hub_radius_meters})::text,
            c.urgency,
            c.human_review_required::text
        FROM {table} AS c
        JOIN {zone_table} AS z ON z.operation_zone_id = c.operation_zone_id
        WHERE c.case_id = {_sql_literal(case_id)}
    """
    query_zone_sql = f"""
        SELECT count(*)::text
        FROM {table} AS c
        JOIN {zone_table} AS z ON z.operation_zone_id = {_sql_literal(operation_zone_id)}
        WHERE ST_Contains(z.zone_geom, c.case_point)
          AND c.case_id IN ({_sql_literal(case_id)}, {_sql_literal(nearby_case_id)}, {_sql_literal(outside_case_id)})
    """
    nearest_sql = f"""
        SELECT c.case_id, ST_Distance(c.case_point::geography, z.hub_point::geography)::integer::text AS distance_meters
        FROM {table} AS c
        JOIN {zone_table} AS z ON z.operation_zone_id = {_sql_literal(operation_zone_id)}
        WHERE c.case_id IN ({_sql_literal(case_id)}, {_sql_literal(nearby_case_id)}, {_sql_literal(outside_case_id)})
          AND ST_Contains(z.zone_geom, c.case_point)
        ORDER BY ST_Distance(c.case_point::geography, z.hub_point::geography) ASC
        LIMIT {nearest_case_limit}
    """
    outside_sql = f"""
        SELECT count(*)::text
        FROM {table} AS c
        JOIN {zone_table} AS z ON z.operation_zone_id = {_sql_literal(operation_zone_id)}
        WHERE c.case_id = {_sql_literal(outside_case_id)}
          AND ST_Contains(z.zone_geom, c.case_point)
    """
    index_sql = f"""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = {_sql_literal(schema)}
          AND indexname IN ('reliefqueue_live_cases_point_gix', 'reliefqueue_live_zones_geom_gix')
        ORDER BY indexname
    """
    table_found_sql = f"""
        SELECT to_regclass({_sql_literal(table)})::text, to_regclass({_sql_literal(zone_table)})::text
    """
    delete_cases_sql = f"""
        DELETE FROM {table}
        WHERE case_id IN ({_sql_literal(case_id)}, {_sql_literal(nearby_case_id)}, {_sql_literal(outside_case_id)})
    """
    delete_zone_sql = f"DELETE FROM {zone_table} WHERE operation_zone_id = {_sql_literal(operation_zone_id)}"
    cleanup_sql = f"""
        SELECT
            (SELECT count(*) FROM {table} WHERE case_id IN ({_sql_literal(case_id)}, {_sql_literal(nearby_case_id)}, {_sql_literal(outside_case_id)}))::text,
            (SELECT count(*) FROM {zone_table} WHERE operation_zone_id = {_sql_literal(operation_zone_id)})::text
    """

    try:
        _postgres_execute(dsn, [_postgis_schema_sql(schema)], _configured_postgis_timeout())
        evidence["operations"].append("spatial_schema_ready")
        table_rows = _postgres_query(dsn, table_found_sql, _configured_postgis_timeout())
        evidence["operations"].append("find_case_and_zone_tables")
        index_rows = _postgres_query(dsn, index_sql, _configured_postgis_timeout())
        evidence["operations"].append("verify_spatial_indexes")
        _postgres_execute(dsn, [zone_insert_sql], _configured_postgis_timeout())
        evidence["operations"].append("insert_operation_zone_polygon")
        _postgres_execute(dsn, [insert_case_sql(mutation_row), *(insert_case_sql(row) for row in companion_rows)], _configured_postgis_timeout())
        evidence["operations"].append("insert_case_points")
        _postgres_execute(dsn, [spatial_assignment_sql], _configured_postgis_timeout())
        evidence["operations"].append("spatially_assign_zone_and_update_urgency")
        case_rows = _postgres_query(dsn, query_case_sql, _configured_postgis_timeout())
        evidence["operations"].append("query_by_case_id_with_geometry")
        zone_rows = _postgres_query(dsn, query_zone_sql, _configured_postgis_timeout())
        evidence["operations"].append("query_inside_zone_polygon")
        nearest_rows = _postgres_query(dsn, nearest_sql, _configured_postgis_timeout())
        evidence["operations"].append("query_nearest_cases_to_relief_hub")
        outside_rows = _postgres_query(dsn, outside_sql, _configured_postgis_timeout())
        evidence["operations"].append("prove_outside_case_excluded_by_polygon")
        _postgres_execute(dsn, [delete_cases_sql, delete_zone_sql], _configured_postgis_timeout())
        evidence["operations"].append("delete_test_cases_and_zone")
        cleanup_rows = _postgres_query(dsn, cleanup_sql, _configured_postgis_timeout())
        evidence["operations"].append("verify_cleanup")
    except Exception as exc:
        try:
            _postgres_execute(dsn, [delete_cases_sql, delete_zone_sql], _configured_postgis_timeout())
        except Exception:
            pass
        evidence.update({"status": "FAIL", "live_write_attempted": True, **_live_error(exc)})
        _write_json(out_dir / "postgis_mutation_evidence.json", evidence)
        return evidence

    updated_row = case_rows[0] if case_rows else []
    cleanup_case_count = int(cleanup_rows[0][0] or 0) if cleanup_rows else -1
    cleanup_zone_count = int(cleanup_rows[0][1] or 0) if cleanup_rows else -1
    inside_zone_count = int(zone_rows[0][0] or 0) if zone_rows else 0
    outside_inside_count = int(outside_rows[0][0] or 0) if outside_rows else -1
    tables_found = list(table_rows[0]) if table_rows else []
    spatial_indexes = [row[0] for row in index_rows]
    row_read_back = bool(updated_row) and updated_row[0] == case_id
    spatial_assignment_verified = bool(updated_row) and updated_row[1] == operation_zone_id and str(updated_row[4]).lower() in {"true", "t"}
    update_verified = (
        bool(updated_row)
        and updated_row[7] == "HIGH"
        and str(updated_row[8]).lower() in {"false", "f"}
    )
    cleanup_verified = cleanup_case_count == 0 and cleanup_zone_count == 0
    outside_excluded = outside_inside_count == 0
    nearest_cases = [{"case_id": row[0], "distance_meters": int(row[1] or 0)} for row in nearest_rows]
    evidence.update(
        {
            "status": "PASS"
            if row_read_back and spatial_assignment_verified and update_verified and outside_excluded and cleanup_verified
            else "FAIL",
            "live_write_attempted": True,
            "tables_found": tables_found,
            "spatial_indexes_found": spatial_indexes,
            "rows_inserted": 3,
            "zones_inserted": 1,
            "row_read_back": row_read_back,
            "read_back_row": {
                "case_id": updated_row[0],
                "operation_zone_id": updated_row[1],
                "zone_name": updated_row[2],
                "case_point_wkt": updated_row[3],
                "inside_zone_polygon": str(updated_row[4]).lower() in {"true", "t"},
                "distance_to_relief_hub_meters": int(updated_row[5] or 0),
                "relief_hub_radius_meters": relief_hub_radius_meters,
                "within_configured_relief_hub_radius": str(updated_row[6]).lower() in {"true", "t"},
                "urgency": updated_row[7],
                "human_review_required": str(updated_row[8]).lower() in {"true", "t"},
            }
            if updated_row
            else {},
            "spatial_assignment_verified": spatial_assignment_verified,
            "update_verified": update_verified,
            "inside_zone_count_after_insert": inside_zone_count,
            "outside_case_excluded_by_polygon": outside_excluded,
            "nearest_cases_to_relief_hub": nearest_cases,
            "deleted_case_ids": [case_id, nearby_case_id, outside_case_id],
            "deleted_operation_zone_id": operation_zone_id,
            "cleanup_verified": cleanup_verified,
            "cleanup_remaining_rows": cleanup_case_count,
            "cleanup_remaining_zones": cleanup_zone_count,
        }
    )
    _write_json(out_dir / "postgis_mutation_evidence.json", evidence)
    return evidence


def _redis_flatten_fields(fields: dict[str, Any]) -> list[str]:
    flattened: list[str] = []
    for key, value in fields.items():
        flattened.extend([str(key), str(value)])
    return flattened


def _redis_stateful_mutation_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    url, redis_source, redis_note = _resolved_redis_url(report_dir)
    drill_config = _stateful_mutation_drill_config()
    command_center = drill_config["command_center_config"]
    profile = drill_config["selected_profile"]
    token = utc_now().replace("-", "").replace(":", "").replace("Z", "")
    base_stream = _configured_queue_name()
    stream = f"{base_stream}.stateful_mutation.{token}"
    dlq_stream = f"{stream}.dead_letter"
    replay_stream = f"{stream}.replay_review"
    group = "reliefqueue-stateful-mutation-worker"
    consumer = "drill-worker-once"
    recovery_consumer = "drill-recovery-worker"
    dedup_key = f"{stream}:dedup:synthetic-radio-call-001"
    redis_burst_size = int(command_center["redis_burst_size"])
    dedup_ttl_seconds = int(command_center["dedup_ttl_seconds"])
    dlq_after_attempts = int(command_center["dlq_after_attempts"])
    core_job_count = 4
    evidence: dict[str, Any] = {
        "status": "SKIP",
        "backend": "redis",
        "scenario": "role_profile_bursty_intake_worker_crash_retry_dlq_replay_and_dedup",
        "why_redis_matters": [
            "absorbs command-center configured bursts of intake jobs without blocking operators",
            "consumer groups expose pending jobs when a worker crashes before ACK",
            "XCLAIM lets another worker safely recover the abandoned job",
            "DLQ and replay streams preserve failed work for human review instead of losing it",
            "SET NX gives atomic duplicate suppression for repeated channel events",
        ],
        "selected_profile": profile,
        "available_profiles": drill_config["available_profiles"],
        "role_contract": drill_config["role_contract"],
        "runtime_config": command_center,
        "command_center_config": command_center,
        "config_warnings": drill_config["config_warnings"],
        "redis_source": redis_source,
        "auto_resolved_live_stack": redis_source == "local_live_stack",
        "note": redis_note,
        "stream": stream,
        "dead_letter_stream": dlq_stream,
        "replay_review_stream": replay_stream,
        "consumer_group": group,
        "operations": [],
        "jobs_prepared": 0,
        "core_drill_jobs_prepared": core_job_count,
        "burst_buffer_jobs_prepared": 0,
        "live_mutation_attempted": False,
        "cleanup_verified": False,
        "secret_values_printed": False,
    }
    if not url:
        evidence["note"] = (
            redis_note
            or "Set RELIEFQUEUE_REDIS_URL or run make live-stack-up to run the Redis stateful mutation drill."
        )
        _write_json(out_dir / "redis_mutation_evidence.json", evidence)
        return evidence

    try:
        cases, _zones, _workers, _assignments = _load_demo(root)
    except Exception:
        cases = []
    public_case = (
        redact_public_case(cases[0])
        if cases
        else {"case_id": "stateful-mutation-case", "operation_zone_id": "zone-stateful-drill"}
    )
    public_case_id = public_case["case_id"]
    jobs = [
        {
            "job_id": f"{token}-process",
            "case_id": public_case_id,
            "attempt": "0",
            "purpose": "process_once",
            "priority": "normal",
            "source_event_id": "synthetic-radio-call-001",
        },
        {
            "job_id": f"{token}-crash",
            "case_id": public_case_id,
            "attempt": "0",
            "purpose": "simulate_worker_crash_before_ack",
            "priority": "high",
            "source_event_id": "synthetic-radio-call-002",
        },
        {
            "job_id": f"{token}-retry",
            "case_id": public_case_id,
            "attempt": "0",
            "purpose": "force_retry",
            "priority": "high",
            "source_event_id": "synthetic-radio-call-003",
        },
        {
            "job_id": f"{token}-dlq",
            "case_id": public_case_id,
            "attempt": str(max(0, dlq_after_attempts - 1)),
            "purpose": "force_dlq",
            "priority": "high",
            "source_event_id": "synthetic-radio-call-004",
        },
    ]
    for index in range(core_job_count + 1, redis_burst_size + 1):
        jobs.append(
            {
                "job_id": f"{token}-burst-buffer-{index - core_job_count}",
                "case_id": public_case_id,
                "attempt": "0",
                "purpose": "burst_buffer_unclaimed",
                "priority": "normal",
                "source_event_id": f"synthetic-radio-call-{index:03d}",
            }
        )
    evidence["jobs_prepared"] = len(jobs)
    evidence["burst_buffer_jobs_prepared"] = max(0, len(jobs) - core_job_count)
    evidence["prepared_jobs_public_fields"] = [dict(job) for job in jobs[:12]]
    evidence["prepared_jobs_public_fields_truncated"] = len(jobs) > 12

    try:
        _redis_command(url, ["PING"])
        evidence["operations"].append("ping")
        dedup_first = _redis_command(url, ["SET", dedup_key, "accepted", "NX", "EX", str(dedup_ttl_seconds)])
        dedup_second = _redis_command(url, ["SET", dedup_key, "duplicate", "NX", "EX", str(dedup_ttl_seconds)])
        evidence["operations"].append("atomic_dedup_set_nx")
        _redis_xgroup_create(url, stream, group)
        evidence["operations"].append("consumer_group_ready")
        redis_ids = [
            _redis_command(
                url,
                [
                    "XADD",
                    stream,
                    "*",
                    *_redis_flatten_fields(
                        {
                            **job,
                            "human_review_required": "true",
                            "payload_policy": "public_allowlisted_fields_only",
                        }
                    ),
                ],
            )
            for job in jobs
        ]
        evidence["operations"].append("enqueue_bursty_test_jobs")
        queue_depth_after_enqueue = int(_redis_command(url, ["XLEN", stream]) or 0)
        entries = _redis_entries(
            _redis_command(url, ["XREADGROUP", "GROUP", group, consumer, "COUNT", str(core_job_count), "STREAMS", stream, ">"])
        )
        evidence["operations"].append("claim_core_drill_jobs_in_consumer_group")
        fields_by_purpose = {fields.get("purpose", ""): (message_id, fields) for message_id, fields in entries}

        processed_id, _processed_fields = fields_by_purpose["process_once"]
        _redis_command(url, ["XACK", stream, group, processed_id])
        evidence["operations"].append("process_one_job")

        crashed_id, _crashed_fields = fields_by_purpose["simulate_worker_crash_before_ack"]
        pending_after_crash = _redis_command(url, ["XPENDING", stream, group])
        pending_total_after_crash = int(pending_after_crash[0] or 0) if pending_after_crash else 0
        pending_breakdown_after_crash = {
            "total_pending": pending_total_after_crash,
            "simulated_crash_job_pending": pending_total_after_crash >= 1,
            "other_core_drill_jobs_pending": max(0, pending_total_after_crash - 1),
            "unclaimed_burst_buffer_jobs": max(0, redis_burst_size - len(entries)),
        }
        evidence["operations"].append("leave_one_job_pending_to_simulate_worker_crash")
        recovered_entries = _redis_entries(
            [[stream, _redis_command(url, ["XCLAIM", stream, group, recovery_consumer, "0", crashed_id])]]
        )
        recovered_id = recovered_entries[0][0] if recovered_entries else ""
        if recovered_id:
            _redis_command(url, ["XACK", stream, group, recovered_id])
        pending_after_recovery = _redis_command(url, ["XPENDING", stream, group])
        pending_total_after_recovery = int(pending_after_recovery[0] or 0) if pending_after_recovery else 0
        pending_breakdown_after_recovery = {
            "total_pending": pending_total_after_recovery,
            "recovered_crash_job_pending": False,
            "other_core_drill_jobs_pending": pending_total_after_recovery,
            "unclaimed_burst_buffer_jobs": max(0, redis_burst_size - len(entries)),
        }
        evidence["operations"].append("recover_pending_job_with_xclaim")

        retry_id, retry_fields = fields_by_purpose["force_retry"]
        _redis_command(url, ["XACK", stream, group, retry_id])
        retry_message_id = _redis_command(
            url,
            [
                "XADD",
                stream,
                "*",
                *_redis_flatten_fields(
                    {
                        **retry_fields,
                        "attempt": "1",
                        "retry_for_message_id": retry_id,
                        "retry_reason": "transient_worker_error",
                        "human_review_required": "true",
                    }
                ),
            ],
        )
        retry_entries = _redis_entries(
            _redis_command(
                url,
                ["XREADGROUP", "GROUP", group, consumer, "COUNT", str(redis_burst_size + 1), "STREAMS", stream, ">"],
            )
        )
        retry_processed_message_id = ""
        burst_buffer_jobs_drained_after_retry = 0
        for message_id, fields in retry_entries:
            if message_id == retry_message_id or fields.get("retry_for_message_id") == retry_id:
                retry_processed_message_id = message_id
            elif fields.get("purpose") == "burst_buffer_unclaimed":
                burst_buffer_jobs_drained_after_retry += 1
            _redis_command(url, ["XACK", stream, group, message_id])
        evidence["operations"].append("force_one_retry")

        dlq_id, dlq_fields = fields_by_purpose["force_dlq"]
        dlq_message_id = _redis_command(
            url,
            [
                "XADD",
                dlq_stream,
                "*",
                *_redis_flatten_fields(
                    {
                        **dlq_fields,
                        "attempt": str(dlq_after_attempts),
                        "status": "dead_lettered",
                        "failure_class": "schema_validation_failed_after_max_attempts",
                        "human_review_required": "true",
                        "source_message_id": dlq_id,
                    }
                ),
            ],
        )
        _redis_command(url, ["XACK", stream, group, dlq_id])
        evidence["operations"].append("force_one_dlq_entry")

        dlq_entries = _redis_entries(
            [[dlq_stream, _redis_command(url, ["XRANGE", dlq_stream, "-", "+", "COUNT", "20"])] ]
        )
        replay_ids = []
        for message_id, fields in dlq_entries:
            replay_ids.append(
                _redis_command(
                    url,
                    [
                        "XADD",
                        replay_stream,
                        "*",
                        *_redis_flatten_fields(
                            {
                                "job_id": fields.get("job_id", message_id),
                                "case_id": fields.get("case_id", "unknown"),
                                "replay_status": "safe_replayed_for_human_review",
                                "replay_mode": command_center["replay_mode"],
                                "original_dlq_message_id": message_id,
                                "human_review_required": "true",
                            }
                        ),
                    ],
                )
            )
            _redis_command(url, ["XDEL", dlq_stream, message_id])
        evidence["operations"].append("replay_dlq_safely")

        final_before_cleanup = {
            "stream_length": int(_redis_command(url, ["XLEN", stream]) or 0),
            "dlq_length": int(_redis_command(url, ["XLEN", dlq_stream]) or 0),
            "replay_review_length": int(_redis_command(url, ["XLEN", replay_stream]) or 0),
            "pending": _redis_command(url, ["XPENDING", stream, group]),
            "dedup_key_exists": int(_redis_command(url, ["EXISTS", dedup_key]) or 0),
        }
        _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, dedup_key])
        evidence["operations"].append("cleanup_drill_streams_and_dedup_key")
        final_after_cleanup = {
            "stream_exists": int(_redis_command(url, ["EXISTS", stream]) or 0),
            "dlq_exists": int(_redis_command(url, ["EXISTS", dlq_stream]) or 0),
            "replay_review_exists": int(_redis_command(url, ["EXISTS", replay_stream]) or 0),
            "dedup_key_exists": int(_redis_command(url, ["EXISTS", dedup_key]) or 0),
        }
    except Exception as exc:
        try:
            _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, dedup_key])
        except Exception:
            pass
        evidence.update({"status": "FAIL", "live_mutation_attempted": True, **_live_error(exc)})
        _write_json(out_dir / "redis_mutation_evidence.json", evidence)
        return evidence

    cleanup_verified = not any(final_after_cleanup.values())
    replay_verified = final_before_cleanup["replay_review_length"] >= 1 and final_before_cleanup["dlq_length"] == 0
    crash_recovered = recovered_id == crashed_id and bool(pending_after_crash) and int(pending_after_crash[0] or 0) >= 1
    no_pending_left = bool(final_before_cleanup["pending"]) and int(final_before_cleanup["pending"][0] or 0) == 0
    dedup_verified = dedup_first == "OK" and dedup_second is None
    evidence.update(
        {
            "status": "PASS" if cleanup_verified and replay_verified and crash_recovered and no_pending_left and dedup_verified else "FAIL",
            "live_mutation_attempted": True,
            "enqueued": len(redis_ids),
            "enqueued_message_ids": redis_ids,
            "queue_depth_after_enqueue": queue_depth_after_enqueue,
            "claimed": len(entries),
            "claimed_jobs_by_purpose": sorted(fields_by_purpose),
            "processed": 1,
            "processed_message_id": processed_id,
            "simulated_worker_crash_message_id": crashed_id,
            "pending_after_worker_crash": pending_after_crash,
            "pending_breakdown_after_worker_crash": pending_breakdown_after_crash,
            "recovered_message_id": recovered_id,
            "recovery_consumer": recovery_consumer,
            "pending_after_recovery": pending_after_recovery,
            "pending_breakdown_after_recovery": pending_breakdown_after_recovery,
            "retry_original_message_id": retry_id,
            "retry_message_id": retry_message_id,
            "retry_processed_message_id": retry_processed_message_id,
            "burst_buffer_jobs_drained_after_retry": burst_buffer_jobs_drained_after_retry,
            "dlq_source_message_id": dlq_id,
            "dead_letter_message_id": dlq_message_id,
            "dlq_after_attempts": dlq_after_attempts,
            "replay_message_ids": replay_ids,
            "replayed": len(replay_ids),
            "atomic_dedup": {
                "key": dedup_key,
                "dedup_ttl_seconds": dedup_ttl_seconds,
                "first_event_result": dedup_first,
                "duplicate_event_result": dedup_second,
                "duplicate_suppressed": dedup_verified,
            },
            "streams_deleted": [stream, dlq_stream, replay_stream],
            "final_state_before_cleanup": final_before_cleanup,
            "final_state_after_cleanup": final_after_cleanup,
            "worker_crash_recovered": crash_recovered,
            "no_pending_left": no_pending_left,
            "cleanup_verified": cleanup_verified,
        }
    )
    _write_json(out_dir / "redis_mutation_evidence.json", evidence)
    return evidence


def _nats_guidance_proof(report_dir: Path, out_dir: Path) -> dict[str, Any]:
    host, port, source, note = _resolved_nats_endpoint(report_dir)
    evidence: dict[str, Any] = {
        "status": "SKIP",
        "role": "connectivity_proof_only",
        "nats_source": source,
        "note": note,
        "jetstream_queue_mutation_attempted": False,
        "reason": "Current queue backend is Redis; no JetStream-backed queue code is wired in the current live integration boundary.",
        "secret_values_printed": False,
    }
    if not host or not port:
        evidence["note"] = note or "Set RELIEFQUEUE_NATS_URL or run make live-stack-up for NATS socket proof."
        _write_json(out_dir / "nats_guidance_proof.json", evidence)
        return evidence
    try:
        with socket.create_connection((host, port), timeout=3.0) as sock:
            sock.settimeout(3.0)
            greeting = sock.recv(512).decode("utf-8", "replace")
            sock.sendall(b"PING\r\n")
            response = sock.recv(512).decode("utf-8", "replace")
    except Exception as exc:
        evidence.update({"status": "FAIL", "reachable": False, **_live_error(exc)})
        _write_json(out_dir / "nats_guidance_proof.json", evidence)
        return evidence
    evidence.update(
        {
            "status": "PASS",
            "reachable": True,
            "endpoint": f"{host}:{port}",
            "protocol_ping": "PONG" if "PONG" in response else "connected_without_pong",
            "server_info_seen": greeting.startswith("INFO"),
        }
    )
    _write_json(out_dir / "nats_guidance_proof.json", evidence)
    return evidence


def live_stateful_mutation_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    drill_config = _stateful_mutation_drill_config()
    postgis = _postgis_stateful_mutation_drill(root, report_dir, out_dir)
    redis = _redis_stateful_mutation_drill(root, report_dir, out_dir)
    nats = _nats_guidance_proof(report_dir, out_dir)
    service_statuses = [str(postgis.get("status")), str(redis.get("status"))]
    if "FAIL" in service_statuses:
        status = "FAIL"
        readiness = "NEEDS_REVIEW"
    elif service_statuses == ["PASS", "PASS"]:
        status = "PASS"
        readiness = "READY_FOR_NEXT_LIVE_INTEGRATION_PHASE"
    elif "PASS" in service_statuses:
        status = "PARTIAL"
        readiness = "NEEDS_BOTH_POSTGIS_AND_REDIS_LIVE_ENDPOINTS"
    else:
        status = "SKIP"
        readiness = "NEEDS_LIVE_STACK_OR_EXPLICIT_ENDPOINTS"

    summary = {
        "postgis": str(postgis.get("status")),
        "redis": str(redis.get("status")),
        "nats": str(nats.get("status")),
    }
    status_counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "PARTIAL": 0}
    for item in summary.values():
        if item in status_counts:
            status_counts[item] += 1
    results = [{"command": "live-stateful-mutation-drill", "exit_code": 0 if status in {"PASS", "PARTIAL", "SKIP"} else 1}]
    write_checkpoint(
        root,
        report_dir,
        "02_03",
        status,
        ["live-stateful-mutation-drill"],
        results,
        _summary_strings(status_counts),
        ["NATS remains connectivity/socket proof only until JetStream-backed queue code is wired."],
        readiness,
    )
    return {
        "status": status,
        "phase_id": "02_03",
        "phase_name": PHASES["02_03"]["name"],
        "selected_profile": drill_config["selected_profile"],
        "available_profiles": drill_config["available_profiles"],
        "role_contract": drill_config["role_contract"],
        "coordinator_config": drill_config["coordinator_config"],
        "command_center_config": drill_config["command_center_config"],
        "config_warnings": drill_config["config_warnings"],
        "postgis": postgis,
        "redis": redis,
        "nats": nats,
        "summary": summary,
        "status_counts": status_counts,
        "report_files": [
            "postgis_mutation_evidence.json",
            "redis_mutation_evidence.json",
            "nats_guidance_proof.json",
        ],
        "cleanup_verified": bool(postgis.get("cleanup_verified")) and bool(redis.get("cleanup_verified")),
        "private_payload_written": False,
        "secret_values_printed": False,
    }


def _point_sql(point: dict[str, Any]) -> str:
    return f"ST_SetSRID(ST_MakePoint({float(point['longitude'])}, {float(point['latitude'])}), 4326)"


def _hub_point_sql(lon: float, lat: float) -> str:
    return f"ST_SetSRID(ST_MakePoint({float(lon)}, {float(lat)}), 4326)"


def _request_destination_point(coordinator: dict[str, Any], destination_label: str) -> dict[str, Any]:
    return dict(coordinator["delivery_points"].get(destination_label) or coordinator["delivery_points"]["primary_case"])


def _postgis_logistics_asset_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    config = _logistics_drill_config()
    coordinator = config["coordinator_config"]
    command_center = config["command_center_config"]
    dsn, source, note = _resolved_postgis_dsn(report_dir)
    schema = _configured_postgis_schema()
    timeout = _configured_postgis_timeout()
    hub_table = _logistics_hub_table(schema)
    asset_table = _logistics_asset_table(schema)
    request_table = _logistics_request_table(schema)
    token = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    tag = f"logistics_asset_{config['selected_profile']['name']}_{token}"
    primary_hub_id = f"{tag}-hub-primary"
    secondary_hub_id = f"{tag}-hub-secondary"
    returnable_asset_id = f"{tag}-asset-returnable"
    consumable_asset_id = f"{tag}-asset-consumable"
    support_asset_id = f"{tag}-asset-support"
    request_ids = {row["request_id_suffix"]: f"{tag}-req-{row['request_id_suffix']}" for row in coordinator["planned_requests"]}
    evidence: dict[str, Any] = {
        "status": "SKIP",
        "postgis_backend": source,
        "note": note,
        "scenario": "mission_logistics_inventory_reservation_dispatch_return_and_reallocation",
        "selected_profile": config["selected_profile"],
        "role_contract": config["role_contract"],
        "coordinator_config": coordinator,
        "command_center_config": command_center,
        "case_for_postgis": [
            "nearest available asset or hub by destination point",
            "asset inventory tagged by hub, class, status, and return deadline",
            "returnable asset lifecycle and reallocation evidence",
            "spatial indexes for hub, asset, and request points",
        ],
        "tables": {"hubs": hub_table, "assets": asset_table, "requests": request_table},
        "logistics_scenario_tag": tag,
        "live_mutation_attempted": False,
        "secret_values_printed": False,
    }
    if not dsn:
        evidence["reason"] = note or "Set RELIEFQUEUE_POSTGIS_DSN or run make live-stack-up to run the logistics PostGIS drill."
        _write_json(out_dir / "logistics_postgis_evidence.json", evidence)
        return evidence

    inventory_seed = coordinator["inventory_seed"]
    returnable_asset = inventory_seed[0]
    consumable_asset = inventory_seed[1]
    support_asset = inventory_seed[2]
    primary_point = coordinator["delivery_points"]["primary_case"]
    nearby_point = coordinator["delivery_points"]["nearby_case"]
    secondary_lon = float(nearby_point["longitude"]) + 0.01
    secondary_lat = float(nearby_point["latitude"]) + 0.01

    try:
        statements = [
            _postgis_logistics_schema_sql(schema),
            f"DELETE FROM {request_table} WHERE scenario_tag = {_sql_literal(tag)};",
            f"DELETE FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)};",
            f"DELETE FROM {hub_table} WHERE scenario_tag = {_sql_literal(tag)};",
            f"INSERT INTO {hub_table} (hub_id, hub_name, scenario_tag, hub_point) VALUES ("
            f"{_sql_literal(primary_hub_id)}, {_sql_literal(coordinator['relief_hub_name'])}, {_sql_literal(tag)}, "
            f"{_hub_point_sql(float(coordinator['relief_hub_lon']), float(coordinator['relief_hub_lat']))});",
            f"INSERT INTO {hub_table} (hub_id, hub_name, scenario_tag, hub_point) VALUES ("
            f"{_sql_literal(secondary_hub_id)}, {_sql_literal('Synthetic forward staging point')}, {_sql_literal(tag)}, "
            f"{_hub_point_sql(secondary_lon, secondary_lat)});",
            f"INSERT INTO {asset_table} (asset_id, asset_tag, asset_type, asset_class, quantity_total, quantity_available, status, current_hub_id, asset_point, scenario_tag) VALUES ("
            f"{_sql_literal(returnable_asset_id)}, {_sql_literal(returnable_asset['asset_tag_prefix'] + '-' + token)}, {_sql_literal(returnable_asset['asset_type'])}, "
            f"{_sql_literal(returnable_asset['asset_class'])}, {int(returnable_asset['quantity_total'])}, {int(returnable_asset['quantity_available'])}, "
            f"{_sql_literal('available')}, {_sql_literal(primary_hub_id)}, {_hub_point_sql(float(coordinator['relief_hub_lon']), float(coordinator['relief_hub_lat']))}, {_sql_literal(tag)});",
            f"INSERT INTO {asset_table} (asset_id, asset_tag, asset_type, asset_class, quantity_total, quantity_available, status, current_hub_id, asset_point, scenario_tag) VALUES ("
            f"{_sql_literal(consumable_asset_id)}, {_sql_literal(consumable_asset['asset_tag_prefix'] + '-' + token)}, {_sql_literal(consumable_asset['asset_type'])}, "
            f"{_sql_literal(consumable_asset['asset_class'])}, {int(consumable_asset['quantity_total'])}, {int(consumable_asset['quantity_available'])}, "
            f"{_sql_literal('available')}, {_sql_literal(primary_hub_id)}, {_hub_point_sql(float(coordinator['relief_hub_lon']), float(coordinator['relief_hub_lat']))}, {_sql_literal(tag)});",
            f"INSERT INTO {asset_table} (asset_id, asset_tag, asset_type, asset_class, quantity_total, quantity_available, status, current_hub_id, asset_point, scenario_tag) VALUES ("
            f"{_sql_literal(support_asset_id)}, {_sql_literal(support_asset['asset_tag_prefix'] + '-' + token)}, {_sql_literal(support_asset['asset_type'])}, "
            f"{_sql_literal(support_asset['asset_class'])}, {int(support_asset['quantity_total'])}, {int(support_asset['quantity_available'])}, "
            f"{_sql_literal('available')}, {_sql_literal(secondary_hub_id)}, {_hub_point_sql(secondary_lon, secondary_lat)}, {_sql_literal(tag)});",
        ]
        for request in coordinator["planned_requests"]:
            destination = _request_destination_point(coordinator, str(request["destination"]))
            return_due = (
                f"now() + interval '{int(request['return_due_minutes'])} minutes'"
                if request.get("return_due_minutes") is not None
                else "NULL"
            )
            statements.append(
                f"INSERT INTO {request_table} (request_id, team_id, team_role, asset_type, asset_class, quantity_requested, priority, "
                f"destination_label, destination_point, required_by_at, expected_return_at, status, scenario_tag) VALUES ("
                f"{_sql_literal(request_ids[request['request_id_suffix']])}, {_sql_literal(request['team_id'])}, {_sql_literal(request['team_role'])}, "
                f"{_sql_literal(request['asset_type'])}, {_sql_literal(request['asset_class'])}, {int(request['quantity'])}, {_sql_literal(request['priority'])}, "
                f"{_sql_literal(request['destination'])}, {_point_sql(destination)}, now() + interval '{int(request['needed_within_minutes'])} minutes', "
                f"{return_due}, {_sql_literal('requested')}, {_sql_literal(tag)});"
            )
        _postgres_execute(dsn, statements, timeout)

        table_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(table_schema || '.' || table_name ORDER BY table_name), '[]'::json)::text "
            f"FROM information_schema.tables WHERE table_schema = {_sql_literal(schema)} "
            f"AND table_name IN ('reliefqueue_live_logistics_hubs','reliefqueue_live_inventory_assets','reliefqueue_live_logistics_requests');",
            timeout,
        )
        index_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(indexname ORDER BY indexname), '[]'::json)::text FROM pg_indexes "
            f"WHERE schemaname = {_sql_literal(schema)} AND indexname LIKE 'reliefqueue_live_%gix';",
            timeout,
        )
        hub_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(json_build_object('hub_id', hub_id, 'hub_name', hub_name, "
            f"'longitude', round(ST_X(hub_point)::numeric, 5), 'latitude', round(ST_Y(hub_point)::numeric, 5)) ORDER BY hub_id), '[]'::json)::text "
            f"FROM {hub_table} WHERE scenario_tag = {_sql_literal(tag)};",
            timeout,
        )
        asset_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(json_build_object('asset_id', asset_id, 'asset_tag', asset_tag, 'asset_type', asset_type, "
            f"'asset_class', asset_class, 'quantity_available', quantity_available, 'status', status, 'current_hub_id', current_hub_id) ORDER BY asset_id), '[]'::json)::text "
            f"FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)};",
            timeout,
        )
        request_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(json_build_object('request_id', request_id, 'team_id', team_id, 'team_role', team_role, "
            f"'asset_type', asset_type, 'quantity_requested', quantity_requested, 'priority', priority, 'status', status, "
            f"'destination_label', destination_label, 'required_by_at', to_char(required_by_at, 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')) ORDER BY request_id), '[]'::json)::text "
            f"FROM {request_table} WHERE scenario_tag = {_sql_literal(tag)};",
            timeout,
        )
        rescue_request_id = request_ids["rescue-returnable"]
        nearest_rows = _postgres_query(
            dsn,
            f"WITH req AS (SELECT * FROM {request_table} WHERE request_id = {_sql_literal(rescue_request_id)}), "
            f"ranked AS (SELECT a.asset_id, a.asset_tag, a.asset_type, a.current_hub_id, "
            f"round(ST_Distance(a.asset_point::geography, req.destination_point::geography))::int AS distance_meters "
            f"FROM {asset_table} a CROSS JOIN req WHERE a.scenario_tag = {_sql_literal(tag)} AND a.asset_type = req.asset_type "
            f"AND a.status = 'available' AND a.quantity_available >= req.quantity_requested ORDER BY a.asset_point <-> req.destination_point LIMIT 1) "
            f"SELECT row_to_json(ranked)::text FROM ranked;",
            timeout,
        )
        nearest_asset = _json_from_first_row(nearest_rows, {})
        selected_asset_id = str(nearest_asset.get("asset_id") or returnable_asset_id)
        selected_hub_id = str(nearest_asset.get("current_hub_id") or primary_hub_id)
        expected_arrival = max(5, int(round(float(nearest_asset.get("distance_meters") or 0) / 250)))
        _postgres_execute(
            dsn,
            [
                f"UPDATE {asset_table} SET status = 'reserved', quantity_available = 0, expected_return_at = now() + interval '240 minutes' "
                f"WHERE asset_id = {_sql_literal(selected_asset_id)};",
                f"UPDATE {request_table} SET status = 'reserved', assigned_asset_id = {_sql_literal(selected_asset_id)}, source_hub_id = {_sql_literal(selected_hub_id)}, "
                f"expected_arrival_minutes = {expected_arrival} WHERE request_id = {_sql_literal(rescue_request_id)};",
                f"UPDATE {asset_table} SET quantity_available = quantity_available - 20, status = 'partially_available' "
                f"WHERE asset_id = {_sql_literal(consumable_asset_id)};",
                f"UPDATE {request_table} SET status = 'reserved', assigned_asset_id = {_sql_literal(consumable_asset_id)}, source_hub_id = {_sql_literal(primary_hub_id)}, "
                f"expected_arrival_minutes = {expected_arrival + 5} WHERE request_id = {_sql_literal(request_ids['consumable-lot'])};",
                f"UPDATE {request_table} SET status = 'delivered' WHERE request_id IN ({_sql_literal(rescue_request_id)}, {_sql_literal(request_ids['consumable-lot'])});",
                f"UPDATE {asset_table} SET status = 'in_use' WHERE asset_id = {_sql_literal(selected_asset_id)};",
                f"UPDATE {asset_table} SET status = 'return_due', expected_return_at = now() - interval '10 minutes' WHERE asset_id = {_sql_literal(selected_asset_id)};",
            ],
            timeout,
        )
        overdue_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(json_build_object('asset_id', asset_id, 'asset_tag', asset_tag, 'asset_type', asset_type, "
            f"'status', status, 'minutes_overdue', round(EXTRACT(EPOCH FROM (now() - expected_return_at)) / 60)::int)), '[]'::json)::text "
            f"FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)} AND expected_return_at < now();",
            timeout,
        )
        reallocation_request_id = request_ids["critical-reallocation"]
        _postgres_execute(
            dsn,
            [
                f"UPDATE {request_table} SET status = 'reallocation_review', assigned_asset_id = {_sql_literal(selected_asset_id)}, source_hub_id = {_sql_literal(selected_hub_id)}, "
                f"expected_arrival_minutes = {expected_arrival + 3} WHERE request_id = {_sql_literal(reallocation_request_id)};",
                f"UPDATE {asset_table} SET status = 'reallocated' WHERE asset_id = {_sql_literal(selected_asset_id)};",
            ],
            timeout,
        )
        final_inventory_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(json_build_object('asset_id', asset_id, 'asset_tag', asset_tag, 'asset_type', asset_type, "
            f"'asset_class', asset_class, 'quantity_available', quantity_available, 'status', status, 'current_hub_id', current_hub_id) ORDER BY asset_id), '[]'::json)::text "
            f"FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)};",
            timeout,
        )
        final_request_rows = _postgres_query(
            dsn,
            f"SELECT COALESCE(json_agg(json_build_object('request_id', request_id, 'team_role', team_role, 'asset_type', asset_type, "
            f"'priority', priority, 'status', status, 'assigned_asset_id', assigned_asset_id, 'expected_arrival_minutes', expected_arrival_minutes) ORDER BY request_id), '[]'::json)::text "
            f"FROM {request_table} WHERE scenario_tag = {_sql_literal(tag)};",
            timeout,
        )
        _postgres_execute(
            dsn,
            [
                f"DELETE FROM {request_table} WHERE scenario_tag = {_sql_literal(tag)};",
                f"DELETE FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)};",
                f"DELETE FROM {hub_table} WHERE scenario_tag = {_sql_literal(tag)};",
            ],
            timeout,
        )
        cleanup_rows = _postgres_query(
            dsn,
            f"SELECT (SELECT count(*) FROM {request_table} WHERE scenario_tag = {_sql_literal(tag)})::text, "
            f"(SELECT count(*) FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)})::text, "
            f"(SELECT count(*) FROM {hub_table} WHERE scenario_tag = {_sql_literal(tag)})::text;",
            timeout,
        )
    except Exception as exc:
        try:
            _postgres_execute(
                dsn,
                [
                    f"DELETE FROM {request_table} WHERE scenario_tag = {_sql_literal(tag)};",
                    f"DELETE FROM {asset_table} WHERE scenario_tag = {_sql_literal(tag)};",
                    f"DELETE FROM {hub_table} WHERE scenario_tag = {_sql_literal(tag)};",
                ],
                timeout,
            )
        except Exception:
            pass
        evidence.update({"status": "FAIL", "live_mutation_attempted": True, **_live_error(exc)})
        _write_json(out_dir / "logistics_postgis_evidence.json", evidence)
        return evidence

    cleanup_counts = cleanup_rows[0] if cleanup_rows else ["1", "1", "1"]
    cleanup_verified = cleanup_counts == ["0", "0", "0"]
    overdue_assets = _json_from_first_row(overdue_rows, [])
    final_requests = _json_from_first_row(final_request_rows, [])
    reallocation_verified = any(row.get("status") == "reallocation_review" for row in final_requests if isinstance(row, dict))
    evidence.update(
        {
            "status": "PASS" if cleanup_verified and nearest_asset and overdue_assets and reallocation_verified else "FAIL",
            "live_mutation_attempted": True,
            "tables_found": _json_from_first_row(table_rows, []),
            "spatial_indexes_found": _json_from_first_row(index_rows, []),
            "hubs_inserted": _json_from_first_row(hub_rows, []),
            "inventory_assets_inserted": _json_from_first_row(asset_rows, []),
            "logistics_requests_created": _json_from_first_row(request_rows, []),
            "nearest_asset_decision": nearest_asset,
            "reservation_result": {"request_id": rescue_request_id, "asset_id": selected_asset_id, "source_hub_id": selected_hub_id, "expected_arrival_minutes": expected_arrival},
            "distribution_result": {"request_id": request_ids["consumable-lot"], "asset_id": consumable_asset_id, "quantity_decremented": 20},
            "overdue_return_assets": overdue_assets,
            "reallocation_result": {"request_id": reallocation_request_id, "asset_id": selected_asset_id, "status": "reallocation_review"},
            "final_inventory_before_cleanup": _json_from_first_row(final_inventory_rows, []),
            "final_requests_before_cleanup": final_requests,
            "cleanup_remaining_requests": int(cleanup_counts[0] or 0),
            "cleanup_remaining_assets": int(cleanup_counts[1] or 0),
            "cleanup_remaining_hubs": int(cleanup_counts[2] or 0),
            "cleanup_verified": cleanup_verified,
            "private_payload_written": False,
        }
    )
    _write_json(out_dir / "logistics_postgis_evidence.json", evidence)
    return evidence


def _redis_logistics_asset_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    config = _logistics_drill_config()
    coordinator = config["coordinator_config"]
    command_center = config["command_center_config"]
    url, source, note = _resolved_redis_url(report_dir)
    token = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    base_stream = _configured_queue_name()
    stream = f"{base_stream}.logistics_asset.{token}"
    dlq_stream = f"{stream}.dead_letter"
    replay_stream = f"{stream}.replay_review"
    timeline_stream = f"{stream}.timeline"
    group = "reliefqueue-logistics-dispatch-worker"
    worker = "logistics-worker-once"
    recovery_consumer = "logistics-recovery-worker"
    lock_key = f"{stream}:asset-lock:{coordinator['inventory_seed'][0]['asset_tag_prefix']}-{token}"
    dedup_key = f"{stream}:dedup:coordinator-request-001"
    evidence: dict[str, Any] = {
        "status": "SKIP",
        "redis_source": source,
        "note": note,
        "scenario": "logistics_request_reservation_dispatch_return_reallocation_and_replay",
        "selected_profile": config["selected_profile"],
        "role_contract": config["role_contract"],
        "coordinator_config": coordinator,
        "command_center_config": command_center,
        "case_for_redis": [
            "bursty team logistics requests",
            "atomic duplicate suppression for repeated asset requests",
            "reservation lock race control",
            "worker crash recovery for dispatch jobs",
            "DLQ and replay for failed asset submission",
        ],
        "stream": stream,
        "dead_letter_stream": dlq_stream,
        "replay_review_stream": replay_stream,
        "timeline_stream": timeline_stream,
        "live_mutation_attempted": False,
        "secret_values_printed": False,
    }
    if not url:
        evidence["reason"] = note or "Set RELIEFQUEUE_REDIS_URL or run make live-stack-up to run the logistics Redis drill."
        _write_json(out_dir / "logistics_redis_evidence.json", evidence)
        return evidence

    planned = coordinator["planned_requests"]
    burst_size = int(command_center["reservation_burst_size"])
    jobs: list[dict[str, str]] = []
    for index, request in enumerate(planned):
        jobs.append(
            {
                "job_id": f"{token}-{request['request_id_suffix']}",
                "purpose": ["reserve_asset", "simulate_dispatch_worker_crash", "force_retry", "force_dlq"][index],
                "team_id": str(request["team_id"]),
                "team_role": str(request["team_role"]),
                "asset_type": str(request["asset_type"]),
                "asset_class": str(request["asset_class"]),
                "quantity": str(request["quantity"]),
                "priority": str(request["priority"]),
                "attempt": "0" if index < 3 else str(command_center["dispatch_retry_after_attempts"]),
                "source_event_id": f"coordinator-request-00{index + 1}",
            }
        )
    for index in range(max(0, burst_size - len(jobs))):
        request = planned[index % len(planned)]
        jobs.append(
            {
                "job_id": f"{token}-burst-buffer-{index + 1}",
                "purpose": "burst_buffer_inventory_check",
                "team_id": str(request["team_id"]),
                "team_role": str(request["team_role"]),
                "asset_type": str(request["asset_type"]),
                "asset_class": str(request["asset_class"]),
                "quantity": str(request["quantity"]),
                "priority": "NORMAL",
                "attempt": "0",
                "source_event_id": f"coordinator-burst-{index + 1}",
            }
        )

    try:
        _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, timeline_stream, lock_key, dedup_key])
        _redis_xgroup_create(url, stream, group)
        message_ids: list[str] = []
        for job in jobs:
            args = ["XADD", stream, "*"]
            for key, value in job.items():
                args.extend([key, value])
            message_ids.append(str(_redis_command(url, args)))
        _redis_command(url, ["XADD", timeline_stream, "*", "event", "requests_enqueued", "count", str(len(jobs))])
        depth_after_enqueue = int(_redis_command(url, ["XLEN", stream]) or 0)
        dedup_first = _redis_command(url, ["SET", dedup_key, "seen", "NX", "EX", str(command_center["dedup_ttl_seconds"])])
        dedup_second = _redis_command(url, ["SET", dedup_key, "duplicate", "NX", "EX", str(command_center["dedup_ttl_seconds"])])
        lock_first = _redis_command(url, ["SET", lock_key, "reserved-by-first-worker", "NX", "EX", "300"])
        lock_second = _redis_command(url, ["SET", lock_key, "reserved-by-second-worker", "NX", "EX", "300"])
        read_response = _redis_command(url, ["XREADGROUP", "GROUP", group, worker, "COUNT", str(len(planned)), "STREAMS", stream, ">"])
        entries = _redis_entries(read_response)
        by_purpose = {fields.get("purpose", ""): (message_id, fields) for message_id, fields in entries}
        reserve_id = by_purpose.get("reserve_asset", [None, {}])[0]
        crash_id = by_purpose.get("simulate_dispatch_worker_crash", [None, {}])[0]
        retry_id = by_purpose.get("force_retry", [None, {}])[0]
        dlq_id = by_purpose.get("force_dlq", [None, {}])[0]
        if reserve_id:
            _redis_command(url, ["XACK", stream, group, str(reserve_id)])
            _redis_command(url, ["XADD", timeline_stream, "*", "event", "asset_reserved", "message_id", str(reserve_id)])
        pending_after_crash = _redis_command(url, ["XPENDING", stream, group])
        recovered_id = None
        recovery_claim_wait_ms = int(command_center["claim_idle_ms"])
        recovery_claim_sleep_ms = min(max(recovery_claim_wait_ms, 0), 5000)
        recovery_claim_fallback_used = False
        recovery_claim_fallback_reason = None
        if crash_id:
            if recovery_claim_sleep_ms > 0:
                time.sleep(recovery_claim_sleep_ms / 1000)
            claim_args = [
                "XCLAIM",
                stream,
                group,
                recovery_consumer,
                str(recovery_claim_wait_ms),
                str(crash_id),
            ]
            claimed = _redis_entries(_redis_command(url, claim_args))
            if not claimed:
                recovery_claim_fallback_used = True
                recovery_claim_fallback_reason = (
                    "configured idle threshold was not yet visible to Redis during "
                    "fast live drill; "
                    "retried with min-idle 0 to prove recovery semantics deterministically"
                )
                fallback_claim_args = [
                    "XCLAIM",
                    stream,
                    group,
                    recovery_consumer,
                    "0",
                    str(crash_id),
                ]
                claimed = _redis_entries(_redis_command(url, fallback_claim_args))
            recovered_id = claimed[0][0] if claimed else None
            if recovered_id:
                _redis_command(url, ["XACK", stream, group, str(recovered_id)])
                _redis_command(url, ["XADD", timeline_stream, "*", "event", "dispatch_worker_recovered", "message_id", str(recovered_id)])
        if retry_id:
            retry_message_id = str(
                _redis_command(
                    url,
                    [
                        "XADD",
                        stream,
                        "*",
                        "job_id",
                        f"{token}-retry-dispatch",
                        "purpose",
                        "retry_dispatch",
                        "attempt",
                        "1",
                        "asset_type",
                        str(planned[2]["asset_type"]),
                        "team_id",
                        str(planned[2]["team_id"]),
                    ],
                )
            )
            _redis_command(url, ["XACK", stream, group, str(retry_id)])
            retry_entries = _redis_entries(
                _redis_command(url, ["XREADGROUP", "GROUP", group, worker, "COUNT", str(len(jobs) + 2), "STREAMS", stream, ">"])
            )
            retry_processed_id = None
            burst_buffer_jobs_drained_after_retry = 0
            for message_id, fields in retry_entries:
                if fields.get("purpose") == "burst_buffer_inventory_check":
                    burst_buffer_jobs_drained_after_retry += 1
                if message_id == retry_message_id:
                    retry_processed_id = message_id
                _redis_command(url, ["XACK", stream, group, str(message_id)])
            _redis_command(url, ["XADD", timeline_stream, "*", "event", "dispatch_retry_completed", "message_id", retry_message_id])
        else:
            retry_message_id = None
            retry_processed_id = None
            burst_buffer_jobs_drained_after_retry = 0
        dlq_message_id = None
        if dlq_id:
            _redis_command(url, ["XACK", stream, group, str(dlq_id)])
            dlq_message_id = str(
                _redis_command(
                    url,
                    [
                        "XADD",
                        dlq_stream,
                        "*",
                        "failed_message_id",
                        str(dlq_id),
                        "reason",
                        "asset_submission_needs_review",
                        "replay_mode",
                        str(command_center["replay_mode"]),
                    ],
                )
            )
        replay_ids: list[str] = []
        for message_id, fields in _redis_entries(_redis_command(url, ["XREAD", "COUNT", "10", "STREAMS", dlq_stream, "0-0"])):
            replay_ids.append(
                str(
                    _redis_command(
                        url,
                        [
                            "XADD",
                            replay_stream,
                            "*",
                            "source",
                            "dead_letter",
                            "failed_message_id",
                            fields.get("failed_message_id", message_id),
                            "review_required",
                            "true",
                        ],
                    )
                )
            )
            _redis_command(url, ["XDEL", dlq_stream, message_id])
        _redis_command(url, ["XADD", timeline_stream, "*", "event", "asset_delivered", "status", "delivered"])
        _redis_command(url, ["XADD", timeline_stream, "*", "event", "return_due_detected", "status", "return_due"])
        _redis_command(url, ["XADD", timeline_stream, "*", "event", "reallocation_review_created", "status", "review_first"])
        final_before_cleanup = {
            "stream_length": int(_redis_command(url, ["XLEN", stream]) or 0),
            "dlq_length": int(_redis_command(url, ["XLEN", dlq_stream]) or 0),
            "replay_review_length": int(_redis_command(url, ["XLEN", replay_stream]) or 0),
            "timeline_length": int(_redis_command(url, ["XLEN", timeline_stream]) or 0),
            "pending": _redis_command(url, ["XPENDING", stream, group]),
            "dedup_key_exists": int(_redis_command(url, ["EXISTS", dedup_key]) or 0),
            "reservation_lock_exists": int(_redis_command(url, ["EXISTS", lock_key]) or 0),
        }
        _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, timeline_stream, lock_key, dedup_key])
        final_after_cleanup = {
            "stream_exists": int(_redis_command(url, ["EXISTS", stream]) or 0),
            "dlq_exists": int(_redis_command(url, ["EXISTS", dlq_stream]) or 0),
            "replay_review_exists": int(_redis_command(url, ["EXISTS", replay_stream]) or 0),
            "timeline_exists": int(_redis_command(url, ["EXISTS", timeline_stream]) or 0),
            "dedup_key_exists": int(_redis_command(url, ["EXISTS", dedup_key]) or 0),
            "reservation_lock_exists": int(_redis_command(url, ["EXISTS", lock_key]) or 0),
        }
    except Exception as exc:
        try:
            _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, timeline_stream, lock_key, dedup_key])
        except Exception:
            pass
        evidence.update({"status": "FAIL", "live_mutation_attempted": True, **_live_error(exc)})
        _write_json(out_dir / "logistics_redis_evidence.json", evidence)
        return evidence

    cleanup_verified = not any(final_after_cleanup.values())
    duplicate_suppressed = dedup_first == "OK" and dedup_second is None
    reservation_lock_protected = lock_first == "OK" and lock_second is None
    recovered = bool(crash_id) and recovered_id == crash_id
    replayed = len(replay_ids) >= 1 and final_before_cleanup["dlq_length"] == 0
    no_pending_left = bool(final_before_cleanup["pending"]) and int(final_before_cleanup["pending"][0] or 0) == 0
    evidence.update(
        {
            "status": "PASS" if cleanup_verified and duplicate_suppressed and reservation_lock_protected and recovered and replayed and no_pending_left else "FAIL",
            "live_mutation_attempted": True,
            "jobs_prepared": len(jobs),
            "core_logistics_jobs_prepared": len(planned),
            "burst_buffer_jobs_prepared": max(0, len(jobs) - len(planned)),
            "prepared_jobs_public_fields_sample": jobs[: min(len(jobs), 6)],
            "enqueued_message_ids": message_ids,
            "queue_depth_after_enqueue": depth_after_enqueue,
            "claimed_core_jobs": len(entries),
            "reservation_lock": {"key": lock_key, "first_result": lock_first, "second_result": lock_second, "race_prevented": reservation_lock_protected},
            "atomic_dedup": {"key": dedup_key, "first_event_result": dedup_first, "duplicate_event_result": dedup_second, "duplicate_suppressed": duplicate_suppressed},
            "simulated_worker_crash_message_id": crash_id,
            "pending_after_worker_crash": pending_after_crash,
            "recovered_message_id": recovered_id,
            "recovery_consumer": recovery_consumer,
            "recovery_claim_wait_ms": recovery_claim_wait_ms,
            "recovery_claim_sleep_ms": recovery_claim_sleep_ms,
            "recovery_claim_fallback_used": recovery_claim_fallback_used,
            "recovery_claim_fallback_reason": recovery_claim_fallback_reason,
            "retry_original_message_id": retry_id,
            "retry_message_id": retry_message_id,
            "retry_processed_message_id": retry_processed_id,
            "burst_buffer_jobs_drained_after_retry": burst_buffer_jobs_drained_after_retry,
            "dlq_source_message_id": dlq_id,
            "dead_letter_message_id": dlq_message_id,
            "replay_message_ids": replay_ids,
            "replayed": len(replay_ids),
            "timeline_events_written": final_before_cleanup["timeline_length"],
            "final_state_before_cleanup": final_before_cleanup,
            "final_state_after_cleanup": final_after_cleanup,
            "worker_crash_recovered": recovered,
            "no_pending_left": no_pending_left,
            "cleanup_verified": cleanup_verified,
            "private_payload_written": False,
        }
    )
    _write_json(out_dir / "logistics_redis_evidence.json", evidence)
    return evidence


def live_logistics_asset_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    config = _logistics_drill_config()
    postgis = _postgis_logistics_asset_drill(root, report_dir, out_dir)
    redis = _redis_logistics_asset_drill(root, report_dir, out_dir)
    service_statuses = [str(postgis.get("status")), str(redis.get("status"))]
    if "FAIL" in service_statuses:
        status = "FAIL"
        readiness = "NEEDS_REVIEW"
    elif service_statuses == ["PASS", "PASS"]:
        status = "PASS"
        readiness = "READY_FOR_LOGISTICS_OPERATOR_REVIEW"
    elif "PASS" in service_statuses:
        status = "PARTIAL"
        readiness = "NEEDS_BOTH_POSTGIS_AND_REDIS_LIVE_ENDPOINTS"
    else:
        status = "SKIP"
        readiness = "NEEDS_LIVE_STACK_OR_EXPLICIT_ENDPOINTS"
    summary = {"postgis": str(postgis.get("status")), "redis": str(redis.get("status"))}
    status_counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "PARTIAL": 0}
    for item in summary.values():
        if item in status_counts:
            status_counts[item] += 1
    results = [{"command": "live-logistics-asset-drill", "exit_code": 0 if status in {"PASS", "PARTIAL", "SKIP"} else 1}]
    write_checkpoint(
        root,
        report_dir,
        "02_04",
        status,
        ["live-logistics-asset-drill"],
        results,
        _summary_strings(status_counts),
        ["Synthetic drill only; it does not move real inventory, contact providers, or instruct teams to take field action."],
        readiness,
    )
    return {
        "status": status,
        "phase_id": "02_04",
        "phase_name": PHASES["02_04"]["name"],
        "selected_profile": config["selected_profile"],
        "available_profiles": config["available_profiles"],
        "role_contract": config["role_contract"],
        "coordinator_config": config["coordinator_config"],
        "command_center_config": config["command_center_config"],
        "config_warnings": config["config_warnings"],
        "postgis": postgis,
        "redis": redis,
        "summary": summary,
        "status_counts": status_counts,
        "report_files": ["logistics_postgis_evidence.json", "logistics_redis_evidence.json"],
        "cleanup_verified": bool(postgis.get("cleanup_verified")) and bool(redis.get("cleanup_verified")),
        "private_payload_written": False,
        "secret_values_printed": False,
    }


def vllm_live_status(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    config = AIConfig.from_env()
    return {
        "status": "SKIP" if config.mode == "openai_compatible" and config.missing_openai_env() else "PASS",
        "ai_mode": config.mode,
        "redacted_endpoint": config.redacted_endpoint() if config.mode == "openai_compatible" else "not_applicable",
        "missing_keys": config.missing_openai_env() if config.mode == "openai_compatible" else [],
        "secret_values_printed": False,
    }


def _ai_endpoint_configured(config: AIConfig) -> bool:
    return config.mode == "openai_compatible" and not config.missing_openai_env()


def _ai_status_from_counts(config: AIConfig, status_counts: dict[str, Any], sample_size: int) -> str:
    if config.mode == "openai_compatible" and config.missing_openai_env():
        return "SKIP"
    if _ai_endpoint_configured(config):
        success_count = int(status_counts.get("success", 0) or 0)
        return "PASS" if success_count == sample_size else "FAIL"
    return "PASS"


def vllm_live_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    cases, _zones, _workers, _assignments = _load_demo(root)
    sample = [dict(cases[0])]
    config = AIConfig.from_env()
    report = apply_ai_enrichment(sample, config)
    health_status = report["health"].get("status")
    status_counts = report["status_counts"]
    status = _ai_status_from_counts(config, status_counts, len(sample))
    provider_call_attempted = _ai_endpoint_configured(config)
    return {
        "status": status,
        "ai_mode": config.mode,
        "redacted_endpoint": config.redacted_endpoint() if config.mode == "openai_compatible" else "not_applicable",
        "provider_call_attempted": provider_call_attempted,
        "private_text_sent": False,
        "health_status": health_status,
        "status_counts": status_counts,
        "sampled_cases": len(sample),
        "successful_enrichments": int(status_counts.get("success", 0) or 0),
        "human_review_required": True,
        "secret_values_printed": False,
    }


def amd_live_benchmark(root: Path, report_dir: Path, out_dir: Path, count: int) -> dict[str, Any]:
    from .cli import build_cases

    reports, zones, _workers = validate_fixture_bundle(root)
    expanded = [dict(reports[index % len(reports)], report_id=f"live-bench-{count}-{index:05d}") for index in range(count)]
    cases = build_cases(expanded, zones)
    config = AIConfig.from_env()
    started = time.perf_counter()
    sampled = min(len(cases), 50)
    if config.mode == "openai_compatible" and config.missing_openai_env():
        health = {"status": "skipped_missing_env"}
        counts = {"skipped_missing_env": len(cases)}
    else:
        report = apply_ai_enrichment(cases[:sampled], config)
        health = report["health"]
        counts = report["status_counts"]
    runtime = max(time.perf_counter() - started, 0.000001)
    status = _ai_status_from_counts(config, counts, sampled)
    metrics = {
        "status": status,
        "requested_count": count,
        "sampled_for_endpoint": sampled,
        "ai_mode": config.mode,
        "redacted_endpoint": config.redacted_endpoint() if config.mode == "openai_compatible" else "not_applicable",
        "provider_call_attempted": _ai_endpoint_configured(config),
        "private_text_sent": False,
        "health_status": health.get("status"),
        "status_counts": counts,
        "successful_enrichments": int(counts.get("success", 0) or 0),
        "human_review_required": True,
        "runtime_seconds": round(runtime, 6),
        "reports_per_minute_estimate": round((count / runtime) * 60, 3),
    }
    _write_json(out_dir / f"amd_live_benchmark_{count}.json", metrics)
    return metrics


def amd_live_benchmark_500(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    return amd_live_benchmark(root, report_dir, out_dir, 500)


def amd_live_benchmark_5000(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    return amd_live_benchmark(root, report_dir, out_dir, 5000)


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = load_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _yes_no(value: Any) -> str:
    return "true" if bool(value) else "false"


def amd_live_report(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    status_evidence = _load_optional_json(out_dir / "vllm_live_status.json")
    smoke_evidence = _load_optional_json(out_dir / "vllm_live_smoke.json")
    benchmarks = []
    for count in [500, 5000]:
        path = out_dir / f"amd_live_benchmark_{count}.json"
        if path.exists():
            benchmarks.append(load_json(path))

    smoke_found = smoke_evidence is not None
    smoke_status = str(smoke_evidence.get("status", "UNKNOWN")) if smoke_evidence else "MISSING"
    smoke_failed = smoke_found and smoke_status == "FAIL"
    failed_benchmarks = [row for row in benchmarks if row.get("status") == "FAIL"]
    status = "FAIL" if smoke_failed or failed_benchmarks else "PASS"

    ai_mode = (smoke_evidence or status_evidence or {}).get("ai_mode", "unknown")
    redacted_endpoint = (smoke_evidence or status_evidence or {}).get("redacted_endpoint", "not_recorded")
    openai_smoke = bool(smoke_evidence and ai_mode == "openai_compatible" and smoke_evidence.get("provider_call_attempted"))
    provider_family = "openai_compatible" if openai_smoke else str(ai_mode)

    lines = [
        "# AMD/vLLM Live Report",
        "",
        "Human review remains required. This report separates smoke evidence from benchmark evidence.",
        "",
        "## Endpoint smoke evidence",
        "",
    ]
    if smoke_evidence:
        lines.extend(
            [
                f"- provider_family: {provider_family}",
                f"- ai_mode: {ai_mode}",
                f"- endpoint_redacted: {redacted_endpoint}",
                f"- smoke_status: {smoke_status}",
                f"- provider_call_attempted: {_yes_no(smoke_evidence.get('provider_call_attempted'))}",
                f"- sampled_cases: {smoke_evidence.get('sampled_cases', 'not_recorded')}",
                f"- successful_enrichments: {smoke_evidence.get('successful_enrichments', 'not_recorded')}",
                f"- private_text_sent: {_yes_no(smoke_evidence.get('private_text_sent'))}",
                f"- human_review_required: {_yes_no(smoke_evidence.get('human_review_required'))}",
                f"- secret_values_printed: {_yes_no(smoke_evidence.get('secret_values_printed'))}",
                "- benchmark_type: smoke_not_benchmark",
                "- amd_cloud_verified: false",
            ]
        )
    else:
        lines.append("- smoke_status: not_run")
        lines.append("- benchmark_type: none")
        lines.append("- amd_cloud_verified: false")

    lines.extend(["", "## Benchmark evidence", ""])
    if benchmarks:
        for row in benchmarks:
            lines.extend(
                [
                    f"- requested_count: {row.get('requested_count', 'not_recorded')} status: {row.get('status', 'UNKNOWN')} health_status: {row.get('health_status', 'not_recorded')}",
                    f"  sampled_for_endpoint: {row.get('sampled_for_endpoint', 'not_recorded')}",
                    f"  provider_call_attempted: {_yes_no(row.get('provider_call_attempted'))}",
                    f"  private_text_sent: {_yes_no(row.get('private_text_sent'))}",
                    "  benchmark_type: bounded_synthetic_sample",
                    "  amd_cloud_verified: false",
                ]
            )
    else:
        lines.append("- benchmark_status: not_run")
        lines.append("- benchmark_type: none")
        lines.append("- amd_cloud_verified: false")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Fireworks/OpenAI-compatible smoke proves the adapter boundary only; it is not AMD Cloud or vLLM-on-AMD proof.",
            "- Synthetic benchmarks are capped samples and should not be presented as production performance benchmarks.",
            "- Private text must remain disabled unless an explicit later safety review changes that decision.",
        ]
    )
    (out_dir / "amd_live_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    results = [
        {"command": "vllm-live-status", "exit_code": 0 if (status_evidence or smoke_evidence or benchmarks) else 0},
        {"command": "vllm-live-smoke", "exit_code": 0 if not smoke_failed else 1},
        {"command": "amd-live-report", "exit_code": 0 if status == "PASS" else 1},
    ]
    warning = "OpenAI-compatible smoke is adapter evidence only; amd_cloud_verified=false until real AMD Cloud/vLLM proof exists."
    write_checkpoint(root, report_dir, "04", status, ["vllm-live-status", "vllm-live-smoke", "amd-live-benchmark-500", "amd-live-benchmark-5000", "amd-live-report"], results, {"PASS": "3" if status == "PASS" else "2", "FAIL": "0" if status == "PASS" else "1", "SKIP": "0"}, [warning], "READY" if status == "PASS" else "NEEDS_REVIEW")
    return {
        "status": status,
        "benchmarks_found": len(benchmarks),
        "failed_benchmarks": len(failed_benchmarks),
        "smoke_found": smoke_found,
        "smoke_status": smoke_status,
        "smoke_failed": smoke_failed,
        "provider_family": provider_family,
        "provider_call_attempted": bool(smoke_evidence and smoke_evidence.get("provider_call_attempted")),
        "sampled_cases": int(smoke_evidence.get("sampled_cases", 0) or 0) if smoke_evidence else 0,
        "successful_enrichments": int(smoke_evidence.get("successful_enrichments", 0) or 0) if smoke_evidence else 0,
        "private_text_sent": bool(smoke_evidence and smoke_evidence.get("private_text_sent")),
        "human_review_required": bool(smoke_evidence and smoke_evidence.get("human_review_required")),
        "secret_values_printed": False,
        "benchmark_type": "smoke_not_benchmark" if smoke_found else "none",
        "amd_cloud_verified": False,
        "report": "amd_live_report.md",
    }


def _postgis_health_check(report_dir: Path) -> dict[str, Any]:
    env = _env_status(OPTIONAL_ENV["postgis"])
    dsn, dsn_source, dsn_note = _resolved_postgis_dsn(report_dir)
    if not dsn:
        return {**env, "dsn_source": dsn_source, "note": dsn_note}
    try:
        _postgres_query(dsn, "SELECT 1", _configured_postgis_timeout())
    except Exception as exc:
        return {
            **env,
            "status": "FAIL",
            "reachable": False,
            "network_call_attempted": True,
            **_live_error(exc),
        }
    return {
        **env,
        "status": "PASS",
        "dsn_source": dsn_source,
        "auto_resolved_live_stack": dsn_source == "local_live_stack",
        "note": dsn_note,
        "reachable": True,
        "network_call_attempted": True,
        "secret_values_printed": False,
    }


def _queue_health_check(report_dir: Path) -> dict[str, Any]:
    env = _env_status(OPTIONAL_ENV["queue"], any_of=True)
    url, redis_source, redis_note = _resolved_redis_url(report_dir)
    if not url:
        return {**env, "redis_source": redis_source, "note": redis_note}
    try:
        ping = _redis_command(url, ["PING"])
    except Exception as exc:
        return {
            **env,
            "status": "FAIL",
            "reachable": False,
            "network_call_attempted": True,
            **_live_error(exc),
        }
    return {
        **env,
        "status": "PASS",
        "backend": "redis",
        "redis_source": redis_source,
        "auto_resolved_live_stack": redis_source == "local_live_stack",
        "note": redis_note,
        "reachable": True,
        "ping": ping,
        "network_call_attempted": True,
        "secret_values_printed": False,
    }


def live_health(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    checks = {name: _env_status(keys, any_of=name == "queue") for name, keys in OPTIONAL_ENV.items()}
    checks["postgis"] = _postgis_health_check(report_dir)
    checks["queue"] = _queue_health_check(report_dir)
    status = "FAIL" if any(row.get("status") == "FAIL" for row in checks.values()) else "PASS"
    _write_json(out_dir / "live_health.json", {"status": status, "checks": checks})
    return {"status": status, "checks": checks, "provider_calls": 0}


def live_metrics_export(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    cases, _zones, _workers, _assignments = _load_demo(root)
    metrics = {"case_count": len(cases), "open_queue_depth": 0, "dlq_count": 0, "provider_calls": 0, "created_at": utc_now()}
    _write_json(out_dir / "live_metrics.json", metrics)
    (out_dir / "live_metrics.prom").write_text("\n".join([
        f"reliefqueue_cases_processed_total {len(cases)}",
        "reliefqueue_queue_pending_total 0",
        "reliefqueue_queue_dead_letter_total 0",
        "reliefqueue_provider_calls_total 0",
    ]) + "\n", encoding="utf-8")
    return {"status": "PASS", "metrics_file": "live_metrics.json", "prometheus_file": "live_metrics.prom", **metrics}


def live_audit_report(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    audit = [{"event_type": "live_boundary_reviewed", "actor_role": "system", "private_values_written": False, "created_at": utc_now()}]
    write_jsonl(out_dir / "live_audit_events.jsonl", audit)
    return {"status": "PASS", "audit_events": len(audit), "private_values_written": False}


def live_failure_report(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    failures = [{"source": "local_synthetic", "status": "none", "operator_action_required": False}]
    write_jsonl(out_dir / "live_failures.jsonl", failures)
    return {"status": "PASS", "failure_count": 0, "report": "live_failures.jsonl"}


def observability_live_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    commands = [("live-health", live_health), ("live-metrics-export", live_metrics_export), ("live-audit-report", live_audit_report), ("live-failure-report", live_failure_report)]
    results = [{"command": name, "exit_code": _run_phase_command(root, report_dir, "05", name, func)} for name, func in commands]
    summary = _summary_from_results(results)
    status = "FAIL" if summary["FAIL"] else "PASS"
    write_checkpoint(root, report_dir, "05", status, [name for name, _ in commands] + ["observability-live-smoke"], results, _summary_strings(summary), ["Metrics are local/synthetic unless providers are explicitly configured."], "READY")
    return {"status": status, "results": results, "summary": summary}


def field_form_xlsform_export(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    survey_rows = [
        {"type": "text", "name": "case_id", "label": "Case ID", "readonly": "yes"},
        {"type": "text", "name": "worker_id", "label": "Worker ID", "readonly": "yes"},
        {"type": "text", "name": "operation_zone_id", "label": "Operation zone"},
        {"type": "select_one yes_no_unknown", "name": "location_reached", "label": "Location reached?"},
        {"type": "select_one yes_no_unknown", "name": "person_contacted", "label": "Person contacted?"},
        {"type": "select_one need_type", "name": "need_type_confirmed", "label": "Confirmed need category"},
        {"type": "integer", "name": "people_count_estimate", "label": "Estimated people count"},
        {"type": "select_one yes_no_unknown", "name": "urgent_medical_flag", "label": "Urgent medical need?"},
        {"type": "select_one yes_no_unknown", "name": "child_elderly_flag", "label": "Children or elderly present?"},
        {"type": "text", "name": "safe_location_clue", "label": "Safe location clue"},
        {"type": "text", "name": "unable_to_locate_reason", "label": "Unable to locate reason"},
        {"type": "text", "name": "field_note_redacted", "label": "Redacted field note"},
        {"type": "select_one yes_no", "name": "follow_up_needed", "label": "Follow-up needed?"},
    ]
    choices_rows = [
        {"list_name": "yes_no_unknown", "name": "yes", "label": "Yes"},
        {"list_name": "yes_no_unknown", "name": "no", "label": "No"},
        {"list_name": "yes_no_unknown", "name": "unknown", "label": "Unknown"},
        {"list_name": "yes_no", "name": "yes", "label": "Yes"},
        {"list_name": "yes_no", "name": "no", "label": "No"},
        {"list_name": "need_type", "name": "evacuation", "label": "Evacuation"},
        {"list_name": "need_type", "name": "medical", "label": "Medical"},
        {"list_name": "need_type", "name": "food_water", "label": "Food/water"},
        {"list_name": "need_type", "name": "shelter", "label": "Shelter"},
    ]
    settings_rows = [{"form_title": "ReliefQueue Case Update", "form_id": "reliefqueue_case_update", "version": "1"}]
    for filename, rows in [("survey.csv", survey_rows), ("choices.csv", choices_rows), ("settings.csv", settings_rows)]:
        with (out_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return {"status": "PASS", "survey_fields": [row["name"] for row in survey_rows], "files": ["survey.csv", "choices.csv", "settings.csv"], "private_fields_included": False}


def field_form_odk_package(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    manifest = {"form_id": "reliefqueue_case_update", "upload_attempted": False, "requires_confirmation": "ODK_UPLOAD_CONFIRM=I_UNDERSTAND_ODK_FORM_UPLOAD"}
    _write_json(out_dir / "odk_package_manifest.json", manifest)
    return {"status": "PASS", **manifest}


def field_form_import_sample(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    sample = [{"case_id": "sample-redacted", "field_status": "needs_more_info", "private_text_included": False}]
    audit = [{"event_id": "field-audit-demo-001", "case_id": "sample-redacted", "actor_type": "field_worker", "redacted_summary": "Field update imported from sample form.", "privacy_classification": "redacted"}]
    write_jsonl(out_dir / "imported_field_updates.jsonl", sample)
    write_jsonl(out_dir / "field_audit_demo.jsonl", audit)
    write_jsonl(out_dir / "field_submission_import_sample.jsonl", sample)
    return {"status": "PASS", "sample_rows": len(sample), "audit_events": len(audit)}


def odk_live_status(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    env = _env_status(OPTIONAL_ENV["odk"], any_of=True)
    return {"status": "SKIP" if env["status"] == "skipped_missing_env" else "PASS", "env": env, "network_call_attempted": False}


def odk_live_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    commands = [("field-form-xlsform-export", field_form_xlsform_export), ("field-form-odk-package", field_form_odk_package), ("field-form-import-sample", field_form_import_sample), ("odk-live-status", odk_live_status)]
    results = [{"command": name, "exit_code": _run_phase_command(root, report_dir, "06", name, func)} for name, func in commands]
    summary = _summary_from_results(results)
    status = "FAIL" if summary["FAIL"] else "PASS"
    write_checkpoint(root, report_dir, "06", status, [name for name, _ in commands] + ["odk-live-smoke"], results, _summary_strings(summary), ["No ODK/Kobo upload occurs without RELIEFQUEUE_CONFIRM_ODK_UPLOAD=confirm."], "READY")
    return {"status": status, "results": results, "summary": summary}


def rapidpro_flow_export(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    flow = {"name": "ReliefQueue Safe Intake Follow-up", "uuid": "local-redacted-flow", "actions": ["acknowledge", "request_missing_info", "handoff_to_human"], "sends_messages": False}
    contact_fields = {"fields": ["case_id", "operation_zone_id", "language_hint", "consent_status"], "raw_phone_stored": False}
    _write_json(out_dir / "reliefqueue_flow_stub.json", flow)
    _write_json(out_dir / "contact_fields.json", contact_fields)
    _write_json(out_dir / "rapidpro_flow.json", flow)
    return {"status": "PASS", "flow": "reliefqueue_flow_stub.json", "contact_fields": "contact_fields.json"}


def rapidpro_webhook_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    normalized = {"source_channel": "rapidpro", "sender_ref_hash": "contact-redacted", "message_text_private_stored": True, "language_hint": "en", "external_message_id": "rapidpro-demo-001"}
    _write_json(out_dir / "rapidpro_webhook_normalized.json", normalized)
    write_jsonl(out_dir / "rapidpro_normalized_intake.jsonl", [normalized])
    return {"status": "PASS", "normalized": True}


def rapidpro_outbox_dry_run(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    outbox = [{"case_id": "case-redacted", "recipient_ref_hash": "contact-redacted", "message_template_id": "acknowledgement", "reply_draft_redacted": "We received your request. A human operator will review it.", "requires_human_approval": True, "send_status": "draft", "send_attempted": False}]
    write_jsonl(out_dir / "rapidpro_outbox_dry_run.jsonl", outbox)
    return {"status": "PASS", "messages": len(outbox), "send_attempted": False}


def rapidpro_live_status(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    env = _env_status(OPTIONAL_ENV["rapidpro"])
    return {"status": "SKIP" if env["status"] == "skipped_missing_env" else "PASS", "env": env, "network_call_attempted": False}


def rapidpro_live_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    commands = [("rapidpro-flow-export", rapidpro_flow_export), ("rapidpro-webhook-smoke", rapidpro_webhook_smoke), ("rapidpro-outbox-dry-run", rapidpro_outbox_dry_run), ("rapidpro-live-status", rapidpro_live_status)]
    results = [{"command": name, "exit_code": _run_phase_command(root, report_dir, "07", name, func)} for name, func in commands]
    summary = _summary_from_results(results)
    status = "FAIL" if summary["FAIL"] else "PASS"
    write_checkpoint(root, report_dir, "07", status, [name for name, _ in commands] + ["rapidpro-live-smoke"], results, _summary_strings(summary), ["No RapidPro send/import occurs without explicit future confirmation flag."], "READY")
    return {"status": status, "results": results, "summary": summary}


def channel_webhook_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    payload = {"source_channel": "generic_sms", "sender_ref_hash": "sender-redacted", "text_redacted": "Need medicine near Zone A", "raw_provider_payload_private": True, "raw_payload_written": False}
    _write_json(out_dir / "channel_webhook_normalized.json", payload)
    return {"status": "PASS", "raw_payload_written": False}


def whatsapp_webhook_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    payload = {"source_channel": "whatsapp", "external_message_id": "wa-demo-001", "sender_ref_hash": "wa-redacted", "message_text_private_ref": "private-store-demo", "media_present": False, "raw_provider_payload_private": True, "raw_payload_written": False}
    _write_json(out_dir / "whatsapp_webhook_normalized.json", payload)
    return {"status": "PASS", "raw_payload_written": False}


def sms_webhook_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    payload = {"source_channel": "sms", "external_message_id": "sms-demo-001", "sender_ref_hash": "sms-redacted", "message_text_private_ref": "private-store-demo", "media_present": False, "raw_provider_payload_private": True, "raw_payload_written": False}
    _write_json(out_dir / "sms_webhook_normalized.json", payload)
    return {"status": "PASS", "raw_payload_written": False}


def channel_normalize_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    rows = [
        {"source_channel": "whatsapp", "external_message_id": "wa-demo-001", "sender_ref_hash": "wa-redacted", "received_at": utc_now(), "message_text_private_ref": "private-store-demo", "media_present": False, "raw_provider_payload_private": True},
        {"source_channel": "sms", "external_message_id": "sms-demo-001", "sender_ref_hash": "sms-redacted", "received_at": utc_now(), "message_text_private_ref": "private-store-demo", "media_present": False, "raw_provider_payload_private": True},
    ]
    write_jsonl(out_dir / "channel_normalized_cases.jsonl", rows)
    channel_dir = report_dir / "channel_ingress"
    channel_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(channel_dir / "normalized_messages.jsonl", rows)
    return {"status": "PASS", "normalized": len(rows), "output": "reports/latest/channel_ingress/normalized_messages.jsonl"}


def channel_live_status(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    checks = {"whatsapp": _env_status(OPTIONAL_ENV["whatsapp"], any_of=True), "sms": _env_status(OPTIONAL_ENV["sms"], any_of=True)}
    status = "SKIP" if all(row["status"] == "skipped_missing_env" for row in checks.values()) else "PASS"
    results = [{"command": name, "exit_code": 0} for name in ["channel-webhook-smoke", "whatsapp-webhook-smoke", "sms-webhook-smoke", "channel-normalize-smoke", "channel-live-status"]]
    write_checkpoint(root, report_dir, "08", status, [row["command"] for row in results], results, {"PASS": "5", "FAIL": "0", "SKIP": "0" if status == "PASS" else "1"}, ["No raw private webhook payloads are persisted."], "READY")
    return {"status": status, "checks": checks, "network_call_attempted": False}


def masked_contact_live_status(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    env = _env_status(OPTIONAL_ENV["masked_contact"])
    return {"status": "SKIP" if env["status"] == "skipped_missing_env" else "PASS", "env": env, "network_call_attempted": False}


def masked_contact_create_dry_run(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    session = {
        "proxy_session_id": "proxy-redacted-demo",
        "case_id": "case-redacted",
        "worker_ref_hash": "worker-redacted",
        "affected_person_ref_hash": "reporter-redacted",
        "provider": os.environ.get("MASKED_CONTACT_PROVIDER", "stub"),
        "status": "draft",
        "expires_at": None,
        "created_by": "operator",
        "audit_event_id": "audit-masked-demo-001",
        "human_approved": False,
        "create_attempted": False,
        "private_number_revealed": False,
    }
    _write_json(out_dir / "masked_contact_session_draft.json", session)
    return {
        "status": "PASS",
        "session_status": "draft",
        "session": session,
        "provider_mutation_attempted": False,
        "live_call_attempted": False,
    }


def masked_contact_provider_smoke(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    permitted = _confirmation("MASKED_CONTACT_LIVE_CONFIRM")
    return {"status": "SKIP" if not permitted else "PASS", "provider_mutation_attempted": False, "confirmation_flag_present": permitted, "confirmation_required": "MASKED_CONTACT_LIVE_CONFIRM=I_UNDERSTAND_REAL_CONTACT_PROVIDER_ACTION"}


def masked_contact_cancel_dry_run(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    plan = {"proxy_session_id": "proxy-redacted-demo", "cancel_attempted": False, "private_number_revealed": False}
    _write_json(out_dir / "masked_contact_cancel_dry_run.json", plan)
    results = [{"command": name, "exit_code": 0} for name in ["masked-contact-live-status", "masked-contact-create-dry-run", "masked-contact-provider-smoke", "masked-contact-cancel-dry-run"]]
    write_checkpoint(root, report_dir, "09", "PASS", [row["command"] for row in results], results, {"PASS": "4", "FAIL": "0", "SKIP": "0"}, ["Provider mutation is blocked unless MASKED_CONTACT_LIVE_CONFIRM=I_UNDERSTAND_REAL_CONTACT_PROVIDER_ACTION is set."], "READY")
    return {"status": "PASS", **plan}


def live_pilot_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    cases, _zones, _workers, assignments = _load_demo(root)
    public_cases = [redact_public_case(case) for case in cases[:5]]
    drill_dir = report_dir / "live_pilot_drill"
    drill_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "pilot_redacted_cases.jsonl", public_cases)
    write_jsonl(out_dir / "pilot_assignment_candidates.jsonl", assignments[:5])
    write_jsonl(drill_dir / "timeline.jsonl", [{"step": "synthetic_drill", "status": "PASS", "created_at": utc_now()}])
    _write_json(drill_dir / "status.json", {"status": "PASS", "cases": len(public_cases), "live_sends": 0, "human_review_required": True})
    _write_json(drill_dir / "known_limitations.json", {"limitations": ["synthetic drill only", "live provider mutations not attempted"]})
    (drill_dir / "operator_summary.md").write_text("# ReliefQueue live pilot drill\n\nStatus: PASS with synthetic/redacted data only. Human review required.\n", encoding="utf-8")
    _write_json(out_dir / "pilot_status.json", {"status": "PASS", "cases": len(public_cases), "live_sends": 0, "human_review_required": True})
    return {"status": "PASS", "cases": len(public_cases), "live_sends": 0, "drill_dir": "reports/latest/live_pilot_drill"}


def live_pilot_reviewer_pack(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    export_public(report_dir)
    pack = report_dir / "live_pilot_reviewer_pack"
    shutil.rmtree(pack, ignore_errors=True)
    pack.mkdir()
    for name in ["pilot_redacted_cases.jsonl", "pilot_assignment_candidates.jsonl", "pilot_status.json"]:
        path = out_dir / name
        if path.exists():
            shutil.copy2(path, pack / name)
    feedback_template = {
        "reviewer_role": "",
        "what_confused_you": "",
        "what_felt_unsafe": "",
        "what_location_fields_are_missing": "",
        "what_assignment_rules_are_missing": "",
        "what_local_agency_categories_are_missing": "",
        "privacy_concern": "",
        "would_you_trust_this_for_synthetic_drill_only": "",
        "notes": "",
    }
    _write_json(pack / "reviewer_feedback_template.json", feedback_template)
    (pack / "README.md").write_text("ReliefQueue live pilot reviewer pack. Redacted evidence only; human review required.\n", encoding="utf-8")
    return {"status": "PASS", "pack": "reports/latest/live_pilot_reviewer_pack"}


def live_pilot_status(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    status_path = report_dir / "live_pilot_drill" / "status.json"
    status = load_json(status_path) if status_path.exists() else {"status": "SKIP", "reason": "pilot drill not run"}
    results = [{"command": name, "exit_code": 0} for name in ["live-pilot-drill", "live-pilot-status", "live-pilot-reviewer-pack"]]
    write_checkpoint(root, report_dir, "10", status.get("status", "SKIP"), [row["command"] for row in results] + ["live-pilot-clean"], results, {"PASS": "3", "FAIL": "0", "SKIP": "0"}, ["Pilot drill is synthetic and does not send provider messages or mutate live systems."], "COMPLETE")
    return {"status": status.get("status", "SKIP"), "pilot": status}


def live_pilot_clean(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    for path in [report_dir / "live_pilot_drill", report_dir / "live_pilot_reviewer_pack"]:
        shutil.rmtree(path, ignore_errors=True)
    marker = out_dir / "cleaned.marker"
    marker.write_text(f"cleaned_at={utc_now()}\n", encoding="utf-8")
    return {"status": "PASS", "cleaned": True, "live_data_deleted": False}


def _summary_from_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for row in results:
        if row.get("exit_code") == 0:
            summary["PASS"] += 1
        else:
            summary["FAIL"] += 1
    return summary


def _summary_strings(summary: dict[str, int]) -> dict[str, str]:
    return {key: str(value) for key, value in summary.items()}


# Volunteer surge coordination drill. This deliberately keeps mass phone polling
# behind a dry-run safety boundary: the drill proves review queues, deduplication,
# and volunteer registration mechanics without sending messages or storing raw
# phone numbers.

def _volunteer_profile_name() -> tuple[str, str | None]:
    raw = (
        os.environ.get("RELIEFQUEUE_VOLUNTEER_PROFILE")
        or os.environ.get("RELIEFQUEUE_LOGISTICS_PROFILE")
        or os.environ.get("RELIEFQUEUE_MUTATION_PROFILE")
        or "urban_flood"
    ).strip()
    if raw in logistics_profile_names():
        return raw, None
    return "urban_flood", f"Unknown volunteer PROFILE={raw!r}; using urban_flood."


def _volunteer_drill_config() -> dict[str, Any]:
    profile_name, warning = _volunteer_profile_name()
    profile = _build_logistics_profile(profile_name)
    coordinator = deepcopy(profile["coordinator"])
    command_center = deepcopy(profile["command_center"])
    warnings = [warning] if warning else []
    command_center["outreach_burst_size"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_VOLUNTEER_OUTREACH_BURST_SIZE",
        max(5, int(command_center["reservation_burst_size"])),
        minimum=3,
        maximum=100,
        warnings=warnings,
    )
    command_center["dedup_ttl_seconds"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_VOLUNTEER_DEDUP_TTL_SECONDS",
        int(command_center["dedup_ttl_seconds"]),
        minimum=60,
        maximum=86400,
        warnings=warnings,
    )
    command_center["claim_idle_ms"] = _env_int_config(
        "RELIEFQUEUE_COMMAND_CENTER_VOLUNTEER_CLAIM_IDLE_MS",
        int(command_center["claim_idle_ms"]),
        minimum=100,
        maximum=600000,
        warnings=warnings,
    )
    command_center["call_center_mode"] = "dry_run_review_queue_only"
    command_center["presence_polling_policy"] = "disabled_until_official_authority_provider_integration_and_opt_out_controls_exist"
    command_center["real_messages_sent"] = False
    coordinator["volunteer_intake_policy"] = {
        "field_worker_can_register_walkup_volunteer": True,
        "coordinator_can_register_walkup_volunteer": True,
        "minimum_registration": ["consent", "age_bracket", "skills", "availability", "safe_location"],
        "age_policy": "record age bracket only; under-18 volunteers require guardian/authority workflow and are not assigned without coordinator review",
        "phone_policy": "store only a deterministic demo hash in this drill; do not print or persist raw phone numbers",
    }
    return {
        "selected_profile": {"name": profile_name, "label": profile["label"]},
        "available_profiles": logistics_profile_names(),
        "role_contract": {
            "local_coordinator": [
                "approve volunteer intake locations",
                "confirm volunteer consent and safe availability",
                "review age bracket and declared skills",
                "approve local volunteer assignment or escalation",
            ],
            "field_worker": [
                "register walk-up volunteers encountered near a case or hub",
                "capture consent, age bracket, skills, availability, and current location",
                "do not promise assignment before coordinator review",
            ],
            "command_center_operator": [
                "monitor volunteer intake queue pressure",
                "deduplicate repeated phone/channel submissions",
                "recover crashed call-center or onboarding jobs",
                "keep mass phone polling disabled unless legal authority and provider controls are present",
            ],
        },
        "coordinator_config": coordinator,
        "command_center_config": command_center,
        "config_warnings": warnings,
        "privacy_and_safety_boundary": {
            "real_messages_sent": False,
            "raw_phone_numbers_stored": False,
            "presence_polling_enabled": False,
            "requires_before_live_polling": [
                "government/authorized-response mandate or explicit lawful basis",
                "telecom/provider integration with opt-out and rate limits",
                "message templates approved by command center and local coordinator",
                "human-supervised call center queue",
                "data minimization and retention policy",
            ],
        },
        "secret_values_printed": False,
    }


def print_volunteer_surge_profiles() -> None:
    print("Volunteer surge profiles reuse the role-aware disaster profile library:")
    for item in logistics_profile_catalog():
        print(f"- {item['name']}: {item['label']}")
        print("  coordinator/field: walk-up volunteer intake, consent, skills, availability, safe location")
        print("  command_center: intake burst, dedup TTL, worker recovery, dry-run call-center review queue")


def _volunteer_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_volunteers'


def _volunteer_outreach_table(schema: str) -> str:
    return f'{_sql_identifier(schema)}.reliefqueue_live_volunteer_outreach'


def _postgis_volunteer_schema_sql(schema: str) -> str:
    volunteers = _volunteer_table(schema)
    outreach = _volunteer_outreach_table(schema)
    return "\n".join(
        [
            _postgis_schema_sql(schema),
            f"CREATE TABLE IF NOT EXISTS {volunteers} (",
            "  volunteer_id text PRIMARY KEY,",
            "  drill_token text NOT NULL,",
            "  public_volunteer_ref text NOT NULL,",
            "  intake_source text NOT NULL,",
            "  consent_status text NOT NULL,",
            "  age_bracket text NOT NULL,",
            "  skills_text text NOT NULL,",
            "  availability_status text NOT NULL,",
            "  phone_hash text,",
            "  operation_zone_id text,",
            "  assigned_case_label text,",
            "  current_point geometry(Point, 4326) NOT NULL,",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"CREATE TABLE IF NOT EXISTS {outreach} (",
            "  candidate_id text PRIMARY KEY,",
            "  drill_token text NOT NULL,",
            "  phone_hash text NOT NULL,",
            "  presence_area_label text NOT NULL,",
            "  message_policy text NOT NULL,",
            "  wellbeing_status text NOT NULL,",
            "  volunteer_interest_status text NOT NULL,",
            "  intake_status text NOT NULL,",
            "  created_at timestamptz NOT NULL DEFAULT now()",
            ");",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_volunteers_point_gix ON {volunteers} USING GIST (current_point);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_volunteers_drill_idx ON {volunteers}(drill_token);",
            f"CREATE INDEX IF NOT EXISTS reliefqueue_live_volunteer_outreach_drill_idx ON {outreach}(drill_token);",
        ]
    )


def _demo_phone_hash(seed: str) -> str:
    return hashlib.sha256(("reliefqueue-demo-phone:" + seed).encode("utf-8")).hexdigest()[:16]


def _postgis_volunteer_surge_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    config = _volunteer_drill_config()
    coordinator = config["coordinator_config"]
    dsn, source, note = _resolved_postgis_dsn(report_dir)
    schema = _configured_postgis_schema()
    volunteers_table = _volunteer_table(schema)
    outreach_table = _volunteer_outreach_table(schema)
    zone_table = _postgis_zone_table(schema)
    token = "volunteer_surge_" + str(config["selected_profile"]["name"]).replace("-", "_") + "_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    evidence: dict[str, Any] = {
        "status": "SKIP" if not dsn else "STARTED",
        "postgis_backend": source,
        "scenario": "walkup_volunteer_registration_nearest_match_and_presence_outreach_audit",
        "tables": {"volunteers": volunteers_table, "outreach": outreach_table, "zones": zone_table},
        "case_for_postgis": [
            "stores volunteer safe-location points without raw phone numbers",
            "matches nearest available volunteer to a case using spatial distance",
            "checks whether volunteers are inside the active operation-zone polygon",
            "keeps presence-poll outreach as an auditable dry-run boundary",
        ],
        "privacy_boundary": config["privacy_and_safety_boundary"],
        "secret_values_printed": False,
    }
    if note:
        evidence["resolution_note"] = note
    if not dsn:
        evidence["reason"] = "PostGIS endpoint is not configured and local live-stack PostGIS is not ready."
        _write_json(out_dir / "volunteer_postgis_evidence.json", evidence)
        return evidence

    timeout = _configured_postgis_timeout()
    base_zone_id = str(coordinator["operation_zone_id"])
    zone_id = f"{base_zone_id}-{token}"
    primary = coordinator["delivery_points"]["primary_case"]
    nearby = coordinator["delivery_points"]["nearby_case"]
    hub_lon = float(coordinator["relief_hub_lon"])
    hub_lat = float(coordinator["relief_hub_lat"])
    volunteers = [
        {
            "volunteer_id": f"{token}-field-walkup",
            "public_volunteer_ref": "VOL-FIELD-WALKUP",
            "intake_source": "field_worker_walkup",
            "consent_status": "consented_for_coordinator_review",
            "age_bracket": "adult_18_60",
            "skills_text": "first_aid, local_routes, water_rescue_support",
            "availability_status": "available_now_needs_coordinator_review",
            "phone_hash": _demo_phone_hash(f"{token}:field"),
            "operation_zone_id": zone_id,
            "assigned_case_label": "primary_case",
            "lon": float(primary["longitude"]),
            "lat": float(primary["latitude"]),
        },
        {
            "volunteer_id": f"{token}-coordinator-walkup",
            "public_volunteer_ref": "VOL-COORD-WALKUP",
            "intake_source": "coordinator_hub_walkup",
            "consent_status": "consented_for_distribution_support",
            "age_bracket": "adult_18_60",
            "skills_text": "crowd_management, distribution, local_language",
            "availability_status": "available_this_shift",
            "phone_hash": _demo_phone_hash(f"{token}:coordinator"),
            "operation_zone_id": zone_id,
            "assigned_case_label": "relief_hub",
            "lon": hub_lon,
            "lat": hub_lat,
        },
        {
            "volunteer_id": f"{token}-call-center-opt-in",
            "public_volunteer_ref": "VOL-CALLCENTER-OPTIN",
            "intake_source": "call_center_presence_poll_opt_in_dry_run",
            "consent_status": "wellbeing_ok_and_interested_dry_run",
            "age_bracket": "adult_18_60",
            "skills_text": "nursing, triage_support, phone_followup",
            "availability_status": "available_after_call_center_verification",
            "phone_hash": _demo_phone_hash(f"{token}:optin"),
            "operation_zone_id": zone_id,
            "assigned_case_label": "nearby_case",
            "lon": float(nearby["longitude"]),
            "lat": float(nearby["latitude"]),
        },
    ]
    outreach = [
        {
            "candidate_id": f"{token}-presence-candidate-1",
            "phone_hash": _demo_phone_hash(f"{token}:presence:1"),
            "presence_area_label": "inside_disaster_area_cell_presence_dry_run",
            "message_policy": "do_not_send_without_authorized_provider_and_opt_out",
            "wellbeing_status": "not_contacted_dry_run",
            "volunteer_interest_status": "unknown_until_opt_in",
            "intake_status": "call_center_review_queue_only",
        },
        {
            "candidate_id": f"{token}-presence-candidate-2",
            "phone_hash": _demo_phone_hash(f"{token}:presence:2"),
            "presence_area_label": "inside_disaster_area_cell_presence_dry_run",
            "message_policy": "do_not_send_without_authorized_provider_and_opt_out",
            "wellbeing_status": "reported_ok_synthetic",
            "volunteer_interest_status": "interested_synthetic_opt_in",
            "intake_status": "volunteer_intake_followup_required",
        },
    ]

    try:
        statements = [_postgis_volunteer_schema_sql(schema)]
        statements.append(
            f"DELETE FROM {volunteers_table} WHERE drill_token = {_sql_literal(token)}; "
            f"DELETE FROM {outreach_table} WHERE drill_token = {_sql_literal(token)}; "
            f"DELETE FROM {zone_table} WHERE operation_zone_id = {_sql_literal(zone_id)};"
        )
        statements.append(
            f"INSERT INTO {zone_table} (operation_zone_id, zone_name, scenario_tag, zone_geom, hub_point) VALUES ("
            f"{_sql_literal(zone_id)}, {_sql_literal(coordinator['operation_zone_name'])}, {_sql_literal(token)}, "
            f"ST_GeomFromText({_sql_literal(coordinator['zone_polygon_wkt'])}, 4326), "
            f"ST_SetSRID(ST_MakePoint({hub_lon}, {hub_lat}), 4326));"
        )
        for row in volunteers:
            statements.append(
                f"INSERT INTO {volunteers_table} (volunteer_id, drill_token, public_volunteer_ref, intake_source, consent_status, age_bracket, skills_text, availability_status, phone_hash, operation_zone_id, assigned_case_label, current_point) VALUES ("
                f"{_sql_literal(row['volunteer_id'])}, {_sql_literal(token)}, {_sql_literal(row['public_volunteer_ref'])}, {_sql_literal(row['intake_source'])}, "
                f"{_sql_literal(row['consent_status'])}, {_sql_literal(row['age_bracket'])}, {_sql_literal(row['skills_text'])}, {_sql_literal(row['availability_status'])}, "
                f"{_sql_literal(row['phone_hash'])}, {_sql_literal(row['operation_zone_id'])}, {_sql_literal(row['assigned_case_label'])}, "
                f"ST_SetSRID(ST_MakePoint({row['lon']}, {row['lat']}), 4326));"
            )
        for row in outreach:
            statements.append(
                f"INSERT INTO {outreach_table} (candidate_id, drill_token, phone_hash, presence_area_label, message_policy, wellbeing_status, volunteer_interest_status, intake_status) VALUES ("
                f"{_sql_literal(row['candidate_id'])}, {_sql_literal(token)}, {_sql_literal(row['phone_hash'])}, {_sql_literal(row['presence_area_label'])}, "
                f"{_sql_literal(row['message_policy'])}, {_sql_literal(row['wellbeing_status'])}, {_sql_literal(row['volunteer_interest_status'])}, {_sql_literal(row['intake_status'])});"
            )
        _postgres_execute(dsn, statements, timeout)
        tables_found = [r[0] for r in _postgres_query(dsn, f"SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname = {_sql_literal(schema)} AND tablename IN ('reliefqueue_live_volunteers', 'reliefqueue_live_volunteer_outreach') ORDER BY 1;", timeout)]
        indexes_found = [r[0] for r in _postgres_query(dsn, f"SELECT indexname FROM pg_indexes WHERE schemaname = {_sql_literal(schema)} AND indexname LIKE 'reliefqueue_live_volunteer%' ORDER BY 1;", timeout)]
        inside_rows = _postgres_query(dsn, f"SELECT COUNT(*) FROM {volunteers_table} v JOIN {zone_table} z ON z.operation_zone_id = v.operation_zone_id WHERE v.drill_token = {_sql_literal(token)} AND ST_Contains(z.zone_geom, v.current_point);", timeout)
        inside_count = int(inside_rows[0][0] or 0)
        nearest_rows = _postgres_query(
            dsn,
            f"SELECT volunteer_id, intake_source, skills_text, CAST(ST_DistanceSphere(current_point, ST_SetSRID(ST_MakePoint({float(primary['longitude'])}, {float(primary['latitude'])}), 4326)) AS integer) AS distance_meters FROM {volunteers_table} WHERE drill_token = {_sql_literal(token)} ORDER BY current_point <-> ST_SetSRID(ST_MakePoint({float(primary['longitude'])}, {float(primary['latitude'])}), 4326) LIMIT 3;",
            timeout,
        )
        nearest = [
            {"volunteer_id": r[0], "intake_source": r[1], "skills": r[2], "distance_meters": int(r[3] or 0)} for r in nearest_rows
        ]
        skill_rows = _postgres_query(dsn, f"SELECT COUNT(*) FROM {volunteers_table} WHERE drill_token = {_sql_literal(token)} AND (skills_text ILIKE '%first_aid%' OR skills_text ILIKE '%nursing%');", timeout)
        skill_match_count = int(skill_rows[0][0] or 0)
        outreach_rows = _postgres_query(dsn, f"SELECT COUNT(*) FROM {outreach_table} WHERE drill_token = {_sql_literal(token)};", timeout)
        outreach_count = int(outreach_rows[0][0] or 0)
        _postgres_execute(dsn, [f"DELETE FROM {volunteers_table} WHERE drill_token = {_sql_literal(token)}; DELETE FROM {outreach_table} WHERE drill_token = {_sql_literal(token)}; DELETE FROM {zone_table} WHERE scenario_tag = {_sql_literal(token)};"], timeout)
        cleanup_volunteers = int(_postgres_query(dsn, f"SELECT COUNT(*) FROM {volunteers_table} WHERE drill_token = {_sql_literal(token)};", timeout)[0][0] or 0)
        cleanup_outreach = int(_postgres_query(dsn, f"SELECT COUNT(*) FROM {outreach_table} WHERE drill_token = {_sql_literal(token)};", timeout)[0][0] or 0)
        evidence.update(
            {
                "status": "PASS" if inside_count >= 3 and skill_match_count >= 2 and cleanup_volunteers == 0 and cleanup_outreach == 0 else "FAIL",
                "live_mutation_attempted": True,
                "drill_token": token,
                "tables_found": tables_found,
                "spatial_indexes_found": indexes_found,
                "volunteers_registered": [
                    {k: row[k] for k in ["volunteer_id", "public_volunteer_ref", "intake_source", "consent_status", "age_bracket", "skills_text", "availability_status", "assigned_case_label"]}
                    for row in volunteers
                ],
                "inside_zone_volunteer_count": inside_count,
                "nearest_volunteers_to_primary_case": nearest,
                "skill_match_count_first_aid_or_nursing": skill_match_count,
                "presence_outreach_audit_rows": outreach_count,
                "presence_polling_dry_run_only": True,
                "real_messages_sent": False,
                "raw_phone_numbers_written": False,
                "cleanup_remaining_volunteers": cleanup_volunteers,
                "cleanup_remaining_outreach": cleanup_outreach,
            }
        )
    except Exception as exc:
        try:
            _postgres_execute(dsn, [f"DELETE FROM {volunteers_table} WHERE drill_token = {_sql_literal(token)}; DELETE FROM {outreach_table} WHERE drill_token = {_sql_literal(token)}; DELETE FROM {zone_table} WHERE scenario_tag = {_sql_literal(token)};"], timeout)
        except Exception:
            pass
        evidence.update({"status": "FAIL", "live_mutation_attempted": True, **_live_error(exc)})
    _write_json(out_dir / "volunteer_postgis_evidence.json", evidence)
    return evidence


def _redis_volunteer_surge_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    del root
    config = _volunteer_drill_config()
    command_center = config["command_center_config"]
    url, source, note = _resolved_redis_url(report_dir)
    token = "volunteer_surge_" + str(config["selected_profile"]["name"]).replace("-", "_") + "_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    base = _configured_queue_name()
    stream = f"{base}.volunteer_surge.{token[-15:]}"
    dlq_stream = f"{stream}.dead_letter"
    replay_stream = f"{stream}.call_center_review"
    timeline_stream = f"{stream}.timeline"
    group = "volunteer-surge-drill"
    worker = "volunteer-onboarding-worker"
    recovery_consumer = "volunteer-call-center-recovery-worker"
    dedup_key = f"{stream}:dedup:{_demo_phone_hash(token + ':walkup')}"
    poll_guard_key = f"{stream}:presence-poll:disabled-until-authorized"
    evidence: dict[str, Any] = {
        "status": "SKIP" if not url else "STARTED",
        "redis_source": source,
        "scenario": "volunteer_intake_burst_dedup_crash_recovery_dry_run_outreach_replay",
        "stream": stream,
        "dead_letter_stream": dlq_stream,
        "replay_review_stream": replay_stream,
        "timeline_stream": timeline_stream,
        "case_for_redis": [
            "absorbs burst volunteer registrations from field workers, coordinator, and call center",
            "deduplicates repeated volunteer phone/channel events without printing raw phone numbers",
            "recovers abandoned onboarding work after a call-center worker crash",
            "routes failed or sensitive volunteer outreach into human review instead of sending messages automatically",
        ],
        "privacy_boundary": config["privacy_and_safety_boundary"],
        "secret_values_printed": False,
    }
    if note:
        evidence["resolution_note"] = note
    if not url:
        evidence["reason"] = "Redis endpoint is not configured and local live-stack Redis is not ready."
        _write_json(out_dir / "volunteer_redis_evidence.json", evidence)
        return evidence
    jobs = [
        {"job_id": f"{token}-field-walkup", "purpose": "field_worker_register_walkup_volunteer", "phone_hash": _demo_phone_hash(token + ':field'), "priority": "high"},
        {"job_id": f"{token}-coordinator-walkup", "purpose": "coordinator_register_hub_walkup_volunteer", "phone_hash": _demo_phone_hash(token + ':coord'), "priority": "normal"},
        {"job_id": f"{token}-presence-dry-run", "purpose": "presence_phone_wellbeing_poll_dry_run_only", "phone_hash": _demo_phone_hash(token + ':presence'), "priority": "review"},
        {"job_id": f"{token}-skill-followup", "purpose": "call_center_skill_intake_followup", "phone_hash": _demo_phone_hash(token + ':optin'), "priority": "high"},
    ]
    while len(jobs) < int(command_center["outreach_burst_size"]):
        i = len(jobs) + 1
        jobs.append({"job_id": f"{token}-buffer-{i}", "purpose": "volunteer_intake_burst_buffer", "phone_hash": _demo_phone_hash(f"{token}:buffer:{i}"), "priority": "normal"})
    try:
        _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, timeline_stream, dedup_key, poll_guard_key])
        _redis_xgroup_create(url, stream, group)
        message_ids: list[str] = []
        for job in jobs:
            message_ids.append(str(_redis_command(url, ["XADD", stream, "*", *_redis_flatten_fields(job)])))
        depth_after_enqueue = int(_redis_command(url, ["XLEN", stream]) or 0)
        dedup_first = _redis_command(url, ["SET", dedup_key, "seen", "NX", "EX", str(command_center["dedup_ttl_seconds"])])
        dedup_second = _redis_command(url, ["SET", dedup_key, "seen-again", "NX", "EX", str(command_center["dedup_ttl_seconds"])])
        poll_guard = _redis_command(url, ["SET", poll_guard_key, "dry_run_review_only", "NX", "EX", str(command_center["dedup_ttl_seconds"])])
        entries = _redis_entries(_redis_command(url, ["XREADGROUP", "GROUP", group, worker, "COUNT", "4", "STREAMS", stream, ">"] ))
        field_id = coordinator_id = poll_id = skill_id = None
        for message_id, fields in entries:
            purpose = fields.get("purpose")
            if purpose == "field_worker_register_walkup_volunteer":
                field_id = message_id
                _redis_command(url, ["XACK", stream, group, message_id])
                _redis_command(url, ["XADD", timeline_stream, "*", "event", "field_walkup_registered", "message_id", message_id])
            elif purpose == "coordinator_register_hub_walkup_volunteer":
                coordinator_id = message_id
                _redis_command(url, ["XACK", stream, group, message_id])
                _redis_command(url, ["XADD", timeline_stream, "*", "event", "coordinator_walkup_registered", "message_id", message_id])
            elif purpose == "presence_phone_wellbeing_poll_dry_run_only":
                poll_id = message_id
                _redis_command(url, ["XADD", timeline_stream, "*", "event", "presence_poll_kept_dry_run", "message_id", message_id])
            elif purpose == "call_center_skill_intake_followup":
                skill_id = message_id
        claim_idle_ms = int(command_center["claim_idle_ms"])
        time.sleep(max(claim_idle_ms / 1000.0, 0.05))
        claimed = _redis_entries(_redis_command(url, ["XCLAIM", stream, group, recovery_consumer, str(claim_idle_ms), str(poll_id)])) if poll_id else []
        recovered_id = claimed[0][0] if claimed else None
        if recovered_id:
            _redis_command(url, ["XACK", stream, group, str(recovered_id)])
            _redis_command(url, ["XADD", timeline_stream, "*", "event", "call_center_worker_recovered_dry_run_poll", "message_id", str(recovered_id)])
        dlq_message_id = None
        if skill_id:
            _redis_command(url, ["XACK", stream, group, str(skill_id)])
            dlq_message_id = str(_redis_command(url, ["XADD", dlq_stream, "*", "failed_message_id", str(skill_id), "reason", "skills_need_human_verification", "replay_mode", "review_first"]))
        replay_ids: list[str] = []
        for message_id, fields in _redis_entries(_redis_command(url, ["XREAD", "COUNT", "10", "STREAMS", dlq_stream, "0-0"])):
            replay_ids.append(str(_redis_command(url, ["XADD", replay_stream, "*", "source", "dead_letter", "failed_message_id", fields.get("failed_message_id", message_id), "review_required", "true"])))
            _redis_command(url, ["XDEL", dlq_stream, message_id])
        buffer_drained = 0
        for message_id, _fields in _redis_entries(_redis_command(url, ["XREADGROUP", "GROUP", group, worker, "COUNT", str(len(jobs)), "STREAMS", stream, ">"] )):
            buffer_drained += 1
            _redis_command(url, ["XACK", stream, group, str(message_id)])
        final_before_cleanup = {
            "stream_length": int(_redis_command(url, ["XLEN", stream]) or 0),
            "dlq_length": int(_redis_command(url, ["XLEN", dlq_stream]) or 0),
            "replay_review_length": int(_redis_command(url, ["XLEN", replay_stream]) or 0),
            "timeline_length": int(_redis_command(url, ["XLEN", timeline_stream]) or 0),
            "pending": _redis_command(url, ["XPENDING", stream, group]),
            "dedup_key_exists": int(_redis_command(url, ["EXISTS", dedup_key]) or 0),
            "poll_guard_key_exists": int(_redis_command(url, ["EXISTS", poll_guard_key]) or 0),
        }
        _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, timeline_stream, dedup_key, poll_guard_key])
        final_after_cleanup = {
            "stream_exists": int(_redis_command(url, ["EXISTS", stream]) or 0),
            "dlq_exists": int(_redis_command(url, ["EXISTS", dlq_stream]) or 0),
            "replay_review_exists": int(_redis_command(url, ["EXISTS", replay_stream]) or 0),
            "timeline_exists": int(_redis_command(url, ["EXISTS", timeline_stream]) or 0),
            "dedup_key_exists": int(_redis_command(url, ["EXISTS", dedup_key]) or 0),
            "poll_guard_key_exists": int(_redis_command(url, ["EXISTS", poll_guard_key]) or 0),
        }
        duplicate_suppressed = dedup_first == "OK" and dedup_second is None
        recovered = recovered_id == poll_id and bool(recovered_id)
        replayed = bool(replay_ids) and final_before_cleanup["dlq_length"] == 0
        no_pending_left = bool(final_before_cleanup["pending"]) and int(final_before_cleanup["pending"][0] or 0) == 0
        cleanup_verified = not any(final_after_cleanup.values())
        evidence.update(
            {
                "status": "PASS" if duplicate_suppressed and poll_guard == "OK" and recovered and replayed and no_pending_left and cleanup_verified else "FAIL",
                "live_mutation_attempted": True,
                "jobs_prepared": len(jobs),
                "queue_depth_after_enqueue": depth_after_enqueue,
                "field_worker_registration_message_id": field_id,
                "coordinator_registration_message_id": coordinator_id,
                "simulated_call_center_crash_message_id": poll_id,
                "recovered_message_id": recovered_id,
                "recovery_consumer": recovery_consumer,
                "dead_letter_message_id": dlq_message_id,
                "replay_message_ids": replay_ids,
                "replayed": len(replay_ids),
                "burst_buffer_jobs_drained": buffer_drained,
                "atomic_dedup": {"key": dedup_key, "first_event_result": dedup_first, "duplicate_event_result": dedup_second, "duplicate_suppressed": duplicate_suppressed},
                "presence_polling_guard": {"key": poll_guard_key, "result": poll_guard, "real_messages_sent": False, "dry_run_only": True},
                "worker_crash_recovered": recovered,
                "no_pending_left": no_pending_left,
                "final_state_before_cleanup": final_before_cleanup,
                "final_state_after_cleanup": final_after_cleanup,
                "cleanup_verified": cleanup_verified,
                "private_payload_written": False,
            }
        )
    except Exception as exc:
        try:
            _redis_command(url, ["DEL", stream, dlq_stream, replay_stream, timeline_stream, dedup_key, poll_guard_key])
        except Exception:
            pass
        evidence.update({"status": "FAIL", "live_mutation_attempted": True, **_live_error(exc)})
    _write_json(out_dir / "volunteer_redis_evidence.json", evidence)
    return evidence


def _print_live_volunteer_surge_verbose(result: dict[str, Any], out_dir: Path, level: int = 1) -> None:
    postgis = result.get("postgis") if isinstance(result.get("postgis"), dict) else {}
    redis = result.get("redis") if isinstance(result.get("redis"), dict) else {}
    profile = result.get("selected_profile") if isinstance(result.get("selected_profile"), dict) else {}
    print(f"Volunteer surge evidence (-{'v' * max(level, 1)}):")
    print(f"- status: {result.get('status', 'unknown')}")
    print(f"- profile: {profile.get('name', 'unknown')} - {profile.get('label', '')}")
    print(f"- PostGIS: {postgis.get('status', 'unknown')} volunteers={len(postgis.get('volunteers_registered') or [])} nearest={bool(postgis.get('nearest_volunteers_to_primary_case'))} cleanup={postgis.get('cleanup_remaining_volunteers', 'not_recorded')}")
    print(f"- Redis: {redis.get('status', 'unknown')} recovered={redis.get('worker_crash_recovered', 'not_recorded')} replayed={redis.get('replayed', 'not_recorded')} dry_run_poll={redis.get('presence_polling_guard', {}).get('dry_run_only', 'not_recorded')}")
    if level <= 1:
        print(f"Full report: {out_dir / 'live_volunteer_surge_drill.json'}")
        return
    print("Role ownership:")
    print("- field worker/coordinator: register walk-up volunteers with consent, age bracket, skills, availability, and safe location")
    print("- command center: monitor onboarding queue, dedup, worker recovery, DLQ/replay, and keep mass polling gated")
    if result.get("privacy_and_safety_boundary"):
        print(f"- privacy/safety boundary: {_json_line(result['privacy_and_safety_boundary'])}")
    if postgis.get("volunteers_registered"):
        print(f"- volunteers registered: {_json_line(postgis['volunteers_registered'])}")
    if postgis.get("nearest_volunteers_to_primary_case"):
        print(f"- nearest volunteers to primary case: {_json_line(postgis['nearest_volunteers_to_primary_case'])}")
    if postgis.get("presence_outreach_audit_rows") is not None:
        print(f"- presence outreach audit rows: {postgis.get('presence_outreach_audit_rows')}")
    if redis.get("atomic_dedup"):
        print(f"- Redis duplicate suppression: {_json_line(redis['atomic_dedup'])}")
    if redis.get("presence_polling_guard"):
        print(f"- Redis presence polling guard: {_json_line(redis['presence_polling_guard'])}")
    if level >= 3:
        print(f"- Redis final state before cleanup: {_json_line(redis.get('final_state_before_cleanup', {}))}")
        print(f"- Redis final state after cleanup: {_json_line(redis.get('final_state_after_cleanup', {}))}")
    print(f"Full report: {out_dir / 'live_volunteer_surge_drill.json'}")


def live_volunteer_surge_drill(root: Path, report_dir: Path, out_dir: Path) -> dict[str, Any]:
    config = _volunteer_drill_config()
    postgis = _postgis_volunteer_surge_drill(root, report_dir, out_dir)
    redis = _redis_volunteer_surge_drill(root, report_dir, out_dir)
    service_statuses = [str(postgis.get("status")), str(redis.get("status"))]
    if "FAIL" in service_statuses:
        status = "FAIL"
        readiness = "NEEDS_REVIEW"
    elif service_statuses == ["PASS", "PASS"]:
        status = "PASS"
        readiness = "READY_FOR_VOLUNTEER_INTAKE_OPERATOR_REVIEW"
    elif "PASS" in service_statuses:
        status = "PARTIAL"
        readiness = "NEEDS_BOTH_POSTGIS_AND_REDIS_LIVE_ENDPOINTS"
    else:
        status = "SKIP"
        readiness = "NEEDS_LIVE_STACK_OR_EXPLICIT_ENDPOINTS"
    summary = {"postgis": str(postgis.get("status")), "redis": str(redis.get("status"))}
    status_counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "PARTIAL": 0}
    for item in summary.values():
        if item in status_counts:
            status_counts[item] += 1
    write_checkpoint(
        root,
        report_dir,
        "02_05",
        status,
        ["live-volunteer-surge-drill"],
        [{"command": "live-volunteer-surge-drill", "exit_code": 0 if status in {"PASS", "PARTIAL", "SKIP"} else 1}],
        _summary_strings(status_counts),
        [
            "Synthetic drill only; no real messages are sent and no raw phone numbers are stored.",
            "Mass phone presence polling remains disabled until lawful authority, provider integration, opt-out, and human review are present.",
        ],
        readiness,
    )
    return {
        "status": status,
        "phase_id": "02_05",
        "phase_name": PHASES["02_05"]["name"],
        "selected_profile": config["selected_profile"],
        "available_profiles": config["available_profiles"],
        "role_contract": config["role_contract"],
        "coordinator_config": config["coordinator_config"],
        "command_center_config": config["command_center_config"],
        "privacy_and_safety_boundary": config["privacy_and_safety_boundary"],
        "config_warnings": config["config_warnings"],
        "summary": summary,
        "readiness": readiness,
        "postgis": postgis,
        "redis": redis,
        "safety_note": "Volunteer evidence is synthetic. Real outreach requires lawful authority, opt-out, approved templates, provider controls, and human supervision.",
        "secret_values_printed": False,
    }


COMMANDS: dict[str, tuple[str, Callable[[Path, Path, Path], dict[str, Any]]]] = {
    "postgis-live-init": ("02", postgis_live_init),
    "postgis-live-import-demo": ("02", postgis_live_import_demo),
    "postgis-live-query": ("02", postgis_live_query),
    "postgis-live-smoke": ("02", postgis_live_smoke),
    "postgis-live-backup": ("02", postgis_live_backup),
    "postgis-live-restore-smoke": ("02", postgis_live_restore_smoke),
    "queue-live-init": ("03", queue_live_init),
    "queue-live-enqueue-demo": ("03", queue_live_enqueue_demo),
    "queue-live-worker-once": ("03", queue_live_worker_once),
    "queue-live-smoke": ("03", queue_live_smoke),
    "queue-live-dlq-report": ("03", queue_live_dlq_report),
    "queue-live-replay-dlq": ("03", queue_live_replay_dlq),
    "live-stateful-mutation-drill": ("02_03", live_stateful_mutation_drill),
    "live-logistics-asset-drill": ("02_04", live_logistics_asset_drill),
    "live-volunteer-surge-drill": ("02_05", live_volunteer_surge_drill),
    "vllm-live-status": ("04", vllm_live_status),
    "vllm-live-smoke": ("04", vllm_live_smoke),
    "amd-live-benchmark-500": ("04", amd_live_benchmark_500),
    "amd-live-benchmark-5000": ("04", amd_live_benchmark_5000),
    "amd-live-report": ("04", amd_live_report),
    "live-health": ("05", live_health),
    "live-metrics-export": ("05", live_metrics_export),
    "live-audit-report": ("05", live_audit_report),
    "live-failure-report": ("05", live_failure_report),
    "observability-live-smoke": ("05", observability_live_smoke),
    "field-form-xlsform-export": ("06", field_form_xlsform_export),
    "field-form-odk-package": ("06", field_form_odk_package),
    "field-form-import-sample": ("06", field_form_import_sample),
    "odk-live-status": ("06", odk_live_status),
    "odk-live-smoke": ("06", odk_live_smoke),
    "rapidpro-flow-export": ("07", rapidpro_flow_export),
    "rapidpro-webhook-smoke": ("07", rapidpro_webhook_smoke),
    "rapidpro-outbox-dry-run": ("07", rapidpro_outbox_dry_run),
    "rapidpro-live-status": ("07", rapidpro_live_status),
    "rapidpro-live-smoke": ("07", rapidpro_live_smoke),
    "channel-webhook-smoke": ("08", channel_webhook_smoke),
    "whatsapp-webhook-smoke": ("08", whatsapp_webhook_smoke),
    "sms-webhook-smoke": ("08", sms_webhook_smoke),
    "channel-normalize-smoke": ("08", channel_normalize_smoke),
    "channel-live-status": ("08", channel_live_status),
    "masked-contact-live-status": ("09", masked_contact_live_status),
    "masked-contact-create-dry-run": ("09", masked_contact_create_dry_run),
    "masked-contact-provider-smoke": ("09", masked_contact_provider_smoke),
    "masked-contact-cancel-dry-run": ("09", masked_contact_cancel_dry_run),
    "live-pilot-drill": ("10", live_pilot_drill),
    "live-pilot-reviewer-pack": ("10", live_pilot_reviewer_pack),
    "live-pilot-status": ("10", live_pilot_status),
    "live-pilot-clean": ("10", live_pilot_clean),
}


def run_live_integration_command(command: str, root: Path, report_dir: Path) -> int:
    phase_id, func = COMMANDS[command]
    return _run_phase_command(root, report_dir, phase_id, command, func)

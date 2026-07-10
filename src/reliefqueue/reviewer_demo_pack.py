"""Reviewer/demo pack export for the end-to-end command-center drill.

This phase intentionally consumes the phase-02-06 report and turns it into a
small reviewable handoff: one machine-readable pack report, a few human-readable
briefs, and a relative-path tarball that can be attached to a hackathon/demo
submission without exposing secrets or pretending to dispatch real resources.
"""

from __future__ import annotations

import argparse
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from reliefqueue.operator_console import (
    bullet,
    clamp_verbose,
    full_json_section,
    key_value,
    section,
    short_text,
    status_text,
    true_false,
    verbosity_help,
)

from reliefqueue.live_command_center_drill import PHASE as SOURCE_PHASE
from reliefqueue.live_command_center_drill import REPORT_RELATIVE_PATH as SOURCE_REPORT_RELATIVE_PATH
from reliefqueue.live_command_center_drill import run_drill

PHASE = "phase-02-07-reviewer-demo-pack-export"
PACK_RELATIVE_DIR = Path("reports/latest/live_integrations/phase_02_07_reviewer_demo_pack")
PACK_REPORT_NAME = "reviewer_demo_pack.json"
ARCHIVE_NAME = "reviewer_demo_pack.tar.gz"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing source report: {path}. Run make live-command-center-drill first, or use --refresh-drill.") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Expected JSON object in source report: {path}")
    return value


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_record(pack_dir: Path, name: str, description: str) -> dict[str, Any]:
    path = pack_dir / name
    return {
        "name": name,
        "path": str(PACK_RELATIVE_DIR / name),
        "description": description,
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _source_status(source: dict[str, Any]) -> str:
    status = str(source.get("status", "UNKNOWN"))
    phase = str(source.get("phase", "unknown"))
    return f"{phase} / {status}"


def _top_case_lines(source: dict[str, Any]) -> list[str]:
    cases = source.get("gis", {}).get("ranked_urgent_cases", [])
    lines: list[str] = []
    for index, item in enumerate(cases[:4], start=1):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"{index}. {item.get('case_id')} — {item.get('need_type')} — priority {item.get('priority')} — {item.get('distance_from_hub_km')} km from hub"
        )
    return lines or ["No ranked cases were available in the source report."]


def _step_lines(source: dict[str, Any]) -> list[str]:
    steps = source.get("steps", [])
    lines: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        lines.append(f"- {step.get('status', 'UNKNOWN')} — {step.get('name', 'unnamed_step')}")
    return lines or ["- UNKNOWN — no steps found in source report"]


def _safe_join(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def _make_demo_story(source: dict[str, Any]) -> str:
    profile_context = source.get("profile_context", {})
    safety = source.get("safety", {})
    queue = source.get("queue_resilience", {})
    logistics = source.get("logistics", {})
    volunteers = source.get("volunteers", {})
    return f"""
# ReliefQueue AI demo story — connected command-center drill

A flood is reported. ReliefQueue starts with the selected disaster profile and creates a synthetic affected zone around **{profile_context.get('affected_zone_label', 'the affected zone')}** with **{profile_context.get('relief_hub_label', 'the relief hub')}** as the coordination point.

The system then shows one connected operator flow:

1. map the affected zone and relief hub,
2. insert urgent cases with GIS points,
3. assign nearby cases to the operation zone,
4. rank urgent cases by priority and distance,
5. create logistics requests from case needs,
6. reserve assets without auto-dispatch,
7. simulate an overdue asset and recommend reallocation,
8. register nearby volunteers,
9. match volunteers by location and skills,
10. simulate burst intake, worker crash, retry, DLQ, and replay,
11. produce role-aware command-center and coordinator briefs,
12. produce a reviewer evidence pack, and
13. clean up synthetic state.

## Top cases

{_safe_join(_top_case_lines(source))}

## Demo proof points

- Logistics requests: {len(logistics.get('requests', []))}
- Proposed dispatches sent externally: {safety.get('external_dispatches_sent', 0)}
- Volunteer matches: {len(volunteers.get('matches', []))}
- Redis-style burst size: {queue.get('burst_size')}
- DLQ replayed: {queue.get('replayed_from_dlq')}
- Remaining DLQ after replay: {queue.get('remaining_dlq')}
- Human review required: {str(safety.get('human_review_required')).lower()}
- Auto-dispatch enabled: {str(safety.get('auto_dispatch_enabled')).lower()}

## Operator commands

```bash
make live-command-center-drill PROFILE=urban_flood VERBOSE_FLAGS=-vv
make reviewer-demo-pack PROFILE=urban_flood VERBOSE_FLAGS=-vv
```

The pack is synthetic and local. It is suitable for review and demo evidence; it is not a production dispatch record.
"""


def _make_command_center_brief(source: dict[str, Any]) -> str:
    brief = source.get("briefs", {}).get("command_center_decision_brief", {})
    queue = source.get("queue_resilience", {})
    logistics = source.get("logistics", {})
    return f"""
# Command Center brief

Audience: Command Center Operator  
Review required: {brief.get('review_required', True)}

{brief.get('summary', 'Command-center summary was not available.')}

## Decisions needed

{_safe_join(f"- {item}" for item in brief.get('decisions_needed', []))}

## Runtime evidence

- Queue mode: {queue.get('mode')}
- Burst size: {queue.get('burst_size')}
- Worker crash simulated after messages: {queue.get('worker_crash_simulated_after_messages')}
- Dead-lettered: {queue.get('dead_lettered')}
- Replayed from DLQ: {queue.get('replayed_from_dlq')}
- Remaining DLQ: {queue.get('remaining_dlq')}
- Worker recovered: {queue.get('worker_recovered')}
- Queue pressure: {queue.get('queue_pressure')}

## Logistics evidence

- Requests created: {len(logistics.get('requests', []))}
- Reservations created: {len(logistics.get('reservations', []))}
- Proposed dispatch records: {len(logistics.get('dispatches', []))}
- External dispatches sent: {logistics.get('external_dispatches_sent', 0)}
- Reallocation recommendations: {len(logistics.get('reallocations', []))}

All proposed operational actions remain pending human review.
"""


def _make_coordinator_brief(source: dict[str, Any]) -> str:
    brief = source.get("briefs", {}).get("coordinator_field_brief", {})
    safe_areas = brief.get("safe_areas", [])
    blocked_areas = brief.get("blocked_areas", [])
    field_actions = brief.get("field_actions_to_review", [])
    volunteer_matches = brief.get("volunteer_matches", [])
    return f"""
# Local Coordinator field brief

Audience: Local Coordinator  
Review required: {brief.get('review_required', True)}

{brief.get('summary', 'Coordinator summary was not available.')}

## Field actions to review

{_safe_join(f"- {item.get('case_id')} — {item.get('need_type')} — {item.get('distance_from_hub_km')} km from hub" for item in field_actions)}

## Volunteer matches to review

{_safe_join(f"- {item.get('case_id')} → {item.get('volunteer_id')} ({item.get('matched_skill')}, {item.get('distance_to_case_km')} km)" for item in volunteer_matches)}

## Safe areas

{_safe_join(f"- {item}" for item in safe_areas)}

## Blocked areas

{_safe_join(f"- {item}" for item in blocked_areas)}

No volunteer is contacted automatically by this drill.
"""


def _make_reviewer_evidence(source: dict[str, Any], source_path: Path) -> str:
    safety = source.get("safety", {})
    cleanup = source.get("cleanup", {})
    source_evidence = source.get("source_evidence", {})
    return f"""
# Reviewer evidence

Source report: `{source_path}`  
Source status: {_source_status(source)}

## Safety contract

- Human review required: {safety.get('human_review_required')}
- Auto-dispatch enabled: {safety.get('auto_dispatch_enabled')}
- External sends: {int(safety.get('external_dispatches_sent', 0)) + int(safety.get('external_messages_sent', 0))}
- External dispatches sent: {safety.get('external_dispatches_sent')}
- External messages sent: {safety.get('external_messages_sent')}
- Secrets redacted: {safety.get('secrets_redacted')}
- Synthetic state cleaned: {cleanup.get('synthetic_state_cleaned')}

## End-to-end steps

{_safe_join(_step_lines(source))}

## Latest source evidence discovered by phase-02-06

```json
{json.dumps(source_evidence, indent=2, sort_keys=True)}
```

This pack is an export of evidence for demo/review. It does not create real cases, dispatch assets, contact volunteers, or call paid services.
"""


def _make_report_contract(source: dict[str, Any]) -> dict[str, Any]:
    safety = source.get("safety", {})
    return {
        "contract": "phase-02-07 reviewer/demo pack source contract",
        "source_phase": source.get("phase"),
        "source_status": source.get("status"),
        "source_profile": source.get("profile"),
        "source_steps": [step.get("name") for step in source.get("steps", []) if isinstance(step, dict)],
        "ranked_case_ids": [item.get("case_id") for item in source.get("gis", {}).get("ranked_urgent_cases", []) if isinstance(item, dict)],
        "logistics_request_count": len(source.get("logistics", {}).get("requests", [])),
        "volunteer_match_count": len(source.get("volunteers", {}).get("matches", [])),
        "queue_replayed_from_dlq": source.get("queue_resilience", {}).get("replayed_from_dlq"),
        "remaining_dlq": source.get("queue_resilience", {}).get("remaining_dlq"),
        "human_review_required": safety.get("human_review_required"),
        "auto_dispatch_enabled": safety.get("auto_dispatch_enabled"),
        "external_dispatches_sent": safety.get("external_dispatches_sent"),
        "external_messages_sent": safety.get("external_messages_sent"),
    }


def _make_demo_script(source: dict[str, Any]) -> str:
    top_cases = _top_case_lines(source)
    return f"""
# Three-minute demo script

## 0:00 — Set context

ReliefQueue AI is a command-center helper for disaster coordination. This demo is synthetic and local, but it shows the full decision flow.

## 0:30 — Run the connected drill

```bash
make live-command-center-drill PROFILE=urban_flood VERBOSE_FLAGS=-vv
```

Point out that one command creates the profile context, GIS-style case ranking, logistics recommendations, volunteer matches, queue recovery evidence, role-aware briefs, reviewer evidence, and cleanup.

## 1:15 — Show top operational priorities

{_safe_join(top_cases)}

Explain that these are ranked recommendations, not automatic actions.

## 1:45 — Show resilience and safety

Open `02_command_center_brief.md` and point to Runtime evidence. Then open `04_reviewer_evidence.md` and point to the safety contract: human review is required, auto-dispatch is disabled, and external sends are zero.

## 2:30 — Show the reviewer/demo pack

```bash
make reviewer-demo-pack PROFILE=urban_flood VERBOSE_FLAGS=-vv
```

The generated archive contains the manifest, demo story, command-center brief, coordinator field brief, reviewer evidence, report contract, and this demo script.
"""


def _create_archive(pack_dir: Path) -> Path:
    archive_path = pack_dir / ARCHIVE_NAME
    if archive_path.exists():
        archive_path.unlink()
    files = [
        PACK_REPORT_NAME,
        "00_manifest.json",
        "01_demo_story.md",
        "02_command_center_brief.md",
        "03_coordinator_field_brief.md",
        "04_reviewer_evidence.md",
        "05_report_contract.json",
        "06_demo_script.md",
    ]
    with tarfile.open(archive_path, "w:gz") as tf:
        for name in files:
            path = pack_dir / name
            arcname = str(Path("phase_02_07_reviewer_demo_pack") / name)
            tf.add(path, arcname=arcname)
    return archive_path


def _validate_source(source: dict[str, Any], source_path: Path) -> None:
    if source.get("phase") != SOURCE_PHASE:
        raise SystemExit(f"Source report phase mismatch in {source_path}: {source.get('phase')!r}")
    if source.get("status") != "PASS":
        raise SystemExit(f"Source report is not PASS in {source_path}: {source.get('status')!r}")
    safety = source.get("safety", {})
    if safety.get("human_review_required") is not True:
        raise SystemExit("Source report does not require human review")
    if safety.get("auto_dispatch_enabled") is not False:
        raise SystemExit("Source report does not prove auto-dispatch disabled")
    if safety.get("external_dispatches_sent") != 0 or safety.get("external_messages_sent") != 0:
        raise SystemExit("Source report indicates external sends; refusing to export demo pack")


def export_reviewer_demo_pack(
    profile_name: str = "urban_flood",
    repo_root: Path | None = None,
    verbose_level: int = 0,
    refresh_drill: bool = False,
) -> dict[str, Any]:
    root = Path.cwd() if repo_root is None else Path(repo_root)
    source_path = root / SOURCE_REPORT_RELATIVE_PATH
    generated_by_refresh = False
    if refresh_drill or not source_path.exists():
        run_drill(profile_name=profile_name, repo_root=root, verbose_level=verbose_level)
        generated_by_refresh = True
    source = _read_json(source_path)
    _validate_source(source, source_path)

    pack_dir = root / PACK_RELATIVE_DIR
    pack_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "phase": PHASE,
        "generated_at": _utc_now(),
        "source_report": str(SOURCE_REPORT_RELATIVE_PATH),
        "pack_dir": str(PACK_RELATIVE_DIR),
        "profile": source.get("profile"),
        "safety": {
            "synthetic_only": True,
            "human_review_required": True,
            "auto_dispatch_enabled": False,
            "external_dispatches_sent": 0,
            "external_messages_sent": 0,
            "secrets_redacted": True,
        },
        "operator_commands": [
            "make live-command-center-drill PROFILE=urban_flood VERBOSE_FLAGS=-vv",
            "make reviewer-demo-pack PROFILE=urban_flood VERBOSE_FLAGS=-vv",
        ],
    }

    _write_json(pack_dir / "00_manifest.json", manifest)
    _write_text(pack_dir / "01_demo_story.md", _make_demo_story(source))
    _write_text(pack_dir / "02_command_center_brief.md", _make_command_center_brief(source))
    _write_text(pack_dir / "03_coordinator_field_brief.md", _make_coordinator_brief(source))
    _write_text(pack_dir / "04_reviewer_evidence.md", _make_reviewer_evidence(source, SOURCE_REPORT_RELATIVE_PATH))
    _write_json(pack_dir / "05_report_contract.json", _make_report_contract(source))
    _write_text(pack_dir / "06_demo_script.md", _make_demo_script(source))

    artifact_descriptions = {
        "00_manifest.json": "Machine-readable index of the reviewer/demo pack.",
        "01_demo_story.md": "Plain-language hackathon narrative for the connected drill.",
        "02_command_center_brief.md": "Command-center runtime and logistics evidence.",
        "03_coordinator_field_brief.md": "Coordinator-facing field actions and volunteer matches to review.",
        "04_reviewer_evidence.md": "Reviewer safety contract and end-to-end evidence list.",
        "05_report_contract.json": "Machine-checkable subset of the source drill report contract.",
        "06_demo_script.md": "Short walkthrough script for a live or recorded demo.",
    }
    artifacts = [_artifact_record(pack_dir, name, desc) for name, desc in artifact_descriptions.items()]

    pack: dict[str, Any] = {
        "phase": PHASE,
        "status": "PASS",
        "generated_at": manifest["generated_at"],
        "profile": source.get("profile"),
        "integration_mode": "local_synthetic_reviewer_demo_export",
        "external_services_required": False,
        "source_report": {
            "path": str(SOURCE_REPORT_RELATIVE_PATH),
            "phase": source.get("phase"),
            "status": source.get("status"),
            "generated_by_refresh": generated_by_refresh,
        },
        "safety": manifest["safety"],
        "artifacts": artifacts,
        "archive": {
            "name": ARCHIVE_NAME,
            "path": str(PACK_RELATIVE_DIR / ARCHIVE_NAME),
            "format": "tar.gz",
            "contains_only_relative_paths": True,
        },
        "reviewer_summary": {
            "story": "Connected disaster coordination proof from flood report to GIS ranking, logistics, volunteers, queue resilience, briefs, evidence, and cleanup.",
            "human_review_boundary": "No asset or volunteer action is auto-dispatched; all actions are recommendations pending review.",
            "top_case_ids": [item.get("case_id") for item in source.get("gis", {}).get("ranked_urgent_cases", [])[:3] if isinstance(item, dict)],
        },
    }

    _write_json(pack_dir / PACK_REPORT_NAME, pack)
    archive_path = _create_archive(pack_dir)
    pack["archive"]["size_bytes"] = archive_path.stat().st_size
    _write_json(pack_dir / PACK_REPORT_NAME, pack)
    return pack


def render_console_summary(pack: dict[str, Any], verbose_level: int = 0) -> str:
    verbose_level = clamp_verbose(verbose_level)
    safety = pack.get("safety", {})
    archive = pack.get("archive", {})
    artifacts = list(pack.get("artifacts", []))
    reviewer_summary = pack.get("reviewer_summary", {})

    lines: list[str] = [
        f"ReliefQueue reviewer/demo pack: {status_text(pack.get('status'))}",
        f"Profile: {pack.get('profile')}",
        "Outputs:",
        f"- pack report: {PACK_RELATIVE_DIR / PACK_REPORT_NAME}",
        f"- archive: {archive.get('path')}",
        "Reviewer result:",
        f"- {reviewer_summary.get('story')}",
        f"- artifacts exported: {len(artifacts)}",
        "Safety:",
        f"- human review required: {true_false(safety.get('human_review_required'))}",
        f"- auto-dispatch enabled: {true_false(safety.get('auto_dispatch_enabled'))}",
        f"- external sends: {int(safety.get('external_dispatches_sent') or 0) + int(safety.get('external_messages_sent') or 0)}",
    ]

    if verbose_level >= 1:
        section(lines, "Artifacts")
        for artifact in artifacts:
            bullet(lines, f"{artifact.get('name')}: {short_text(artifact.get('description'), 120)}")

    if verbose_level >= 2:
        section(lines, "Safety contract")
        key_value(lines, "human_review_required", true_false(safety.get("human_review_required")))
        key_value(lines, "auto_dispatch_enabled", true_false(safety.get("auto_dispatch_enabled")))
        key_value(lines, "external_dispatches_sent", safety.get("external_dispatches_sent"))
        key_value(lines, "external_messages_sent", safety.get("external_messages_sent"))
        key_value(lines, "top case ids", reviewer_summary.get("top_case_ids", []))

    if verbose_level >= 3:
        section(lines, "Artifact paths")
        for artifact in artifacts:
            bullet(lines, f"{artifact.get('path')} ({artifact.get('size_bytes')} bytes)")
        section(lines, "Source report")
        source = pack.get("source_report", {})
        key_value(lines, "path", source.get("path"))
        key_value(lines, "status", source.get("status"))
        key_value(lines, "generated_by_refresh", true_false(source.get("generated_by_refresh")))
        key_value(lines, "archive_relative_paths_only", true_false(archive.get("contains_only_relative_paths")))

    if verbose_level >= 4:
        full_json_section(lines, "Full captured pack JSON", pack)

    return "\n".join(lines)

def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the phase-02-07 reviewer/demo pack from the latest command-center drill report.")
    parser.add_argument("--profile", default=os.environ.get("PROFILE", "urban_flood"), help="Disaster profile used if the source drill must be refreshed.")
    parser.add_argument("--refresh-drill", action="store_true", default=os.environ.get("REFRESH_DRILL", "0") in {"1", "true", "TRUE", "yes", "YES"}, help="Run phase-02-06 before exporting the reviewer/demo pack.")
    parser.add_argument("-v", "--verbose", action="count", default=0, help=verbosity_help())
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    verbose_level = clamp_verbose(args.verbose)
    pack = export_reviewer_demo_pack(
        profile_name=args.profile,
        repo_root=Path.cwd(),
        verbose_level=verbose_level,
        refresh_drill=bool(args.refresh_drill),
    )
    print(render_console_summary(pack, verbose_level=verbose_level))
    return 0 if pack["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

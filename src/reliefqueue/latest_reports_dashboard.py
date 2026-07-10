"""Lightweight dashboard wiring for the latest ReliefQueue evidence reports.

This module does not build a full web application. It turns the latest phase-02-06
command-center drill and phase-02-07 reviewer/demo pack into a small,
offline-safe dashboard state JSON plus a self-contained HTML snapshot that a
future UI can consume without re-learning the report contracts.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from reliefqueue.operator_console import (
    bullet,
    clamp_verbose,
    full_json_section,
    key_value,
    list_text,
    section,
    status_text,
    true_false,
    verbosity_help,
)

from reliefqueue.live_command_center_drill import REPORT_RELATIVE_PATH as DRILL_REPORT_RELATIVE_PATH
from reliefqueue.reviewer_demo_pack import PACK_RELATIVE_DIR, PACK_REPORT_NAME, export_reviewer_demo_pack

PHASE = "phase-02-08-lightweight-dashboard-wiring"
DASHBOARD_RELATIVE_DIR = Path("reports/latest/live_integrations/phase_02_08_dashboard")
DASHBOARD_REPORT_NAME = "latest_reports_dashboard.json"
DASHBOARD_HTML_NAME = "index.html"
DASHBOARD_SUMMARY_NAME = "dashboard_summary.md"
DRILL_PHASE = "phase-02-06-end-to-end-command-center-drill"
PACK_PHASE = "phase-02-07-reviewer-demo-pack-export"
PACK_REPORT_RELATIVE_PATH = PACK_RELATIVE_DIR / PACK_REPORT_NAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _source_record(name: str, path: Path, rel_path: Path, expected_phase: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": name,
            "path": str(rel_path),
            "exists": False,
            "status": "MISSING",
            "phase": None,
            "size_bytes": 0,
        }
    payload = _read_json(path)
    return {
        "name": name,
        "path": str(rel_path),
        "exists": True,
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "phase_matches_expected": payload.get("phase") == expected_phase,
        "profile": payload.get("profile"),
        "size_bytes": path.stat().st_size,
        "generated_at": payload.get("generated_at") or payload.get("completed_at") or payload.get("started_at"),
    }


def _validate_source_contracts(drill: dict[str, Any], pack: dict[str, Any], drill_path: Path, pack_path: Path) -> None:
    if drill.get("phase") != DRILL_PHASE:
        raise SystemExit(f"Drill report phase mismatch in {drill_path}: {drill.get('phase')!r}")
    if drill.get("status") != "PASS":
        raise SystemExit(f"Drill report is not PASS in {drill_path}: {drill.get('status')!r}")
    if pack.get("phase") != PACK_PHASE:
        raise SystemExit(f"Reviewer/demo pack phase mismatch in {pack_path}: {pack.get('phase')!r}")
    if pack.get("status") != "PASS":
        raise SystemExit(f"Reviewer/demo pack is not PASS in {pack_path}: {pack.get('status')!r}")
    safety = drill.get("safety", {})
    pack_safety = pack.get("safety", {})
    for source_name, source_safety in (("drill", safety), ("pack", pack_safety)):
        if source_safety.get("human_review_required") is not True:
            raise SystemExit(f"{source_name} does not prove human review is required")
        if source_safety.get("auto_dispatch_enabled") is not False:
            raise SystemExit(f"{source_name} does not prove auto-dispatch is disabled")
        if source_safety.get("external_dispatches_sent") != 0 or source_safety.get("external_messages_sent") != 0:
            raise SystemExit(f"{source_name} indicates external sends; refusing dashboard export")


def _metric_cards(drill: dict[str, Any], pack: dict[str, Any]) -> list[dict[str, Any]]:
    profile = drill.get("profile_context", {})
    gis = drill.get("gis", {})
    logistics = drill.get("logistics", {})
    volunteers = drill.get("volunteers", {})
    queue = drill.get("queue_resilience", {})
    safety = drill.get("safety", {})
    ranked_cases = gis.get("ranked_urgent_cases", []) if isinstance(gis.get("ranked_urgent_cases"), list) else []
    top_case_ids = [item.get("case_id") for item in ranked_cases[:3] if isinstance(item, dict)]

    return [
        {
            "id": "incident_profile",
            "title": "Incident profile",
            "status": "PASS",
            "audience": ["Local Coordinator", "Command Center Operator", "Reviewer"],
            "summary": f"{profile.get('label', 'Selected disaster profile')} around {profile.get('affected_zone_label', 'the affected zone')}.",
            "metrics": {
                "profile": drill.get("profile"),
                "relief_hub": profile.get("relief_hub_label"),
                "reachable_radius_km": profile.get("reachable_radius_km"),
                "blocked_areas": len(profile.get("blocked_areas", [])),
                "safe_areas": len(profile.get("safe_areas", [])),
            },
            "source": str(DRILL_REPORT_RELATIVE_PATH),
        },
        {
            "id": "gis_priority",
            "title": "GIS priority queue",
            "status": "PASS",
            "audience": ["Local Coordinator", "Command Center Operator"],
            "summary": "Urgent cases are assigned to the operation zone and ranked by priority and distance.",
            "metrics": {
                "urgent_cases_inserted": gis.get("urgent_cases_inserted"),
                "assigned_cases": len(gis.get("assigned_cases", [])),
                "ranked_urgent_cases": len(ranked_cases),
                "top_case_ids": top_case_ids,
            },
            "source": str(DRILL_REPORT_RELATIVE_PATH),
        },
        {
            "id": "logistics_assets",
            "title": "Logistics assets",
            "status": "PASS",
            "audience": ["Command Center Operator", "Reviewer"],
            "summary": "Requests, reservations, proposed dispatches, and overdue-asset reallocation remain review-gated.",
            "metrics": {
                "assets": len(logistics.get("assets", [])),
                "requests": len(logistics.get("requests", [])),
                "reservations": len(logistics.get("reservations", [])),
                "reallocations": len(logistics.get("reallocations", [])),
                "external_dispatches_sent": logistics.get("external_dispatches_sent"),
            },
            "source": str(DRILL_REPORT_RELATIVE_PATH),
        },
        {
            "id": "volunteer_surge",
            "title": "Volunteer surge",
            "status": "PASS",
            "audience": ["Local Coordinator", "Reviewer"],
            "summary": "Nearby volunteers are matched by location and skills, but messages are not sent automatically.",
            "metrics": {
                "registered_volunteers": len(volunteers.get("registered_volunteers", [])),
                "matches": len(volunteers.get("matches", [])),
                "external_messages_sent": volunteers.get("external_messages_sent"),
            },
            "source": str(DRILL_REPORT_RELATIVE_PATH),
        },
        {
            "id": "queue_resilience",
            "title": "Queue resilience",
            "status": "PASS",
            "audience": ["Command Center Operator", "Reviewer"],
            "summary": "Redis-style burst, crash, retry, DLQ, replay, and worker recovery evidence is summarized for runtime review.",
            "metrics": {
                "burst_size": queue.get("burst_size"),
                "worker_crash_after": queue.get("worker_crash_simulated_after_messages"),
                "dead_lettered": queue.get("dead_lettered"),
                "replayed_from_dlq": queue.get("replayed_from_dlq"),
                "remaining_dlq": queue.get("remaining_dlq"),
                "worker_recovered": queue.get("worker_recovered"),
            },
            "source": str(DRILL_REPORT_RELATIVE_PATH),
        },
        {
            "id": "review_safety",
            "title": "Review and safety",
            "status": "PASS",
            "audience": ["Local Coordinator", "Command Center Operator", "Reviewer"],
            "summary": "Dashboard keeps the human-review boundary visible: no real dispatches, no external messages, no hidden services.",
            "metrics": {
                "human_review_required": safety.get("human_review_required"),
                "auto_dispatch_enabled": safety.get("auto_dispatch_enabled"),
                "external_dispatches_sent": safety.get("external_dispatches_sent"),
                "external_messages_sent": safety.get("external_messages_sent"),
                "external_services_required": drill.get("external_services_required"),
            },
            "source": str(DRILL_REPORT_RELATIVE_PATH),
        },
        {
            "id": "reviewer_pack",
            "title": "Reviewer/demo pack",
            "status": "PASS",
            "audience": ["Reviewer"],
            "summary": "Reviewer-facing archive and scripts are linked from the dashboard state.",
            "metrics": {
                "artifacts": len(pack.get("artifacts", [])),
                "archive": pack.get("archive", {}).get("path"),
                "archive_size_bytes": pack.get("archive", {}).get("size_bytes"),
            },
            "source": str(PACK_REPORT_RELATIVE_PATH),
        },
    ]


def _role_views(cards: list[dict[str, Any]], drill: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    def card_ids_for(audience: str) -> list[str]:
        return [card["id"] for card in cards if audience in card.get("audience", [])]

    command_center_brief = drill.get("briefs", {}).get("command_center_decision_brief", {})
    coordinator_brief = drill.get("briefs", {}).get("coordinator_field_brief", {})
    reviewer_summary = pack.get("reviewer_summary", {})
    return {
        "command_center_operator": {
            "label": "Command Center Operator",
            "cards": card_ids_for("Command Center Operator"),
            "primary_actions": command_center_brief.get("decisions_needed", []),
            "focus": "runtime health, queue replay, logistics approvals, and reallocation review",
        },
        "local_coordinator": {
            "label": "Local Coordinator",
            "cards": card_ids_for("Local Coordinator"),
            "primary_actions": coordinator_brief.get("field_actions_to_review", []),
            "focus": "field-readable priorities, safe areas, blocked areas, and volunteer recommendations",
        },
        "reviewer": {
            "label": "Reviewer / Demo Judge",
            "cards": card_ids_for("Reviewer"),
            "primary_actions": [
                "Open the reviewer/demo pack archive.",
                "Check the safety contract and zero external-send evidence.",
                "Review the source drill and pack JSON contracts.",
            ],
            "focus": reviewer_summary.get("story", "connected disaster coordination evidence"),
        },
    }


def _links(pack: dict[str, Any]) -> list[dict[str, str]]:
    archive_path = pack.get("archive", {}).get("path") or str(PACK_RELATIVE_DIR / "reviewer_demo_pack.tar.gz")
    return [
        {"label": "Command-center drill JSON", "path": str(DRILL_REPORT_RELATIVE_PATH), "type": "json"},
        {"label": "Reviewer/demo pack JSON", "path": str(PACK_REPORT_RELATIVE_PATH), "type": "json"},
        {"label": "Reviewer/demo archive", "path": str(archive_path), "type": "tar.gz"},
        {"label": "Dashboard state JSON", "path": str(DASHBOARD_RELATIVE_DIR / DASHBOARD_REPORT_NAME), "type": "json"},
        {"label": "Dashboard HTML snapshot", "path": str(DASHBOARD_RELATIVE_DIR / DASHBOARD_HTML_NAME), "type": "html"},
        {"label": "Dashboard summary", "path": str(DASHBOARD_RELATIVE_DIR / DASHBOARD_SUMMARY_NAME), "type": "markdown"},
    ]


def _summary_markdown(dashboard: dict[str, Any]) -> str:
    lines = [
        "# ReliefQueue latest reports dashboard",
        "",
        f"Status: **{dashboard.get('status')}**",
        f"Profile: `{dashboard.get('profile')}`",
        "",
        "## What this proves",
        "",
        "The latest reports are wired into one lightweight dashboard state for demo and reviewer use. It is offline-safe, synthetic, and does not send dispatches or volunteer messages.",
        "",
        "## Dashboard cards",
        "",
    ]
    for card in dashboard.get("cards", []):
        lines.append(f"- **{card.get('title')}** — {card.get('summary')}")
    lines.extend(["", "## Role views", ""])
    for view in dashboard.get("role_views", {}).values():
        lines.append(f"- **{view.get('label')}**: {view.get('focus')}")
    lines.extend(["", "## Links", ""])
    for link in dashboard.get("links", []):
        lines.append(f"- {link.get('label')}: `{link.get('path')}`")
    return "\n".join(lines)


def _metric_value_to_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "0"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _html_dashboard(dashboard: dict[str, Any]) -> str:
    cards_html: list[str] = []
    for card in dashboard.get("cards", []):
        metrics = "".join(
            f"<li><span>{html.escape(str(key).replace('_', ' '))}</span><strong>{html.escape(_metric_value_to_text(value))}</strong></li>"
            for key, value in card.get("metrics", {}).items()
        )
        audience = ", ".join(card.get("audience", []))
        cards_html.append(
            f"""
<section class=\"card\" data-card-id=\"{html.escape(str(card.get('id')))}\">
  <p class=\"eyebrow\">{html.escape(audience)}</p>
  <h2>{html.escape(str(card.get('title')))}</h2>
  <p>{html.escape(str(card.get('summary')))}</p>
  <ul>{metrics}</ul>
  <p class=\"source\">Source: <code>{html.escape(str(card.get('source')))}</code></p>
</section>"""
        )

    roles_html: list[str] = []
    for role_id, view in dashboard.get("role_views", {}).items():
        cards = ", ".join(view.get("cards", []))
        roles_html.append(
            f"""
<section class=\"role\" data-role-id=\"{html.escape(str(role_id))}\">
  <h2>{html.escape(str(view.get('label')))}</h2>
  <p>{html.escape(str(view.get('focus')))}</p>
  <p><strong>Cards:</strong> {html.escape(cards)}</p>
</section>"""
        )

    links_html = "".join(
        f"<li>{html.escape(str(link.get('label')))} — <code>{html.escape(str(link.get('path')))}</code></li>"
        for link in dashboard.get("links", [])
    )
    embedded_json = html.escape(json.dumps(dashboard, sort_keys=True))
    safety = dashboard.get("safety", {})
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>ReliefQueue latest reports dashboard</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; }}
body {{ margin: 0; padding: 2rem; background: Canvas; color: CanvasText; }}
header {{ max-width: 1100px; margin: 0 auto 1.5rem; }}
.kicker {{ text-transform: uppercase; letter-spacing: .08em; font-size: .78rem; opacity: .75; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; max-width: 1100px; margin: 0 auto; }}
.card, .role, .links, .safety {{ border: 1px solid color-mix(in srgb, CanvasText 20%, transparent); border-radius: 16px; padding: 1rem; background: color-mix(in srgb, Canvas 92%, CanvasText 8%); }}
.card h2, .role h2 {{ margin: .1rem 0 .4rem; }}
.eyebrow, .source {{ font-size: .82rem; opacity: .8; }}
ul {{ padding-left: 1.1rem; }}
.card li {{ margin: .25rem 0; display: flex; justify-content: space-between; gap: 1rem; }}
.card li span {{ opacity: .8; }}
.full {{ max-width: 1100px; margin: 1rem auto; }}
code {{ white-space: normal; word-break: break-word; }}
</style>
</head>
<body>
<header>
  <p class=\"kicker\">{html.escape(str(dashboard.get('phase')))}</p>
  <h1>ReliefQueue latest reports dashboard</h1>
  <p>Status: <strong>{html.escape(str(dashboard.get('status')))}</strong> · Profile: <strong>{html.escape(str(dashboard.get('profile')))}</strong></p>
  <p>This is a static, offline-safe dashboard snapshot wired to the latest command-center drill and reviewer/demo pack reports.</p>
</header>
<section class=\"full safety\">
  <h2>Safety boundary</h2>
  <p>Human review required: <strong>{str(safety.get('human_review_required')).lower()}</strong> · Auto-dispatch enabled: <strong>{str(safety.get('auto_dispatch_enabled')).lower()}</strong> · External dispatches: <strong>{safety.get('external_dispatches_sent')}</strong> · External messages: <strong>{safety.get('external_messages_sent')}</strong></p>
</section>
<main class=\"grid\">
{''.join(cards_html)}
</main>
<section class=\"grid full\">
{''.join(roles_html)}
</section>
<section class=\"full links\">
  <h2>Report links</h2>
  <ul>{links_html}</ul>
</section>
<script id=\"reliefqueue-dashboard-state\" type=\"application/json\">{embedded_json}</script>
</body>
</html>"""


def build_latest_reports_dashboard(
    profile_name: str = "urban_flood",
    repo_root: Path | None = None,
    verbose_level: int = 0,
    refresh_pack: bool = False,
) -> dict[str, Any]:
    root = Path.cwd() if repo_root is None else Path(repo_root)
    drill_path = root / DRILL_REPORT_RELATIVE_PATH
    pack_path = root / PACK_REPORT_RELATIVE_PATH
    generated_by_refresh = False

    if refresh_pack or not drill_path.exists() or not pack_path.exists():
        export_reviewer_demo_pack(profile_name=profile_name, repo_root=root, verbose_level=verbose_level, refresh_drill=True)
        generated_by_refresh = True

    drill = _read_json(drill_path)
    pack = _read_json(pack_path)
    _validate_source_contracts(drill, pack, drill_path, pack_path)

    pack_safety = pack.get("safety", {})
    cards = _metric_cards(drill, pack)
    dashboard: dict[str, Any] = {
        "phase": PHASE,
        "status": "PASS",
        "generated_at": _utc_now(),
        "profile": drill.get("profile") or pack.get("profile") or profile_name,
        "integration_mode": "local_static_latest_report_dashboard",
        "external_services_required": False,
        "generated_by_refresh": generated_by_refresh,
        "source_reports": [
            _source_record("phase_02_06_command_center", drill_path, DRILL_REPORT_RELATIVE_PATH, DRILL_PHASE),
            _source_record("phase_02_07_reviewer_demo_pack", pack_path, PACK_REPORT_RELATIVE_PATH, PACK_PHASE),
        ],
        "cards": cards,
        "role_views": _role_views(cards, drill, pack),
        "links": _links(pack),
        "safety": {
            "synthetic_only": True,
            "human_review_required": pack_safety.get("human_review_required") is True,
            "auto_dispatch_enabled": False,
            "external_dispatches_sent": _safe_int(pack_safety.get("external_dispatches_sent")),
            "external_messages_sent": _safe_int(pack_safety.get("external_messages_sent")),
            "secrets_redacted": True,
        },
        "dashboard_outputs": {
            "json": str(DASHBOARD_RELATIVE_DIR / DASHBOARD_REPORT_NAME),
            "html": str(DASHBOARD_RELATIVE_DIR / DASHBOARD_HTML_NAME),
            "summary_markdown": str(DASHBOARD_RELATIVE_DIR / DASHBOARD_SUMMARY_NAME),
        },
    }

    dashboard_dir = root / DASHBOARD_RELATIVE_DIR
    _write_json(dashboard_dir / DASHBOARD_REPORT_NAME, dashboard)
    _write_text(dashboard_dir / DASHBOARD_SUMMARY_NAME, _summary_markdown(dashboard))
    _write_text(dashboard_dir / DASHBOARD_HTML_NAME, _html_dashboard(dashboard))
    return dashboard


def render_console_summary(dashboard: dict[str, Any], verbose_level: int = 0) -> str:
    verbose_level = clamp_verbose(verbose_level)
    cards = list(dashboard.get("cards", []))
    role_views = dashboard.get("role_views", {})
    safety = dashboard.get("safety", {})

    lines: list[str] = [
        f"ReliefQueue latest reports dashboard: {status_text(dashboard.get('status'))}",
        f"Profile: {dashboard.get('profile')}",
        "Outputs:",
        f"- dashboard JSON: {DASHBOARD_RELATIVE_DIR / DASHBOARD_REPORT_NAME}",
        f"- dashboard HTML: {DASHBOARD_RELATIVE_DIR / DASHBOARD_HTML_NAME}",
        f"- dashboard summary: {DASHBOARD_RELATIVE_DIR / DASHBOARD_SUMMARY_NAME}",
        "Dashboard result:",
        f"- cards ready: {len(cards)}",
        f"- role views ready: {len(role_views)}",
        "Safety:",
        f"- human review required: {true_false(safety.get('human_review_required'))}",
        f"- auto-dispatch enabled: {true_false(safety.get('auto_dispatch_enabled'))}",
        f"- external sends: {int(safety.get('external_dispatches_sent') or 0) + int(safety.get('external_messages_sent') or 0)}",
    ]

    if verbose_level >= 1:
        section(lines, "Cards")
        for card in cards:
            bullet(lines, f"{status_text(card.get('status'))}: {card.get('id')} — {card.get('title')}")

    if verbose_level >= 2:
        section(lines, "Role views")
        for role_id, view in role_views.items():
            bullet(lines, f"{role_id}: cards={list_text(view.get('cards', []))}")
        section(lines, "Safety contract")
        key_value(lines, "human_review_required", true_false(safety.get("human_review_required")))
        key_value(lines, "auto_dispatch_enabled", true_false(safety.get("auto_dispatch_enabled")))
        key_value(lines, "external_dispatches_sent", safety.get("external_dispatches_sent"))
        key_value(lines, "external_messages_sent", safety.get("external_messages_sent"))

    if verbose_level >= 3:
        section(lines, "Source reports")
        for source in dashboard.get("source_reports", []):
            bullet(lines, f"{source.get('name')}: {source.get('path')} status={status_text(source.get('status'))} size={source.get('size_bytes')}")
        section(lines, "Links")
        for link in dashboard.get("links", []):
            bullet(lines, f"{link.get('label')}: {link.get('path')}")

    if verbose_level >= 4:
        full_json_section(lines, "Full captured dashboard JSON", dashboard)

    return "\n".join(lines)

def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a lightweight dashboard from the latest ReliefQueue reports.")
    parser.add_argument("--profile", default=os.environ.get("PROFILE", "urban_flood"), help="Disaster profile used if source reports are refreshed.")
    parser.add_argument(
        "--refresh-pack",
        action="store_true",
        default=os.environ.get("REFRESH_PACK", "0") in {"1", "true", "TRUE", "yes", "YES"},
        help="Refresh phase-02-07, which refreshes phase-02-06 first, before building the dashboard.",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help=verbosity_help())
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    verbose_level = clamp_verbose(args.verbose)
    dashboard = build_latest_reports_dashboard(
        profile_name=args.profile,
        repo_root=Path.cwd(),
        verbose_level=verbose_level,
        refresh_pack=bool(args.refresh_pack),
    )
    print(render_console_summary(dashboard, verbose_level=verbose_level))
    return 0 if dashboard["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

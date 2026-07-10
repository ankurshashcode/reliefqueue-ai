from __future__ import annotations

import json
from pathlib import Path

from reliefqueue.latest_reports_dashboard import (
    DASHBOARD_HTML_NAME,
    DASHBOARD_RELATIVE_DIR,
    DASHBOARD_REPORT_NAME,
    DASHBOARD_SUMMARY_NAME,
    build_latest_reports_dashboard,
    render_console_summary,
)


def test_latest_reports_dashboard_contract(tmp_path: Path) -> None:
    dashboard = build_latest_reports_dashboard(profile_name="urban_flood", repo_root=tmp_path, verbose_level=2, refresh_pack=True)
    dashboard_path = tmp_path / DASHBOARD_RELATIVE_DIR / DASHBOARD_REPORT_NAME
    html_path = tmp_path / DASHBOARD_RELATIVE_DIR / DASHBOARD_HTML_NAME
    summary_path = tmp_path / DASHBOARD_RELATIVE_DIR / DASHBOARD_SUMMARY_NAME

    assert dashboard_path.exists()
    assert html_path.exists()
    assert summary_path.exists()
    loaded = json.loads(dashboard_path.read_text(encoding="utf-8"))

    assert loaded == dashboard
    assert loaded["status"] == "PASS"
    assert loaded["phase"] == "phase-02-08-lightweight-dashboard-wiring"
    assert loaded["integration_mode"] == "local_static_latest_report_dashboard"
    assert loaded["external_services_required"] is False
    assert loaded["generated_by_refresh"] is True
    assert len(loaded["source_reports"]) == 2
    assert all(item["exists"] for item in loaded["source_reports"])
    assert all(item["status"] == "PASS" for item in loaded["source_reports"])
    assert all(item["phase_matches_expected"] is True for item in loaded["source_reports"])
    assert len(loaded["cards"]) >= 7
    assert {card["id"] for card in loaded["cards"]} >= {
        "incident_profile",
        "gis_priority",
        "logistics_assets",
        "volunteer_surge",
        "queue_resilience",
        "review_safety",
        "reviewer_pack",
    }
    assert loaded["safety"]["human_review_required"] is True
    assert loaded["safety"]["auto_dispatch_enabled"] is False
    assert loaded["safety"]["external_dispatches_sent"] == 0
    assert loaded["safety"]["external_messages_sent"] == 0


def test_latest_reports_dashboard_outputs_are_static_and_role_aware(tmp_path: Path) -> None:
    dashboard = build_latest_reports_dashboard(profile_name="urban_flood", repo_root=tmp_path, verbose_level=0, refresh_pack=True)
    html_text = (tmp_path / DASHBOARD_RELATIVE_DIR / DASHBOARD_HTML_NAME).read_text(encoding="utf-8")
    summary_text = (tmp_path / DASHBOARD_RELATIVE_DIR / DASHBOARD_SUMMARY_NAME).read_text(encoding="utf-8")

    assert "ReliefQueue latest reports dashboard" in html_text
    assert "reliefqueue-dashboard-state" in html_text
    assert "http://" not in html_text
    assert "https://" not in html_text
    assert "Command Center Operator" in html_text
    assert "Local Coordinator" in html_text
    assert "Reviewer / Demo Judge" in html_text
    assert "Dashboard cards" in summary_text
    assert "Role views" in summary_text
    assert "Command Center Operator" in summary_text
    assert dashboard["role_views"]["command_center_operator"]["cards"]
    assert dashboard["role_views"]["local_coordinator"]["cards"]
    assert dashboard["role_views"]["reviewer"]["cards"]


def test_latest_reports_dashboard_verbosity_tiers_are_distinct(tmp_path: Path) -> None:
    dashboard = build_latest_reports_dashboard(profile_name="urban_flood", repo_root=tmp_path, verbose_level=4, refresh_pack=True)

    default_output = render_console_summary(dashboard, verbose_level=0)
    v_output = render_console_summary(dashboard, verbose_level=1)
    vv_output = render_console_summary(dashboard, verbose_level=2)
    vvv_output = render_console_summary(dashboard, verbose_level=3)
    vvvv_output = render_console_summary(dashboard, verbose_level=4)

    assert "Cards:" not in default_output
    assert "Cards:" in v_output
    assert "Role views:" in vv_output
    assert "Source reports:" in vvv_output
    assert "Full captured dashboard JSON:" in vvvv_output
    assert "role_views" in vvvv_output
    assert len(default_output.splitlines()) < len(v_output.splitlines()) < len(vv_output.splitlines()) < len(vvv_output.splitlines()) < len(vvvv_output.splitlines())

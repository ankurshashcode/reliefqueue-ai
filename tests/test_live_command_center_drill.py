from __future__ import annotations

import json
from pathlib import Path

from reliefqueue.live_command_center_drill import REPORT_RELATIVE_PATH, render_console_summary, run_drill


def test_live_command_center_drill_report_contract(tmp_path: Path) -> None:
    report = run_drill(profile_name="urban_flood", repo_root=tmp_path, verbose_level=2)
    report_path = tmp_path / REPORT_RELATIVE_PATH

    assert report_path.exists()
    loaded = json.loads(report_path.read_text(encoding="utf-8"))

    assert loaded["status"] == "PASS"
    assert loaded["phase"] == "phase-02-06-end-to-end-command-center-drill"
    assert loaded["profile"] == "urban_flood"
    assert loaded["integration_mode"] == "local_synthetic_end_to_end_evidence_drill"
    assert loaded["safety"]["human_review_required"] is True
    assert loaded["safety"]["auto_dispatch_enabled"] is False
    assert loaded["safety"]["external_dispatches_sent"] == 0
    assert loaded["safety"]["external_messages_sent"] == 0
    assert loaded["cleanup"]["synthetic_state_cleaned"] is True
    assert len(loaded["steps"]) >= 14
    assert len(loaded["gis"]["ranked_urgent_cases"]) >= 3
    assert loaded["logistics"]["external_dispatches_sent"] == 0
    assert len(loaded["logistics"]["reallocations"]) == 1
    assert len(loaded["volunteers"]["matches"]) >= 3
    assert loaded["queue_resilience"]["worker_recovered"] is True
    assert loaded["queue_resilience"]["remaining_dlq"] == 0
    assert report == loaded


def test_live_command_center_briefs_are_role_aware_and_review_gated(tmp_path: Path) -> None:
    report = run_drill(profile_name="urban_flood", repo_root=tmp_path, verbose_level=0)
    briefs = report["briefs"]

    assert briefs["command_center_decision_brief"]["audience"] == "Command Center Operator"
    assert briefs["coordinator_field_brief"]["audience"] == "Local Coordinator"
    assert briefs["reviewer_evidence_pack"]["audience"] == "Reviewer / Demo Judge"
    assert briefs["command_center_decision_brief"]["review_required"] is True
    assert briefs["coordinator_field_brief"]["review_required"] is True
    assert briefs["reviewer_evidence_pack"]["review_required"] is True
    assert "runtime_evidence" in briefs["command_center_decision_brief"]
    assert "field_actions_to_review" in briefs["coordinator_field_brief"]
    assert "evidence_items" in briefs["reviewer_evidence_pack"]


def test_live_command_center_verbosity_tiers_are_distinct(tmp_path: Path) -> None:
    report = run_drill(profile_name="urban_flood", repo_root=tmp_path, verbose_level=4)

    default_output = render_console_summary(report, verbose_level=0)
    v_output = render_console_summary(report, verbose_level=1)
    vv_output = render_console_summary(report, verbose_level=2)
    vvv_output = render_console_summary(report, verbose_level=3)
    vvvv_output = render_console_summary(report, verbose_level=4)

    assert "Steps:" not in default_output
    assert "Steps:" in v_output
    assert "Decision evidence:" in vv_output
    assert "Verbose briefs:" in vvv_output
    assert "Full captured report JSON:" in vvvv_output
    assert "ranked_urgent_cases" in vvvv_output
    assert len(default_output.splitlines()) < len(v_output.splitlines()) < len(vv_output.splitlines()) < len(vvv_output.splitlines()) < len(vvvv_output.splitlines())

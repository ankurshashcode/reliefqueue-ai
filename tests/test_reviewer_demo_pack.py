from __future__ import annotations

import json
import tarfile
from pathlib import Path

from reliefqueue.live_command_center_drill import REPORT_RELATIVE_PATH, run_drill
from reliefqueue.reviewer_demo_pack import PACK_RELATIVE_DIR, PACK_REPORT_NAME, export_reviewer_demo_pack, render_console_summary


def test_reviewer_demo_pack_exports_reviewable_artifacts(tmp_path: Path) -> None:
    run_drill(profile_name="urban_flood", repo_root=tmp_path, verbose_level=2)
    pack = export_reviewer_demo_pack(profile_name="urban_flood", repo_root=tmp_path, verbose_level=2)
    pack_dir = tmp_path / PACK_RELATIVE_DIR
    pack_path = pack_dir / PACK_REPORT_NAME

    assert pack_path.exists()
    loaded = json.loads(pack_path.read_text(encoding="utf-8"))
    assert loaded == pack
    assert loaded["status"] == "PASS"
    assert loaded["phase"] == "phase-02-07-reviewer-demo-pack-export"
    assert loaded["source_report"]["phase"] == "phase-02-06-end-to-end-command-center-drill"
    assert loaded["source_report"]["path"] == str(REPORT_RELATIVE_PATH)
    assert loaded["safety"]["human_review_required"] is True
    assert loaded["safety"]["auto_dispatch_enabled"] is False
    assert loaded["safety"]["external_dispatches_sent"] == 0
    assert loaded["safety"]["external_messages_sent"] == 0

    names = {artifact["name"] for artifact in loaded["artifacts"]}
    assert {
        "00_manifest.json",
        "01_demo_story.md",
        "02_command_center_brief.md",
        "03_coordinator_field_brief.md",
        "04_reviewer_evidence.md",
        "05_report_contract.json",
        "06_demo_script.md",
    }.issubset(names)

    assert "A flood is reported" in (pack_dir / "01_demo_story.md").read_text(encoding="utf-8")
    assert "Runtime evidence" in (pack_dir / "02_command_center_brief.md").read_text(encoding="utf-8")
    assert "Field actions to review" in (pack_dir / "03_coordinator_field_brief.md").read_text(encoding="utf-8")
    assert "External sends: 0" in (pack_dir / "04_reviewer_evidence.md").read_text(encoding="utf-8")
    assert len(json.loads((pack_dir / "05_report_contract.json").read_text(encoding="utf-8"))["source_steps"]) >= 14


def test_reviewer_demo_pack_archive_is_relative_and_complete(tmp_path: Path) -> None:
    run_drill(profile_name="urban_flood", repo_root=tmp_path, verbose_level=0)
    export_reviewer_demo_pack(profile_name="urban_flood", repo_root=tmp_path, verbose_level=0)
    archive_path = tmp_path / PACK_RELATIVE_DIR / "reviewer_demo_pack.tar.gz"

    assert archive_path.exists()
    with tarfile.open(archive_path, "r:gz") as tf:
        names = set(tf.getnames())
    assert "phase_02_07_reviewer_demo_pack/reviewer_demo_pack.json" in names
    assert "phase_02_07_reviewer_demo_pack/00_manifest.json" in names
    assert "phase_02_07_reviewer_demo_pack/01_demo_story.md" in names
    assert "phase_02_07_reviewer_demo_pack/06_demo_script.md" in names
    assert all(not name.startswith("/") and ".." not in Path(name).parts for name in names)


def test_reviewer_demo_pack_can_refresh_missing_source_drill(tmp_path: Path) -> None:
    pack = export_reviewer_demo_pack(profile_name="urban_flood", repo_root=tmp_path, verbose_level=1, refresh_drill=True)

    assert (tmp_path / REPORT_RELATIVE_PATH).exists()
    assert pack["source_report"]["generated_by_refresh"] is True
    assert pack["status"] == "PASS"


def test_reviewer_demo_pack_verbosity_tiers_are_distinct(tmp_path: Path) -> None:
    run_drill(profile_name="urban_flood", repo_root=tmp_path, verbose_level=0)
    pack = export_reviewer_demo_pack(profile_name="urban_flood", repo_root=tmp_path, verbose_level=4)

    default_output = render_console_summary(pack, verbose_level=0)
    v_output = render_console_summary(pack, verbose_level=1)
    vv_output = render_console_summary(pack, verbose_level=2)
    vvv_output = render_console_summary(pack, verbose_level=3)
    vvvv_output = render_console_summary(pack, verbose_level=4)

    assert "archive:" in default_output.lower()
    assert "Artifacts:" in v_output
    assert "Safety contract:" in vv_output
    assert "Artifact paths:" in vvv_output
    assert "Full captured pack JSON:" in vvvv_output
    assert "reviewer_summary" in vvvv_output
    assert len(default_output.splitlines()) < len(v_output.splitlines()) < len(vv_output.splitlines()) < len(vvv_output.splitlines()) < len(vvvv_output.splitlines())

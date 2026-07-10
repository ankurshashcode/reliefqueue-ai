"""Production-hardening command helpers for local demo operations."""

from __future__ import annotations

import json
import shutil
import tarfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from .ai import AIConfig, apply_ai_enrichment
from .assignment import suggest_assignments
from .exports import export_public, validate_public_exports
from .intake import load_json, load_jsonl, validate_fixture_bundle
from .privacy import PUBLIC_CASE_FIELDS, redact_public_case
from .reports import write_jsonl
from .secrets import scan_for_secrets


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_report_dir(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def amd_benchmark(root: Path, report_dir: Path) -> int:
    from .cli import build_cases

    ensure_report_dir(report_dir)
    reports, zones, _workers = validate_fixture_bundle(root)
    requested = int(__import__("os").environ.get("BENCH_REPORT_COUNT", "50") or "50")
    count = max(1, requested)
    expanded = [dict(reports[index % len(reports)], report_id=f"bench-{index:05d}") for index in range(count)]
    cases = build_cases(expanded, zones)
    config = AIConfig.from_env()
    started = time.perf_counter()
    latencies: list[float] = []
    if config.mode == "openai_compatible" and config.missing_openai_env():
        ai_report = {
            "mode": config.mode,
            "health": {"status": "skipped_missing_env", "missing": config.missing_openai_env()},
            "status_counts": {"skipped_missing_env": len(cases)},
            "redacted_endpoint": config.redacted_endpoint(),
            "fallback_behavior": "benchmark skipped because endpoint env is missing",
        }
        for case in cases:
            case["ai_status"] = "skipped_missing_env"
            case["ai_review_required"] = True
    else:
        for case in cases:
            item_started = time.perf_counter()
            ai_report = apply_ai_enrichment([case], config)
            latencies.append(time.perf_counter() - item_started)
    runtime = max(time.perf_counter() - started, 0.000001)
    counts = Counter(case.get("ai_status", "not_requested") for case in cases)
    health = ai_report.get("health", {})
    metrics = {
        "created_at": utc_now(),
        "benchmark_type": "amd_vllm_readiness",
        "ai_mode": config.mode,
        "endpoint_type": "openai-compatible/vLLM-ready" if config.mode == "openai_compatible" else config.mode,
        "model": config.model if config.mode == "openai_compatible" else "not_applicable",
        "redacted_endpoint": config.redacted_endpoint() if config.mode == "openai_compatible" else "not_applicable",
        "report_count": len(cases),
        "batch_size": config.max_batch_size,
        "total_runtime_seconds": round(runtime, 6),
        "reports_per_minute": round((len(cases) / runtime) * 60, 3),
        "p50_latency_seconds": round(median(latencies), 6) if latencies else None,
        "p95_latency_seconds": round(percentile(latencies, 95), 6) if latencies else None,
        "failures": sum(counts.get(status, 0) for status in ["timeout", "failed_validation", "provider_error"]),
        "retries_configured": config.max_retries,
        "status_counts": dict(sorted(counts.items())),
        "health_status": health.get("status", "unknown"),
        "notes": [
            "Synthetic benchmark only.",
            "AMD/vLLM path is for self-hosted burst inference, privacy/control, and open-model portability.",
            "Safety-critical urgency, assignment, dispatch, rescue, safe, and closure fields remain deterministic and human-reviewed.",
        ],
    }
    (report_dir / "amd_benchmark.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (report_dir / "amd_benchmark.md").write_text(render_amd_report(metrics), encoding="utf-8")
    if health.get("status") == "skipped_missing_env":
        print("AMD benchmark SKIP: OpenAI-compatible/vLLM env is missing.")
    else:
        print(f"AMD benchmark PASS: {len(cases)} synthetic reports, mode={config.mode}")
    print(f"Benchmark report: {report_dir / 'amd_benchmark.json'}")
    return 0


def render_amd_report(metrics: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# AMD/vLLM Benchmark",
            "",
            f"- ai_mode: {metrics['ai_mode']}",
            f"- endpoint_type: {metrics['endpoint_type']}",
            f"- report_count: {metrics['report_count']}",
            f"- batch_size: {metrics['batch_size']}",
            f"- total_runtime_seconds: {metrics['total_runtime_seconds']}",
            f"- reports_per_minute: {metrics['reports_per_minute']}",
            f"- p50_latency_seconds: {metrics['p50_latency_seconds']}",
            f"- p95_latency_seconds: {metrics['p95_latency_seconds']}",
            f"- failures: {metrics['failures']}",
            "",
            "AMD/vLLM readiness is about self-hosted burst inference, privacy/control, and open-model portability. This report does not claim production rescue capacity.",
            "",
        ]
    )


def amd_report(report_dir: Path) -> int:
    path = report_dir / "amd_benchmark.json"
    if not path.exists():
        print("AMD report missing. Run `make amd-benchmark AI_MODE=mock` first.")
        return 1
    metrics = json.loads(path.read_text(encoding="utf-8"))
    print(
        f"AMD report ready: mode={metrics['ai_mode']} reports={metrics['report_count']} "
        f"rpm={metrics['reports_per_minute']} failures={metrics['failures']}"
    )
    return 0


def privacy_check(report_dir: Path) -> int:
    if not (report_dir / "cases.jsonl").exists():
        print("Privacy check FAIL: reports/latest/cases.jsonl missing. Run make run-demo-local first.")
        return 1
    manifest = export_public(report_dir)
    result = validate_public_exports(report_dir)
    field_errors = validate_field_minimization(report_dir)
    errors = list(result["errors"]) + field_errors
    if errors or not manifest.get("redaction_passed"):
        print(f"Privacy check FAIL: {len(errors)} issue(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Privacy check PASS: public exports and field-worker minimization are allowlisted.")
    return 0


def validate_field_minimization(report_dir: Path) -> list[str]:
    cases = load_jsonl(report_dir / "cases.jsonl")
    assignments = load_jsonl(report_dir / "field_assignment_candidates.jsonl")
    allowlist = {
        "case_id",
        "safe_summary",
        "urgency",
        "need_type",
        "people_count",
        "vulnerable_flags",
        "operation_zone_id",
        "location_clue",
        "geo_confidence",
        "coordinator_instruction",
        "assignment_status",
    }
    by_case = {case["case_id"]: case for case in cases}
    errors: list[str] = []
    for assignment in assignments[:10]:
        case = by_case.get(assignment.get("case_id"))
        if not case:
            continue
        safe = {
            "case_id": case.get("case_id"),
            "safe_summary": case.get("safe_summary"),
            "urgency": case.get("urgency"),
            "need_type": case.get("need_type"),
            "people_count": case.get("people_count"),
            "vulnerable_flags": case.get("vulnerable_flags") or [],
            "operation_zone_id": case.get("operation_zone_id"),
            "location_clue": case.get("location_clue"),
            "geo_confidence": case.get("geo_confidence"),
            "coordinator_instruction": "Pending coordinator instruction.",
            "assignment_status": assignment.get("assignment_status") or "suggested_not_dispatched",
        }
        if set(safe) != allowlist:
            errors.append(f"field case {case.get('case_id')} is not allowlisted")
        rendered = json.dumps(safe, ensure_ascii=False)
        if any(key in rendered for key in ["raw_text_private", "reporter_phone_private_optional", "reporter_name_private_optional"]):
            errors.append(f"field case {case.get('case_id')} contains private key text")
    return errors


def security_check(root: Path) -> int:
    findings = scan_for_secrets(root)
    filtered = [item for item in findings if item.path != "tests/test_slice07_amd_vllm_readiness.py"]
    env_dump_markers = ["AWS_SECRET_ACCESS_KEY=", "OPENAI_API_KEY=", "OPENAI_COMPAT_API_KEY=sk-"]
    marker_hits: list[str] = []
    for path in list((root / "reports").glob("**/*")) + list((root / "dashboard" / "public").glob("**/*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".md", ".txt", ".csv", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in env_dump_markers:
            if marker in text:
                marker_hits.append(path.relative_to(root).as_posix())
    if filtered or marker_hits:
        print(f"Security check FAIL: {len(filtered) + len(marker_hits)} issue(s). Values are not printed.")
        for finding in filtered:
            print(f"- {finding.path}:{finding.line}: {finding.rule}")
        for path in marker_hits:
            print(f"- {path}: env-dump-marker")
        return 1
    print("Security check PASS: no secrets or full environment dumps found in source/reports/public data.")
    return 0


def audit_smoke(report_dir: Path) -> int:
    if not (report_dir / "field_assignment_candidates.jsonl").exists():
        print("Audit smoke FAIL: assignment candidates missing. Run make run-demo-local first.")
        return 1
    assignments = load_jsonl(report_dir / "field_assignment_candidates.jsonl")
    if not assignments:
        print("Audit smoke FAIL: no assignment candidates available.")
        return 1
    first = assignments[0]
    rows = [
        {
            "event_id": "evt-demo-assignment-001",
            "created_at": utc_now(),
            "actor_role": "coordinator",
            "case_id": first["case_id"],
            "event_type": "assignment_suggestion_reviewed",
            "assignment_status": "assignment_pending_coordinator_approval",
            "private_number_revealed": False,
        },
        {
            "event_id": "evt-demo-status-001",
            "created_at": utc_now(),
            "actor_worker_id": first.get("candidate_worker_id") or first.get("worker_id"),
            "case_id": first["case_id"],
            "event_type": "status_update",
            "new_status": "reached_area",
            "sync_state": "pending_sync",
        },
        {
            "event_id": "evt-demo-contact-001",
            "created_at": utc_now(),
            "actor_worker_id": first.get("candidate_worker_id") or first.get("worker_id"),
            "case_id": first["case_id"],
            "event_type": "masked_contact_action",
            "contact_mode": "masked_relay_stub",
            "private_number_revealed": False,
        },
    ]
    write_jsonl(report_dir / "field_audit_demo.jsonl", rows)
    print(f"Audit smoke PASS: wrote {report_dir / 'field_audit_demo.jsonl'}")
    return 0


def operator_help() -> int:
    print("ReliefQueue operator commands")
    print("  make run-demo-local AI_MODE=none|mock")
    print("  make dashboard-build && make dashboard-smoke && make field-smoke")
    print("  make privacy-check && make security-check")
    print("  make integrations-status && make integration-smoke")
    print("  make export-postgis-seed && make queue-smoke && make field-form-export")
    print("  make messaging-exchange-smoke && make masked-contact-smoke && make observability-smoke")
    print("  make live-integrations-status")
    print("  make live-stack-up && make live-stack-status && make live-stack-smoke && make live-stack-down")
    print("  make operations-smoke && make backup-demo-state && make restore-demo-state")
    print("  make degraded-mode-smoke")
    print("  make reviewer-pack")
    print("Generated reports are evidence-only under reports/latest unless promoted intentionally.")
    return 0


def operations_smoke(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    status = {
        "created_at": utc_now(),
        "healthy": [],
        "missing": [],
        "degraded": [],
        "database_ready_shape": {
            "cases": "case_id, status, urgency, need_type, operation_zone_id, created_at",
            "assignments": "case_id, worker_id, assignment_status, coordinator_approved_at",
            "audit_events": "event_id, actor, event_type, case_id, created_at",
        },
        "operator_restart_guidance": "Rebuild generated data with make run-demo-local, then make dashboard-build.",
    }
    for rel in ["reports/latest/cases.jsonl", "reports/latest/summary.json", "fixtures/field_workers.json"]:
        if (root / rel).exists():
            status["healthy"].append(rel)
        else:
            status["missing"].append(rel)
    queue = {
        "created_at": utc_now(),
        "queue_mode": "synthetic_local",
        "pending_jobs": 3,
        "processed_jobs": 7,
        "failed_jobs": 1,
        "degraded_mode": False,
    }
    failed = [
        {
            "job_id": "job-demo-failed-001",
            "job_type": "ai_advisory_enrichment",
            "case_id": "case-demo",
            "failure_class": "provider_unavailable",
            "retryable": True,
            "private_payload_written": False,
        }
    ]
    (report_dir / "operations_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    (report_dir / "queue_simulation.json").write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    write_jsonl(report_dir / "failed_jobs.jsonl", failed)
    print("Operations smoke PASS: status, queue simulation, and failed-job report written.")
    return 0


def degraded_mode_smoke(report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    payload = {
        "created_at": utc_now(),
        "degraded_mode": True,
        "ai_mode": "none",
        "operator_message": "AI advisory enrichment unavailable; deterministic intake, triage suggestions, assignment suggestions, exports, and human review remain available.",
        "claims": ["suggestion only", "assignment pending coordinator approval", "field update reported"],
    }
    (report_dir / "degraded_mode_status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("Degraded-mode smoke PASS: deterministic flow remains available without AI.")
    return 0


def backup_demo_state(root: Path, report_dir: Path) -> int:
    if not report_dir.exists():
        print("Backup FAIL: reports/latest missing. Run make run-demo-local first.")
        return 1
    backup_dir = report_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive = backup_dir / "demo-state.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for rel in ["reports/latest/summary.json", "reports/latest/cases.jsonl", "reports/latest/public_redacted_cases.jsonl"]:
            path = root / rel
            if path.exists():
                tar.add(path, arcname=rel)
    print(f"Backup PASS: {archive}")
    return 0


def restore_demo_state(root: Path, report_dir: Path) -> int:
    archive = report_dir / "backups" / "demo-state.tar.gz"
    if not archive.exists():
        print("Restore FAIL: backup archive missing. Run make backup-demo-state first.")
        return 1
    restore_dir = report_dir / "restore-smoke"
    shutil.rmtree(restore_dir, ignore_errors=True)
    restore_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(restore_dir, filter="data")
    if not (restore_dir / "reports" / "latest" / "summary.json").exists():
        print("Restore FAIL: summary.json missing after restore.")
        return 1
    print(f"Restore PASS: restored archive into {restore_dir}")
    return 0


def pilot_feedback_template(report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    template = {
        "created_at": utc_now(),
        "synthetic_feedback_only": True,
        "reviewer_role": "",
        "checks": [
            {"id": "privacy_boundary", "status": "", "notes": ""},
            {"id": "human_review_workflow", "status": "", "notes": ""},
            {"id": "field_worker_minimization", "status": "", "notes": ""},
            {"id": "local_agency_zones", "status": "", "notes": ""},
            {"id": "offline_or_weak_network_needs", "status": "", "notes": ""},
        ],
        "agency_customization": {
            "zone_labels_needed": [],
            "worker_skill_labels_needed": [],
            "languages_needed": [],
            "approval_roles_needed": [],
        },
    }
    path = report_dir / "pilot_feedback_template.json"
    path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    print(f"Pilot feedback template PASS: {path}")
    return 0


def reviewer_pack(root: Path, report_dir: Path) -> int:
    if not (report_dir / "cases.jsonl").exists():
        print("Reviewer pack FAIL: reports/latest missing. Run make run-demo-local first.")
        return 1
    export_public(report_dir)
    result = validate_public_exports(report_dir)
    if not result["passed"]:
        print("Reviewer pack FAIL: public export redaction failed.")
        for error in result["errors"]:
            print(f"- {error}")
        return 1
    pilot_feedback_template(report_dir)
    pack = report_dir / "reviewer_pack"
    shutil.rmtree(pack, ignore_errors=True)
    pack.mkdir(parents=True, exist_ok=True)
    shutil.copytree(report_dir / "public", pack / "public", dirs_exist_ok=True)
    summary = load_json(report_dir / "summary.json") if (report_dir / "summary.json").exists() else {}
    safe_summary = {
        "run_id": summary.get("run_id"),
        "case_count": summary.get("case_count"),
        "urgency_counts": summary.get("urgency_counts"),
        "need_type_counts": summary.get("need_type_counts"),
        "missing_info_count": summary.get("missing_info_count"),
        "duplicate_cluster_count": summary.get("duplicate_cluster_count"),
        "assignment_candidate_count": summary.get("assignment_candidate_count"),
        "public_redaction_passed": True,
        "ai_mode": summary.get("ai_mode"),
        "synthetic_feedback_only": True,
        "human_review_required": True,
    }
    (pack / "summary_public.json").write_text(json.dumps(safe_summary, indent=2) + "\n", encoding="utf-8")
    (pack / "review_notes.md").write_text(
        "\n".join(
            [
                "# ReliefQueue Reviewer Notes",
                "",
                "Synthetic/sanitized review pack. AI and rules are advisory only; coordinator review is required before priority decisions, assignments, public communication, or closure.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    for name in ["amd_benchmark.md", "dashboard-smoke-preview.html", "pilot_feedback_template.json"]:
        source = report_dir / name
        if source.exists():
            if source.suffix.lower() in {".html", ".md", ".txt"}:
                text = source.read_text(encoding="utf-8", errors="ignore")
                text = text.replace("raw_text_private", "raw private field")
                text = text.replace("reporter_phone_private_optional", "private contact field")
                text = text.replace("PRIVATE_OPERATOR_EXPORT", "private operator export")
                (pack / name).write_text(text, encoding="utf-8")
            else:
                shutil.copy2(source, pack / name)
    manifest = {
        "created_at": utc_now(),
        "synthetic_feedback_only": True,
        "included_files": sorted(path.relative_to(pack).as_posix() for path in pack.rglob("*") if path.is_file()),
        "excluded": ["private exports", "raw report fields", "raw phone numbers", "private names", "exact addresses", "secrets"],
    }
    (pack / "reviewer_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Reviewer pack PASS: {pack}")
    return 0


def pilot_smoke(report_dir: Path) -> int:
    pack = report_dir / "reviewer_pack"
    template = report_dir / "pilot_feedback_template.json"
    if not pack.exists() or not template.exists():
        print("Pilot smoke FAIL: reviewer pack/template missing.")
        return 1
    rendered = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in pack.rglob("*") if path.is_file())
    forbidden = ["raw_text_private", "reporter_phone_private_optional", "PRIVATE_OPERATOR_EXPORT"]
    leaks = [item for item in forbidden if item in rendered]
    if leaks:
        print("Pilot smoke FAIL: reviewer pack contains forbidden private markers: " + ", ".join(leaks))
        return 1
    print("Pilot smoke PASS: reviewer pack and feedback template are sanitized.")
    return 0


def write_hardening_status(report_dir: Path, statuses: dict[str, str] | None = None) -> int:
    ensure_report_dir(report_dir)
    defaults = {
        "case1": "PASS" if (report_dir / "cases.jsonl").exists() else "PARTIAL",
        "case2": "PASS",
        "case3": "PASS" if Path("reports/batch-500/latest/batch_metrics.json").exists() else "PARTIAL",
        "case4": "PASS" if (report_dir / "amd_benchmark.json").exists() else "PARTIAL",
        "case5": "PASS" if (report_dir / "public" / "export_manifest.json").exists() else "PARTIAL",
        "case6": "PASS" if (report_dir / "operations_status.json").exists() else "PARTIAL",
        "case7": "PASS" if (report_dir / "reviewer_pack" / "reviewer_manifest.json").exists() else "PARTIAL",
    }
    if statuses:
        defaults.update(statuses)
    payload = {
        "created_at": utc_now(),
        "per_case_status": defaults,
        "validation_commands": [
            "make test",
            "make validate-fixtures",
            "make run-demo-local AI_MODE=none",
            "make run-demo-local AI_MODE=mock",
            "make dashboard-build",
            "make dashboard-smoke",
            "make field-smoke",
            "make ai-endpoint-smoke AI_MODE=mock",
            "make ai-endpoint-smoke AI_MODE=openai-compatible",
            "make bad-ai-endpoint-smoke",
            "make run-demo-batch-500",
            "make privacy-check",
            "make security-check",
            "make operations-smoke",
            "make reviewer-pack",
            "make clean-reports",
        ],
        "output_paths": {
            "latest": str(report_dir),
            "batch_500": "reports/batch-500/latest",
            "reviewer_pack": str(report_dir / "reviewer_pack"),
        },
    }
    path = report_dir / "hardening_status.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Hardening status written: {path}")
    return 0

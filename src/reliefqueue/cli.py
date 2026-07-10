"""Command line entry points for the local ReliefQueue pipeline."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from .ai import AIConfig, apply_ai_enrichment
from .assignment import assignment_ready, suggest_assignments
from .batch import batch_report, run_batch_demo
from .duplicates import apply_duplicate_groups
from .exports import export_private, export_public, validate_public_exports
from .fixture_expander import expand_seed_fixture_file
from .geo import tag_zone
from .hardening import (
    amd_benchmark,
    amd_report,
    audit_smoke,
    backup_demo_state,
    degraded_mode_smoke,
    operations_smoke,
    pilot_feedback_template,
    pilot_smoke,
    privacy_check,
    restore_demo_state,
    reviewer_pack,
    security_check,
    write_hardening_status,
)
from .integrations import (
    export_postgis_seed,
    field_form_export,
    integration_smoke,
    integrations_status,
    live_integrations_status,
    masked_contact_smoke,
    messaging_exchange_smoke,
    observability_smoke,
    queue_smoke,
)
from .container_runtime import container_runtime_readiness
from .live_integrations import COMMANDS as LIVE_PHASE_COMMANDS, run_live_integration_command
from .live_stack import live_stack_down, live_stack_smoke, live_stack_status, live_stack_up
from .intake import ValidationError, validate_fixture_bundle
from .models import stable_case_id
from .operator_catalog import catalog_check, render_operator_help, render_scope, render_search
from .phase01_host import phase01_host_preflight, phase01_host_setup
from .phase01_live import phase01_live_clean, phase01_live_proof
from .reports import build_summary, write_outputs
from .secrets import SecretFinding, scan_for_secrets
from .triage import (
    detect_language,
    detect_need_type,
    detect_vulnerable_flags,
    extract_people_count,
    required_skills,
    safe_summary,
    urgency_for,
)
from .validation import render_validation_markdown, validate_expected_behavior


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "latest"


def build_cases(reports: list[dict[str, Any]], zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for report in reports:
        text = str(report["text"])
        geo = tag_zone(report, zones)
        need_type = detect_need_type(text)
        people_count = extract_people_count(text)
        vulnerable_flags = detect_vulnerable_flags(text)
        missing_fields = []
        if not geo.get("operation_zone_id"):
            missing_fields.append("location")
        if need_type == "unknown":
            missing_fields.append("need_type")
        if people_count is None and need_type not in {"information_request"}:
            missing_fields.append("people_count")
        if not report.get("reporter_phone_private_optional"):
            missing_fields.append("contact_possible")
        urgency, reasons = urgency_for(text, need_type, missing_fields, vulnerable_flags)
        case = {
            "case_id": stable_case_id(report["report_id"]),
            "source_report_id": report["report_id"],
            "source_channel": report["source_channel"],
            "language_hint": detect_language(text),
            "raw_text_private": text,
            "safe_summary": "",
            "urgency": urgency,
            "urgency_reasons": reasons,
            "need_type": need_type,
            "people_count": people_count,
            "vulnerable_flags": vulnerable_flags,
            "missing_fields": missing_fields,
            "duplicate_key": "",
            "duplicate_cluster_id": "",
            "duplicate_cluster_size": 1,
            "location_clue": geo["location_clue"],
            "geo_scope_type": geo["geo_scope_type"],
            "geo_confidence": geo["geo_confidence"],
            "operation_zone_id": geo["operation_zone_id"],
            "required_skills": required_skills(need_type, text, vulnerable_flags),
            "assignment_ready": False,
            "human_review_required": urgency == "REVIEW" or bool(missing_fields),
            "suggested_reply_draft": "A coordinator should review this report and approve any field action.",
            "privacy_level": "PRIVATE_OPERATOR_EXPORT_DO_NOT_SHARE_PUBLICLY",
            "created_from_synthetic_fixture": True,
            "reporter_name_private_optional": report.get("reporter_name_private_optional"),
            "reporter_phone_private_optional": report.get("reporter_phone_private_optional"),
            "media_note_private_optional": report.get("media_note_private_optional"),
        }
        case["safe_summary"] = safe_summary(case)
        case["assignment_ready"] = assignment_ready(case)
        cases.append(case)
    apply_duplicate_groups(cases)
    return cases


def validate_fixtures(root: Path = ROOT) -> int:
    reports, zones, workers = validate_fixture_bundle(root)
    print(f"Fixture validation PASS: {len(reports)} reports, {len(zones)} zones, {len(workers)} workers")
    return 0


def run_demo(root: Path = ROOT, report_dir: Path = REPORT_DIR) -> int:
    reports, zones, workers = validate_fixture_bundle(root)
    cases = build_cases(reports, zones)
    ai_report = apply_ai_enrichment(cases, AIConfig.from_env())
    suggestions = suggest_assignments(cases, workers)
    errors, notes = validate_expected_behavior(root, reports, cases, suggestions)
    summary = build_summary(cases, suggestions, ai_report=ai_report)
    validation = render_validation_markdown(errors, notes, summary, ai_report)
    write_outputs(report_dir, cases, suggestions, validation, zones, ai_report)
    if errors:
        print(f"Demo generated reports with validation FAIL: {len(errors)} errors")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Demo generated reports in {report_dir}")
    print("Validation PASS")
    return 0


def export_report(root: Path = ROOT, report_dir: Path = REPORT_DIR) -> int:
    required = [
        "summary.json",
        "cases.jsonl",
        "validation.md",
        "zone_summary.csv",
        "field_assignment_candidates.jsonl",
        "public_redacted_cases.jsonl",
    ]
    missing = [name for name in required if not (report_dir / name).exists()]
    if missing:
        print("Missing report files: " + ", ".join(missing))
        print("Run `make run-demo-local` first.")
        return 1
    print(f"Report export ready: {report_dir.relative_to(root)}")
    for name in required:
        print(f"- {name}")
    return 0


def export_private_command(report_dir: Path = REPORT_DIR) -> int:
    try:
        manifest = export_private(report_dir)
    except FileNotFoundError as exc:
        print(f"Private export FAIL: {exc}")
        print("Run `make run-demo-local` first.")
        return 1
    print(f"Private export ready: {report_dir / 'private'}")
    for name in manifest["files"]:
        print(f"- {name}")
    return 0


def export_public_command(report_dir: Path = REPORT_DIR) -> int:
    try:
        manifest = export_public(report_dir)
    except FileNotFoundError as exc:
        print(f"Public export FAIL: {exc}")
        print("Run `make run-demo-local` first.")
        return 1
    print(f"Public export ready: {report_dir / 'public'}")
    print(f"Redaction passed: {manifest.get('redaction_passed')}")
    for name in manifest["files"]:
        print(f"- {name}")
    if not manifest.get("redaction_passed"):
        print("Public export FAIL: redaction validator did not pass.")
        return 1
    return 0


def validate_redaction_command(report_dir: Path = REPORT_DIR) -> int:
    result = validate_public_exports(report_dir)
    if result["passed"]:
        print(f"Redaction validation PASS: {report_dir / 'public'}")
        return 0
    print(f"Redaction validation FAIL: {len(result['errors'])} issue(s)")
    for error in result["errors"]:
        print(f"- {error}")
    return 1


def expand_fixtures(count: int, seed: int, out_path: Path, root: Path = ROOT) -> int:
    rows = expand_seed_fixture_file(
        root / "fixtures" / "reliefqueue_seed_reports.jsonl",
        count=count,
        seed=seed,
        out_path=out_path,
    )
    print(f"Expanded {len(rows)} synthetic reports to {out_path}")
    return 0



def _sanitize_ai_smoke_detail(value: str) -> str:
    sanitized = re.sub(r"(?i)(authorization|bearer|api[_-]?key|token|secret)([\s:=]+)([^\s,;]+)", r"\1\2<redacted>", value)
    sanitized = re.sub(r"\b(?:sk|fw|fireworks)[-_][A-Za-z0-9_\-]{12,}\b", "<redacted-api-key>", sanitized)
    sanitized = re.sub(r"\+?\d[\d\s().-]{8,}\d", "<redacted-phone>", sanitized)
    sanitized = " ".join(sanitized.split())
    return sanitized[:240] + ("..." if len(sanitized) > 240 else "")


def _print_ai_smoke_failure_details(cases: list[dict[str, Any]]) -> None:
    details: list[tuple[str, str, str]] = []
    for case in cases:
        status = str(case.get("ai_status") or "unknown")
        if status == "success":
            continue
        error = str(case.get("ai_error") or "").strip()
        if not error:
            continue
        case_id = str(case.get("case_id") or case.get("source_report_id") or "unknown-case")
        details.append((case_id, status, _sanitize_ai_smoke_detail(error)))
    if not details:
        return
    print("AI failure details:")
    for case_id, status, error in details:
        print(f"- {case_id}: {status}: {error}")


def _endpoint_smoke_case() -> dict[str, Any]:
    return {
        "case_id": "synthetic-endpoint-smoke",
        "source_report_id": "synthetic-endpoint-smoke",
        "source_channel": "synthetic_smoke",
        "language_hint": "en",
        "safe_summary": "Synthetic endpoint smoke case requesting a safe advisory JSON response.",
        "urgency": "GREEN",
        "need_type": "information_request",
        "missing_fields": ["location"],
        "operation_zone_id": "synthetic-zone",
        "vulnerable_flags": [],
        "human_review_required": True,
        "assignment_ready": False,
        "created_from_synthetic_fixture": True,
    }


def ai_smoke(root: Path = ROOT) -> int:
    reports, zones, _workers = validate_fixture_bundle(root)
    cases = build_cases(reports[:2], zones)
    ai_report = apply_ai_enrichment(cases, AIConfig.from_env())
    status_counts = ai_report["status_counts"]
    print(f"AI smoke mode: {ai_report['mode']}")
    print(f"AI health: {ai_report['health'].get('status')}")
    print(f"AI status counts: {status_counts}")
    print(f"AI endpoint: {ai_report['redacted_endpoint']}")
    if ai_report["mode"] == "mock" and status_counts.get("success") != len(cases):
        print("AI smoke FAIL: mock mode did not enrich all sampled cases")
        return 1
    if ai_report["mode"] == "openai_compatible":
        health_status = ai_report["health"].get("status")
        if health_status == "skipped_missing_env":
            print("AI smoke degraded-mode PASS: OpenAI-compatible env is missing, so no network call was made.")
            return 0
        if status_counts.get("success") != len(cases):
            _print_ai_smoke_failure_details(cases)
            print("AI smoke FAIL: configured OpenAI-compatible endpoint did not enrich all sampled cases.")
            return 1
    return 0


def ai_endpoint_smoke() -> int:
    config = AIConfig.from_env()
    print(f"AI endpoint smoke mode: {config.mode}")
    print(f"AI endpoint smoke base_url: {config.redacted_endpoint() if config.mode == 'openai_compatible' else 'not_applicable'}")
    print(f"AI endpoint smoke model: {config.model if config.mode == 'openai_compatible' else 'not_applicable'}")
    print("AI endpoint smoke payload: synthetic_safe_text_only")

    if config.mode == "none":
        print("AI endpoint smoke SKIP: AI_MODE=none; deterministic case flow remains available.")
        return 0
    if config.mode == "mock":
        cases = [_endpoint_smoke_case()]
        report = apply_ai_enrichment(cases, config)
        print(f"AI endpoint smoke health: {report['health'].get('status')}")
        print(f"AI endpoint smoke status counts: {report['status_counts']}")
        if report["status_counts"].get("success") == 1 and cases[0].get("ai_review_required") is True:
            print("AI endpoint smoke mock PASS: no network call was made.")
            return 0
        print("AI endpoint smoke FAIL: mock mode did not return advisory output.")
        return 1
    if config.mode != "openai_compatible":
        print("AI endpoint smoke SKIP: unsupported AI_MODE resolved to deterministic no-AI behavior.")
        return 0

    cases = [_endpoint_smoke_case()]
    report = apply_ai_enrichment(cases, config)
    health_status = report["health"].get("status")
    print(f"AI endpoint smoke health: {health_status}")
    print(f"AI endpoint smoke status counts: {report['status_counts']}")
    if health_status == "skipped_missing_env":
        missing = ", ".join(report["health"].get("missing") or [])
        print(f"AI endpoint smoke SKIP: missing endpoint env: {missing}")
        return 0
    if report["status_counts"].get("success") == 1 and cases[0].get("ai_review_required") is True:
        print("AI endpoint smoke PASS: endpoint returned advisory output requiring human review.")
        return 0
    _print_ai_smoke_failure_details(cases)
    print("AI endpoint smoke FAIL: configured endpoint did not return valid advisory output.")
    return 1


def no_secrets(root: Path = ROOT) -> int:
    findings = [
        finding
        for finding in scan_for_secrets(root)
        if not _is_intentional_no_secrets_fixture(root, finding)
    ]
    if not findings:
        print("No-secrets PASS: scanned source, docs, env examples, reports, and public exports.")
        return 0
    print(f"No-secrets FAIL: {len(findings)} possible secret issue(s). Values are not printed.")
    for finding in findings:
        print(f"- {finding.path}:{finding.line}: {finding.rule}")
    return 1


def _is_intentional_no_secrets_fixture(root: Path, finding: SecretFinding) -> bool:
    """Allow only the test fixture that proves real .env secrets are reported."""

    expected_rule = "-".join(("secret", "assignment"))
    if finding.path != "tests/test_slice07_amd_vllm_readiness.py" or finding.rule != expected_rule:
        return False
    try:
        line = (root / finding.path).read_text(encoding="utf-8").splitlines()[finding.line - 1]
    except (IndexError, OSError, UnicodeDecodeError):
        return False
    expected_key = "OPENAI_COMPAT_API" + "_KEY"
    expected_value = "sk-" + "realSecretValue1234567890"
    return f"{expected_key}={expected_value}" in line


def production_readiness_status(root: Path = ROOT, report_dir: Path = REPORT_DIR, summary_only: bool = False) -> int:
    from .production_readiness import plain_summary, write_status

    if summary_only:
        print(plain_summary(root, report_dir))
        return 0
    path = write_status(root, report_dir)
    print(f"Production readiness status written: {path.relative_to(root)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ReliefQueue AI local commands")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate-fixtures")
    subcommands.add_parser("run-demo-local")
    subcommands.add_parser("export-report")
    private_parser = subcommands.add_parser("export-private")
    private_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    public_parser = subcommands.add_parser("export-public")
    public_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    redaction_parser = subcommands.add_parser("validate-redaction")
    redaction_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    subcommands.add_parser("ai-smoke")
    subcommands.add_parser("ai-endpoint-smoke")
    subcommands.add_parser("no-secrets")
    expand_parser = subcommands.add_parser("expand-fixtures")
    expand_parser.add_argument("--count", type=int, required=True)
    expand_parser.add_argument("--seed", type=int, required=True)
    expand_parser.add_argument("--out", type=Path, required=True)
    batch_parser = subcommands.add_parser("run-demo-batch")
    batch_parser.add_argument("--count", type=int, required=True, choices=[100, 500, 5000])
    batch_parser.add_argument("--seed", type=int, default=42)
    subcommands.add_parser("batch-report")
    subcommands.add_parser("amd-benchmark")
    subcommands.add_parser("amd-report")
    subcommands.add_parser("privacy-check")
    subcommands.add_parser("security-check")
    subcommands.add_parser("audit-smoke")
    subcommands.add_parser("operator")
    search_parser = subcommands.add_parser("operator-search")
    search_parser.add_argument("--query", required=True)
    scope_parser = subcommands.add_parser("operator-scope")
    scope_parser.add_argument("--action", required=True)
    subcommands.add_parser("operator-catalog-check")
    subcommands.add_parser("phase01-host-preflight")
    subcommands.add_parser("phase01-host-setup")
    subcommands.add_parser("phase01-live-proof")
    subcommands.add_parser("phase01-live-clean")
    subcommands.add_parser("operations-smoke")
    subcommands.add_parser("degraded-mode-smoke")
    subcommands.add_parser("backup-demo-state")
    subcommands.add_parser("restore-demo-state")
    subcommands.add_parser("reviewer-pack")
    subcommands.add_parser("pilot-feedback-template")
    subcommands.add_parser("pilot-smoke")
    subcommands.add_parser("write-hardening-status")
    subcommands.add_parser("integrations-status")
    subcommands.add_parser("integration-smoke")
    subcommands.add_parser("export-postgis-seed")
    subcommands.add_parser("queue-smoke")
    subcommands.add_parser("field-form-export")
    subcommands.add_parser("messaging-exchange-smoke")
    subcommands.add_parser("masked-contact-smoke")
    subcommands.add_parser("observability-smoke")
    subcommands.add_parser("live-integrations-status")
    subcommands.add_parser("container-runtime-readiness")
    subcommands.add_parser("production-readiness-status")
    subcommands.add_parser("production-readiness-summary")
    for command in LIVE_PHASE_COMMANDS:
        live_parser = subcommands.add_parser(command)
        live_parser.add_argument("-v", "--verbose", action="count", default=0, help="increase live evidence verbosity; use -vv or -vvv for more detail")
    live_stack_parser = subcommands.add_parser("live-stack")
    live_stack_subcommands = live_stack_parser.add_subparsers(dest="live_stack_command", required=True)
    live_stack_subcommands.add_parser("up")
    live_stack_subcommands.add_parser("status")
    live_stack_subcommands.add_parser("smoke")
    live_stack_subcommands.add_parser("down")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-fixtures":
            return validate_fixtures()
        if args.command == "run-demo-local":
            return run_demo()
        if args.command == "export-report":
            return export_report()
        if args.command == "export-private":
            return export_private_command(args.report_dir)
        if args.command == "export-public":
            return export_public_command(args.report_dir)
        if args.command == "validate-redaction":
            return validate_redaction_command(args.report_dir)
        if args.command == "ai-smoke":
            return ai_smoke()
        if args.command == "ai-endpoint-smoke":
            return ai_endpoint_smoke()
        if args.command == "no-secrets":
            return no_secrets()
        if args.command == "expand-fixtures":
            return expand_fixtures(args.count, args.seed, args.out)
        if args.command == "run-demo-batch":
            return run_batch_demo(ROOT, count=args.count, seed=args.seed)
        if args.command == "batch-report":
            return batch_report(ROOT)
        if args.command == "amd-benchmark":
            return amd_benchmark(ROOT, REPORT_DIR)
        if args.command == "amd-report":
            return amd_report(REPORT_DIR)
        if args.command == "privacy-check":
            return privacy_check(REPORT_DIR)
        if args.command == "security-check":
            return security_check(ROOT)
        if args.command == "audit-smoke":
            return audit_smoke(REPORT_DIR)
        if args.command == "operator":
            print(render_operator_help())
            return 0
        if args.command == "operator-search":
            print(render_search(args.query))
            return 0
        if args.command == "operator-scope":
            exit_code, rendered = render_scope(args.action)
            print(rendered)
            return exit_code
        if args.command == "operator-catalog-check":
            exit_code, errors = catalog_check(ROOT)
            if errors:
                print(f"Operator catalog check FAIL: {len(errors)} issue(s)")
                for error in errors:
                    print(f"- {error}")
            else:
                print("Operator catalog check PASS")
            return exit_code
        if args.command == "phase01-host-preflight":
            return phase01_host_preflight(ROOT, REPORT_DIR)
        if args.command == "phase01-host-setup":
            return phase01_host_setup(ROOT, REPORT_DIR)
        if args.command == "phase01-live-proof":
            return phase01_live_proof(ROOT, REPORT_DIR)
        if args.command == "phase01-live-clean":
            return phase01_live_clean(ROOT, REPORT_DIR)
        if args.command == "operations-smoke":
            return operations_smoke(ROOT, REPORT_DIR)
        if args.command == "degraded-mode-smoke":
            return degraded_mode_smoke(REPORT_DIR)
        if args.command == "backup-demo-state":
            return backup_demo_state(ROOT, REPORT_DIR)
        if args.command == "restore-demo-state":
            return restore_demo_state(ROOT, REPORT_DIR)
        if args.command == "reviewer-pack":
            return reviewer_pack(ROOT, REPORT_DIR)
        if args.command == "pilot-feedback-template":
            return pilot_feedback_template(REPORT_DIR)
        if args.command == "pilot-smoke":
            return pilot_smoke(REPORT_DIR)
        if args.command == "write-hardening-status":
            return write_hardening_status(REPORT_DIR)
        if args.command == "integrations-status":
            return integrations_status(ROOT, REPORT_DIR)
        if args.command == "integration-smoke":
            return integration_smoke(ROOT, REPORT_DIR)
        if args.command == "export-postgis-seed":
            return export_postgis_seed(ROOT, REPORT_DIR)
        if args.command == "queue-smoke":
            return queue_smoke(ROOT, REPORT_DIR)
        if args.command == "field-form-export":
            return field_form_export(ROOT, REPORT_DIR)
        if args.command == "messaging-exchange-smoke":
            return messaging_exchange_smoke(ROOT, REPORT_DIR)
        if args.command == "masked-contact-smoke":
            return masked_contact_smoke(ROOT, REPORT_DIR)
        if args.command == "observability-smoke":
            return observability_smoke(ROOT, REPORT_DIR)
        if args.command == "live-integrations-status":
            return live_integrations_status(ROOT, REPORT_DIR)
        if args.command == "container-runtime-readiness":
            return container_runtime_readiness(ROOT, REPORT_DIR)
        if args.command == "production-readiness-status":
            return production_readiness_status(ROOT, REPORT_DIR)
        if args.command == "production-readiness-summary":
            return production_readiness_status(ROOT, REPORT_DIR, summary_only=True)
        if args.command in LIVE_PHASE_COMMANDS:
            verbose_level = int(getattr(args, "verbose", 0) or 0)
            if verbose_level:
                os.environ["RELIEFQUEUE_LIVE_VERBOSE_LEVEL"] = str(verbose_level)
                if args.command == "live-stateful-mutation-drill":
                    os.environ["RELIEFQUEUE_LIVE_MUTATION_VERBOSE"] = str(verbose_level)
                if args.command == "live-logistics-asset-drill":
                    os.environ["RELIEFQUEUE_LIVE_LOGISTICS_VERBOSE"] = str(verbose_level)
                if args.command == "live-volunteer-surge-drill":
                    os.environ["RELIEFQUEUE_LIVE_VOLUNTEER_VERBOSE"] = str(verbose_level)
            return run_live_integration_command(args.command, ROOT, REPORT_DIR)
        if args.command == "live-stack":
            if args.live_stack_command == "up":
                return live_stack_up(ROOT, REPORT_DIR)
            if args.live_stack_command == "status":
                return live_stack_status(ROOT, REPORT_DIR)
            if args.live_stack_command == "smoke":
                return live_stack_smoke(ROOT, REPORT_DIR)
            if args.live_stack_command == "down":
                return live_stack_down(ROOT, REPORT_DIR)
    except ValidationError as exc:
        print(f"Validation FAIL: {exc}")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

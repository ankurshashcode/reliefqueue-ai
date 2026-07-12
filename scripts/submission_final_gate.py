#!/usr/bin/env python3
"""Run the final local submission gate and preserve one auditable report."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVIDER_ENV_KEYS = {
    "OPENAI_COMPAT_BASE_URL",
    "OPENAI_COMPAT_API_KEY",
    "OPENAI_COMPAT_MODEL",
    "OPENAI_COMPAT_UNDERLYING_MODEL",
    "FIREWORKS_API_KEY",
    "FIREWORKS_BASE_URL",
    "FIREWORKS_MODEL",
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitized_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in PROVIDER_ENV_KEYS:
        env.pop(key, None)
    env["AI_MODE"] = "mock"
    env["PYTHONPATH"] = "src"
    return env


def command_plan(fast: bool = False, include_public: bool = False) -> list[tuple[str, list[str]]]:
    plan: list[tuple[str, list[str]]] = [
        ("amd-evidence-validate", ["python3", "scripts/amd_evidence_report.py"]),
        ("repository-tests", ["python3", "-m", "unittest", "discover", "-s", "tests"]),
        ("no-secrets", ["python3", "-m", "reliefqueue.cli", "no-secrets"]),
        ("public-ship-check", ["python3", "scripts/public_ship_check.py"]),
        ("dashboard-build", ["make", "dashboard-build"]),
        ("amd-evidence-ui-check", ["npm", "--prefix", "dashboard", "run", "amd-evidence-ui-check"]),
        ("command-center-click-smoke", ["npm", "--prefix", "dashboard", "run", "command-center-click-smoke"]),
        ("field-app-click-smoke", ["npm", "--prefix", "dashboard", "run", "field-app-click-smoke"]),
        ("local-coordinator-click-smoke", ["npm", "--prefix", "dashboard", "run", "local-coordinator-click-smoke"]),
    ]
    if not fast:
        plan.extend(
            [
                ("product-complete-smoke", ["npm", "--prefix", "dashboard", "run", "product-complete-smoke"]),
                ("replit-smoke", ["bash", "scripts/replit_smoke.sh"]),
                ("replit-navigation-smoke", ["npm", "--prefix", "dashboard", "run", "replit-navigation-smoke"]),
            ]
        )
    plan.append(("submission-pack", ["python3", "-m", "reliefqueue.submission_pack"]))
    if include_public:
        plan.append(("submission-public-check", ["python3", "scripts/submission_public_check.py", os.environ["RELIEFQUEUE_PUBLIC_URL"]]))
    return plan


def run_gate(repo_root: Path, output_dir: Path, fast: bool = False) -> dict[str, Any]:
    root = repo_root.resolve()
    out = output_dir.resolve()
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    public_url = str(os.environ.get("RELIEFQUEUE_PUBLIC_URL") or "").strip()
    plan = command_plan(fast=fast, include_public=bool(public_url))
    env = sanitized_environment()
    results: list[dict[str, Any]] = []

    for index, (name, command) in enumerate(plan, start=1):
        log_path = logs / f"{index:02d}-{name}.log"
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"COMMAND={shlex.join(command)}\n")
            log.flush()
            completed = subprocess.run(
                command,
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        duration = round(time.monotonic() - started, 3)
        results.append(
            {
                "name": name,
                "command": command,
                "exit_code": completed.returncode,
                "duration_seconds": duration,
                "log": str(log_path.relative_to(root)) if log_path.is_relative_to(root) else str(log_path),
                "status": "PASS" if completed.returncode == 0 else "FAIL",
            }
        )
        print(f"GATE_STEP={name} status={results[-1]['status']} seconds={duration}")

    failures = [item["name"] for item in results if item["exit_code"] != 0]
    report = {
        "contract": "reliefqueue-submission-final-gate/v1",
        "generated_at_utc": utc_now(),
        "status": "PASS" if not failures else "FAIL",
        "fast_mode": fast,
        "provider_calls": 0,
        "provider_credentials_removed": sorted(PROVIDER_ENV_KEYS),
        "public_url_checked": bool(public_url),
        "steps": results,
        "failures": failures,
    }
    report_path = out / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SUBMISSION_FINAL_GATE={report['status']}")
    print(f"SUBMISSION_FINAL_GATE_REPORT={report_path}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("reports/submission-final-gate/latest"))
    parser.add_argument("--fast", action="store_true", help="Skip the longest aggregate and Replit browser checks")
    args = parser.parse_args(argv)
    output = args.output_dir
    if not output.is_absolute():
        output = args.repo_root / output
    report = run_gate(args.repo_root, output, fast=args.fast)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

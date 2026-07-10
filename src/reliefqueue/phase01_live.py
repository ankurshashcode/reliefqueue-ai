"""Phase 01 live proof and cleanup orchestration."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .live_stack import SERVICES
from .phase01_host import collect_host_preflight


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def phase01_live_proof(root: Path, report_dir: Path) -> int:
    report_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "created_at": utc_now(),
        "status": "SKIP",
        "summary": "",
        "steps": [],
        "secret_values_printed": False,
        "volumes_behavior": "preserved",
        "container_summary": _container_summary(),
    }
    preflight = collect_host_preflight()
    report["host_preflight_status"] = preflight["status"]
    if preflight["status"] != "PASS":
        report["summary"] = "Docker Engine, Compose plugin, or socket access is not ready."
        report["recommended_next_command"] = preflight["recommended_next_command"]
        _write_report(report_dir / "phase01_live_proof.json", report)
        print(f"Phase 01 live proof SKIP: {report['summary']}")
        print(f"Report: {report_dir / 'phase01_live_proof.json'}")
        return 0

    overall_fail = False
    started_stack = False
    try:
        for label, command, category, timeout in [
            ("test_gate", ["make", "test"], "make_test", 180),
            ("stack_down_before", ["make", "live-stack-down"], "live_stack_down", 90),
            ("stack_up", ["make", "live-stack-up"], "live_stack_up", 150),
            ("stack_status", ["make", "live-stack-status"], "live_stack_status", 60),
        ]:
            step = _run_step(root, label, command, category, timeout)
            report["steps"].append(step)
            if label == "stack_up" and step["status"] == "PASS":
                started_stack = True
            if step["status"] != "PASS":
                overall_fail = True
                break
        if not overall_fail:
            for label, command in _protocol_commands():
                step = _run_step(root, label, command, "docker_exec_protocol", 45)
                report["steps"].append(step)
                if step["status"] != "PASS":
                    overall_fail = True
                    break
        if not overall_fail:
            step = _run_step(root, "live_stack_smoke", ["make", "live-stack-smoke"], "live_stack_smoke", 90)
            step["report_path"] = (report_dir / "live_stack_smoke.json").as_posix()
            report["steps"].append(step)
            if step["status"] != "PASS":
                overall_fail = True
    finally:
        if os.environ.get("RELIEFQUEUE_PHASE01_KEEP_STACK") == "1":
            report["cleanup"] = "skipped_keep_stack_requested"
        else:
            cleanup = _run_step(root, "cleanup_stack_down", ["make", "live-stack-down"], "live_stack_down", 90)
            cleanup["report_path"] = (report_dir / "live_stack_status.json").as_posix()
            report["steps"].append(cleanup)
            report["cleanup"] = "attempted"
            if started_stack and cleanup["status"] != "PASS":
                overall_fail = True

    report["status"] = "FAIL" if overall_fail else "PASS"
    report["summary"] = "Phase 01 live proof PASS." if report["status"] == "PASS" else "Phase 01 live proof FAIL."
    report["reports"] = [
        (report_dir / "phase01_live_proof.json").as_posix(),
        (report_dir / "live_stack_status.json").as_posix(),
        (report_dir / "live_stack_smoke.json").as_posix(),
    ]
    _write_report(report_dir / "phase01_live_proof.json", report)
    print(f"Phase 01 live proof {report['status']}: report {report_dir / 'phase01_live_proof.json'}")
    return 0 if report["status"] == "PASS" else 1


def phase01_live_clean(root: Path, report_dir: Path) -> int:
    report_dir.mkdir(parents=True, exist_ok=True)
    purge = os.environ.get("RELIEFQUEUE_LIVE_STACK_PURGE") == "1"
    step = _run_step(root, "live_stack_down", ["make", "live-stack-down"], "live_stack_down", 90)
    report = {
        "created_at": utc_now(),
        "status": step["status"],
        "summary": "Phase 01 live stack cleanup completed." if step["status"] == "PASS" else "Phase 01 live stack cleanup did not fully pass.",
        "steps": [step],
        "volumes_behavior": "purged" if purge else "preserved",
        "report_path": (report_dir / "phase01_live_clean.json").as_posix(),
        "secret_values_printed": False,
    }
    _write_report(report_dir / "phase01_live_clean.json", report)
    print(f"Phase 01 live clean {report['status']}: volumes {report['volumes_behavior']}")
    print(f"Report: {report_dir / 'phase01_live_clean.json'}")
    return 0 if step["status"] in {"PASS", "SKIP"} else 1


def _protocol_commands() -> list[tuple[str, list[str]]]:
    return [
        (
            "postgis_select",
            [
                "docker",
                "exec",
                "reliefqueue-live-postgis-1",
                "psql",
                "-U",
                "reliefqueue",
                "-d",
                "reliefqueue",
                "-c",
                "SELECT 1 AS reliefqueue_postgis_ok;",
            ],
        ),
        ("redis_ping", ["docker", "exec", "reliefqueue-live-redis-1", "redis-cli", "ping"]),
        (
            "redis_streams_xadd",
            [
                "docker",
                "exec",
                "reliefqueue-live-redis-1",
                "redis-cli",
                "XADD",
                "reliefqueue.live_stack_smoke",
                "*",
                "event",
                "synthetic",
                "source",
                "phase01_live_proof",
            ],
        ),
        (
            "nats_healthz",
            [
                "docker",
                "exec",
                "reliefqueue-live-nats-1",
                "wget",
                "-qO-",
                "http://127.0.0.1:8222/healthz",
            ],
        ),
    ]


def _run_step(root: Path, label: str, command: list[str], category: str, timeout: int) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        result = subprocess.CompletedProcess(command, 1, "", str(exc))
    status = "PASS" if result.returncode == 0 else "FAIL"
    return {
        "label": label,
        "command_category": category,
        "status": status,
        "exit_code": result.returncode,
        "detail": _sanitize(result.stdout or result.stderr or status),
        "secret_values_printed": False,
    }


def _container_summary() -> dict[str, str]:
    return {name: endpoint for name, endpoint in SERVICES.items()}


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["report_path"] = path.as_posix()
    path.write_text(json.dumps(_sanitize_obj(payload), indent=2) + "\n", encoding="utf-8")


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_obj(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_obj(item) for item in value]
    if isinstance(value, str):
        return _sanitize(value)
    return value


def _sanitize(value: str) -> str:
    value = " ".join(value.split())
    lowered = value.lower()
    if any(token in lowered for token in ["password", "passwd", "token", "secret", "api_key", "authorization"]):
        return "<redacted>"
    return value[:300]

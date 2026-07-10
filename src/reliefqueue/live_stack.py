"""Local live infrastructure stack commands.

The stack is optional for deterministic offline workflows, but live-stack
commands require Docker readiness and fail fast when the host cannot access the
Docker daemon. Podman is guidance-only for now.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .container_runtime import (
    classify_container_runtime_error,
    collect_container_runtime_readiness,
)


SERVICES = {
    "postgis": "127.0.0.1:54329",
    "redis": "127.0.0.1:63799",
    "nats": "127.0.0.1:42299",
}
VALID_STATUSES = {"PASS", "FAIL", "SKIP"}
DEFAULT_PROJECT = "reliefqueue-live"


@dataclass(frozen=True)
class ComposeCommand:
    engine: str
    command: list[str]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compose_file(root: Path) -> Path:
    return root / "ops" / "live-stack" / "compose.live.yml"


def report_path(report_dir: Path, command: str) -> Path:
    name = "live_stack_smoke.json" if command == "smoke" else "live_stack_status.json"
    return report_dir / name


def detect_compose_command(engine: str | None = None) -> ComposeCommand | None:
    """Return the supported Docker compose command when Docker readiness passes.

    Podman is intentionally not a first-class live-stack engine in the current live-stack boundary.
    The readiness report may mention Podman as guidance, but this function never
    selects Podman for live stack execution.
    """

    requested = (engine or os.environ.get("RELIEFQUEUE_LIVE_STACK_ENGINE") or os.environ.get("CONTAINER_ENGINE") or "auto").strip().lower()
    if requested not in {"auto", "docker"}:
        return None
    for command in (["docker", "compose"], ["docker-compose"]):
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(
                [*command, "version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return ComposeCommand("docker", command)
    return None


def _runtime_ready_or_report(root: Path, report_dir: Path, command: str) -> tuple[ComposeCommand | None, int | None]:
    readiness = collect_container_runtime_readiness(root, report_dir, write_report=True)
    if readiness.get("status") == "PASS":
        compose_command = [str(item) for item in readiness.get("compose_command") or []]
        if compose_command:
            return ComposeCommand("docker", compose_command), None
    payload = _base_report(command, "FAIL", "Container runtime readiness failed; live stack command was not run.")
    payload["container_runtime_readiness"] = {
        "status": readiness.get("status", "FAIL"),
        "failure_class": readiness.get("failure_class", "unknown"),
        "problem": readiness.get("problem", "unknown"),
        "report_path": readiness.get("report_path", ""),
        "operator_guidance": readiness.get("operator_guidance", []),
    }
    _add_fail_services(payload, f"container runtime not ready: {readiness.get('failure_class', 'unknown')}")
    _write_report(report_dir, payload)
    _print_report(payload)
    print("Container runtime readiness FAIL. Run: make container-runtime-readiness")
    return None, 1


def live_stack_up(root: Path, report_dir: Path) -> int:
    detected, readiness_exit = _runtime_ready_or_report(root, report_dir, "up")
    if readiness_exit is not None:
        return readiness_exit
    assert detected is not None

    compose = _compose_args(root, detected)
    result = _run_compose([*compose, "up", "-d"], timeout=120)
    if result.returncode != 0:
        detail = _sanitize(result.stderr or result.stdout)
        payload = _base_report("up", "FAIL", "Local live stack did not start.", detected)
        payload["failure_class"] = classify_container_runtime_error(detail)
        payload["services"] = _unknown_services("FAIL", detail)
        _write_report(report_dir, payload)
        _print_report(payload)
        return 1

    payload, exit_code = _wait_for_ready(root, detected)
    if payload["status"] == "PASS":
        payload["summary"] = "Local live stack started and is ready."
    else:
        payload["summary"] = "Local live stack started but did not become ready."
    _write_report(report_dir, payload)
    _print_report(payload)
    _print_ports()
    return exit_code


def live_stack_status(root: Path, report_dir: Path) -> int:
    detected, readiness_exit = _runtime_ready_or_report(root, report_dir, "status")
    if readiness_exit is not None:
        return readiness_exit
    payload, exit_code = _status_payload(root, report_dir, command="status", detected=detected)
    _write_report(report_dir, payload)
    _print_report(payload)
    if payload["status"] == "PASS":
        _print_ports()
    return exit_code


def live_stack_smoke(root: Path, report_dir: Path) -> int:
    detected, readiness_exit = _runtime_ready_or_report(root, report_dir, "smoke")
    if readiness_exit is not None:
        return readiness_exit
    status_payload, status_exit = _status_payload(root, report_dir, command="status", detected=detected)
    detected = None
    if status_payload.get("engine") in {"docker", "podman"}:
        detected = ComposeCommand(
            str(status_payload["engine"]),
            [str(item) for item in status_payload.get("compose_command") or []],
        )
    payload = _base_report("smoke", status_payload["status"], "Local live stack smoke completed.", detected)
    payload["stack_status"] = status_payload["status"]
    payload["services"] = [_smoke_service(service) for service in status_payload["services"]]
    payload["status"] = _rollup_status(payload["services"])
    if payload["status"] == "PASS":
        payload["summary"] = "Local live stack smoke PASS."
    elif payload["status"] == "SKIP":
        payload["summary"] = "Local live stack smoke SKIP: no protocol clients or stack unavailable."
    else:
        payload["summary"] = "Local live stack smoke FAIL: one or more checks failed."
    _write_report(report_dir, payload)
    _print_report(payload)
    return 1 if payload["status"] == "FAIL" or status_exit == 1 else 0


def live_stack_down(root: Path, report_dir: Path) -> int:
    purge = os.environ.get("RELIEFQUEUE_LIVE_STACK_PURGE") == "1"
    detected, readiness_exit = _runtime_ready_or_report(root, report_dir, "down")
    if readiness_exit is not None:
        print("Volumes: preserved")
        return readiness_exit
    assert detected is not None

    args = [*_compose_args(root, detected), "down"]
    if purge:
        args.append("--volumes")
    result = _run_compose(args, timeout=90)
    status = "PASS" if result.returncode == 0 else "FAIL"
    summary = "Local live stack stopped." if status == "PASS" else "Local live stack did not stop cleanly."
    payload = _base_report("down", status, summary, detected)
    payload["services"] = _unknown_services(status, "stopped" if status == "PASS" else _sanitize(result.stderr or result.stdout))
    payload["volumes"] = "purged" if purge else "preserved"
    _write_report(report_dir, payload)
    _print_report(payload)
    print(f"Volumes: {payload['volumes']}")
    return 0 if status == "PASS" else 1


def _status_payload(
    root: Path,
    report_dir: Path,
    command: str,
    detected: ComposeCommand | None = None,
) -> tuple[dict[str, Any], int]:
    del report_dir
    detected = detected or detect_compose_command()
    if detected is None:
        payload = _base_report(command, "FAIL", "Container runtime readiness failed; compose command is unavailable.")
        _add_fail_services(payload, "compose command unavailable")
        return payload, 1

    result = _run_compose([*_compose_args(root, detected), "ps", "--format", "json"], timeout=30)
    if result.returncode != 0:
        payload = _base_report(command, "SKIP", "Local stack cannot be inspected; run make live-stack-up.")
        payload.update({"engine": detected.engine, "compose_command": detected.command})
        _add_skip_services(payload, _sanitize(result.stderr or result.stdout or "compose ps unavailable"))
        return payload, 0

    services = _parse_compose_ps(result.stdout)
    service_reports = _service_reports(services)
    status = _rollup_status(service_reports)
    summary = {
        "PASS": "Local live stack services are running.",
        "FAIL": "Local live stack services are unhealthy or stopped.",
        "SKIP": "Local live stack is not running; run make live-stack-up.",
    }[status]
    payload = _base_report(command, status, summary, detected)
    payload["services"] = service_reports
    return payload, 1 if status == "FAIL" else 0


def _wait_for_ready(root: Path, detected: ComposeCommand) -> tuple[dict[str, Any], int]:
    timeout_seconds = _ready_timeout_seconds()
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    last_exit_code = 1
    while True:
        payload, exit_code = _status_payload(root, Path(), command="up", detected=detected)
        last_payload = payload
        last_exit_code = exit_code
        if payload.get("status") == "PASS":
            return payload, 0
        if payload.get("status") == "FAIL" and not _has_starting_service(payload):
            return payload, 1
        if time.monotonic() >= deadline:
            payload["status"] = "FAIL"
            payload["summary"] = "Local live stack started but services did not become healthy."
            payload["failure_class"] = "live_stack_not_ready"
            return payload, 1
        time.sleep(1)


def _has_starting_service(payload: dict[str, Any]) -> bool:
    for service in payload.get("services") or []:
        detail = str(service.get("detail") or "").lower()
        if service.get("status") == "SKIP" or "starting" in detail or "health: starting" in detail:
            return True
    return False


def _ready_timeout_seconds() -> float:
    raw = os.environ.get("RELIEFQUEUE_LIVE_STACK_READY_TIMEOUT_SECONDS", "60").strip()
    try:
        return max(1.0, min(float(raw), 300.0))
    except ValueError:
        return 60.0

def _compose_args(root: Path, detected: ComposeCommand) -> list[str]:
    project = _safe_project_name(os.environ.get("RELIEFQUEUE_LIVE_STACK_PROJECT") or DEFAULT_PROJECT)
    return [*detected.command, "-p", project, "-f", str(compose_file(root))]


def _run_compose(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr=str(exc))


def _parse_compose_ps(stdout: str) -> dict[str, dict[str, Any]]:
    text = stdout.strip()
    if not text:
        return {}
    rows: list[dict[str, Any]] = []
    try:
        parsed = json.loads(text)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        for line in text.splitlines():
            try:
                parsed_line = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed_line, dict):
                rows.append(parsed_line)
    services: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("Service") or row.get("Name") or "").lower()
        if name in SERVICES:
            services[name] = row
    return services


def _service_reports(services: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    reports: list[dict[str, str]] = []
    for name, endpoint in SERVICES.items():
        row = services.get(name)
        if row is None:
            reports.append({"name": name, "status": "SKIP", "detail": "not running", "endpoint": endpoint})
            continue
        state = str(row.get("State") or row.get("Status") or "").lower()
        health = str(row.get("Health") or "").lower()
        if "unhealthy" in state or "unhealthy" in health:
            reports.append({"name": name, "status": "FAIL", "detail": "unhealthy", "endpoint": endpoint})
        elif health == "starting" or "starting" in state:
            reports.append({"name": name, "status": "SKIP", "detail": "running (starting)", "endpoint": endpoint})
        elif health == "healthy" or (("running" in state or state == "") and not health):
            detail = "running"
            if health:
                detail = f"running ({_sanitize(health)})"
            reports.append({"name": name, "status": "PASS", "detail": detail, "endpoint": endpoint})
        elif "running" in state:
            reports.append({"name": name, "status": "SKIP", "detail": f"running ({_sanitize(health)})", "endpoint": endpoint})
        else:
            reports.append({"name": name, "status": "FAIL", "detail": _sanitize(state or "not running"), "endpoint": endpoint})
    return reports


def _smoke_service(service: dict[str, str]) -> dict[str, str]:
    name = service["name"]
    if service["status"] != "PASS":
        return {"name": name, "status": service["status"], "detail": service["detail"]}
    if name == "postgis":
        if importlib.util.find_spec("psycopg") is not None:
            return _psycopg_smoke()
        if importlib.util.find_spec("psycopg2") is not None:
            return _psycopg2_smoke()
        return {"name": name, "status": "SKIP", "detail": "Python Postgres client not installed; container readiness only."}
    if name == "redis":
        if importlib.util.find_spec("redis") is not None:
            return _redis_smoke()
        return {"name": name, "status": "SKIP", "detail": "Python Redis client not installed; container readiness only."}
    if name == "nats":
        if importlib.util.find_spec("nats") is not None:
            return {"name": name, "status": "SKIP", "detail": "NATS async client present; protocol smoke deferred to later phase."}
        return {"name": name, "status": "SKIP", "detail": "Python NATS client not installed; container readiness only."}
    return {"name": name, "status": "SKIP", "detail": "unknown service"}


def _psycopg_smoke() -> dict[str, str]:
    dsn = os.environ.get("RELIEFQUEUE_POSTGIS_DSN") or "postgresql://reliefqueue:reliefqueue@127.0.0.1:54329/reliefqueue"
    try:
        import psycopg  # type: ignore[import-not-found]

        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"name": "postgis", "status": "PASS", "detail": "Postgres client SELECT 1 passed."}
    except Exception as exc:  # pragma: no cover - depends on optional local service/client
        return {"name": "postgis", "status": "FAIL", "detail": _sanitize(str(exc))}


def _psycopg2_smoke() -> dict[str, str]:
    dsn = os.environ.get("RELIEFQUEUE_POSTGIS_DSN") or "postgresql://reliefqueue:reliefqueue@127.0.0.1:54329/reliefqueue"
    try:
        import psycopg2  # type: ignore[import-not-found]

        conn = psycopg2.connect(dsn, connect_timeout=3)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            conn.close()
        return {"name": "postgis", "status": "PASS", "detail": "Postgres client SELECT 1 passed."}
    except Exception as exc:  # pragma: no cover - depends on optional local service/client
        return {"name": "postgis", "status": "FAIL", "detail": _sanitize(str(exc))}


def _redis_smoke() -> dict[str, str]:
    url = os.environ.get("RELIEFQUEUE_REDIS_URL") or "redis://127.0.0.1:63799/0"
    try:
        import redis  # type: ignore[import-not-found]

        client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        client.ping()
        client.xadd("reliefqueue.live_stack_smoke", {"event": "synthetic"})
        return {"name": "redis", "status": "PASS", "detail": "Redis ping and synthetic stream write passed."}
    except Exception as exc:  # pragma: no cover - depends on optional local service/client
        return {"name": "redis", "status": "FAIL", "detail": _sanitize(str(exc))}


def _rollup_status(services: list[dict[str, str]]) -> str:
    statuses = [service["status"] for service in services]
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if statuses and all(status == "PASS" for status in statuses):
        return "PASS"
    return "SKIP"


def _base_report(
    command: str,
    status: str,
    summary: str,
    detected: ComposeCommand | None = None,
) -> dict[str, Any]:
    return {
        "created_at": utc_now(),
        "command": command,
        "status": status if status in VALID_STATUSES else "FAIL",
        "summary": summary,
        "engine": detected.engine if detected else "unknown",
        "compose_command": detected.command if detected else [],
        "services": [],
        "secret_values_printed": False,
    }


def _add_skip_services(payload: dict[str, Any], detail: str) -> None:
    payload["services"] = _unknown_services("SKIP", detail)


def _add_fail_services(payload: dict[str, Any], detail: str) -> None:
    payload["services"] = _unknown_services("FAIL", detail)


def _unknown_services(status: str, detail: str) -> list[dict[str, str]]:
    return [
        {"name": name, "status": status, "detail": _sanitize(detail), "endpoint": endpoint}
        for name, endpoint in SERVICES.items()
    ]


def _write_report(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_path(report_dir, str(payload["command"]))
    payload["report_path"] = path.as_posix()
    path.write_text(json.dumps(_sanitize_obj(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _print_report(payload: dict[str, Any]) -> None:
    print(f"Live stack {payload['command']} {payload['status']}: {payload['summary']}")
    print(f"Engine: {payload.get('engine') or 'unknown'}")
    for service in payload.get("services") or []:
        print(f"- {service['name']}: {service['status']} ({service['detail']})")
    if payload.get("report_path"):
        print(f"Report: {payload['report_path']}")


def _print_ports() -> None:
    print("Local service ports:")
    for name, endpoint in SERVICES.items():
        print(f"- {name}: {endpoint}")


def _safe_project_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", value.strip())
    return safe or DEFAULT_PROJECT


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_obj(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_obj(item) for item in value]
    if isinstance(value, str):
        return _sanitize(value)
    return value


def _sanitize(value: str) -> str:
    sanitized = re.sub(r"(?i)(password|passwd|token|secret|api[_-]?key)([\s:=]+)([^\s,;]+)", r"\1\2<redacted>", value)
    sanitized = re.sub(r"(?i)(postgres(?:ql)?://[^:\s/@]+):([^@\s]+)@", r"\1:<redacted>@", sanitized)
    sanitized = re.sub(r"\b(?:sk|fw|fireworks)-[A-Za-z0-9_\-]{12,}\b", "<redacted-api-key>", sanitized)
    sanitized = re.sub(r"\+?\d[\d\s().-]{8,}\d", "<redacted-phone>", sanitized)
    return " ".join(sanitized.split())[:300]

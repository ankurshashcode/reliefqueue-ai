"""Read-only container runtime readiness checks for local live integrations.

This module intentionally does not repair host permissions. Docker daemon access is
host-level security state; ReliefQueue only detects it, writes clear evidence, and
prints safe operator guidance.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALID_STATUSES = {"PASS", "FAIL", "SKIP"}
SUPPORTED_ENGINE = "docker"
REPORT_NAME = "container_runtime_readiness.json"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def container_runtime_report_path(report_dir: Path) -> Path:
    return report_dir / REPORT_NAME


def collect_container_runtime_readiness(root: Path, report_dir: Path, *, write_report: bool = True) -> dict[str, Any]:
    """Collect a sanitized, read-only report about local container runtime access."""

    del root
    requested = _requested_engine()
    docker_path = shutil.which("docker")
    podman_path = shutil.which("podman")
    docker_compose_path = shutil.which("docker-compose")
    socket_path = _docker_socket_path()
    report: dict[str, Any] = {
        "created_at": utc_now(),
        "status": "FAIL",
        "summary": "Container runtime readiness failed.",
        "supported_engine": SUPPORTED_ENGINE,
        "requested_engine": requested,
        "engine": "unknown",
        "compose_command": [],
        "docker": {
            "path": docker_path or "",
            "version": "",
            "info_status": "not_checked",
            "rootless": False,
            "docker_host_configured": bool(os.environ.get("DOCKER_HOST")),
            "docker_context_configured": bool(os.environ.get("DOCKER_CONTEXT")),
        },
        "docker_compose_plugin": {"available": False, "version": ""},
        "legacy_docker_compose": {"path": docker_compose_path or "", "available": False, "version": ""},
        "podman": {
            "path": podman_path or "",
            "detected": bool(podman_path),
            "guidance_only": True,
            "first_class_supported": False,
        },
        "docker_socket": _socket_status(socket_path),
        "failure_class": "unknown",
        "problem": "unknown",
        "operator_guidance": [],
        "host_changes_attempted": False,
        "secret_values_printed": False,
    }

    if requested not in {"auto", SUPPORTED_ENGINE}:
        report.update(
            {
                "status": "FAIL",
                "summary": "Unsupported container engine requested.",
                "failure_class": "unsupported_engine",
                "problem": (
                    f"Requested engine {requested!r} is not supported for ReliefQueue live stack. "
                    "Docker is the only first-class live engine in the current live-stack boundary."
                ),
            }
        )
        _attach_guidance(report)
        return _finish_report(report_dir, report, write_report)

    if not docker_path:
        report.update(
            {
                "status": "FAIL",
                "summary": "Docker CLI is missing.",
                "failure_class": "docker_cli_missing",
                "problem": "The docker command was not found on PATH.",
            }
        )
        _attach_guidance(report)
        return _finish_report(report_dir, report, write_report)

    docker_version = _run(["docker", "--version"], timeout=8)
    report["docker"]["version"] = _sanitize(docker_version.stdout or docker_version.stderr)
    if docker_version.returncode != 0:
        report.update(
            {
                "status": "FAIL",
                "summary": "Docker CLI did not run successfully.",
                "failure_class": "docker_cli_failed",
                "problem": _sanitize(docker_version.stderr or docker_version.stdout or "docker --version failed"),
            }
        )
        _attach_guidance(report)
        return _finish_report(report_dir, report, write_report)

    info = _run(["docker", "info"], timeout=15)
    info_text = _sanitize((info.stdout or "") + "\n" + (info.stderr or ""))
    report["docker"]["info_status"] = "PASS" if info.returncode == 0 else "FAIL"
    report["docker"]["rootless"] = "rootless" in info_text.lower()
    if info.returncode != 0:
        failure_class = classify_container_runtime_error(info_text)
        report.update(
            {
                "status": "FAIL",
                "summary": "Docker daemon is not accessible.",
                "failure_class": failure_class,
                "problem": info_text or "docker info failed",
            }
        )
        _attach_guidance(report)
        return _finish_report(report_dir, report, write_report)

    compose = _detect_docker_compose()
    if compose is None:
        report.update(
            {
                "status": "FAIL",
                "summary": "Docker is accessible but Docker Compose is unavailable.",
                "failure_class": "docker_compose_missing",
                "problem": "Neither `docker compose version` nor `docker-compose version` succeeded.",
            }
        )
        _attach_guidance(report)
        return _finish_report(report_dir, report, write_report)

    report["engine"] = "docker"
    report["compose_command"] = compose["command"]
    if compose["command"] == ["docker", "compose"]:
        report["docker_compose_plugin"] = {"available": True, "version": compose["version"]}
    else:
        report["legacy_docker_compose"] = {"path": docker_compose_path or "", "available": True, "version": compose["version"]}
    report.update(
        {
            "status": "PASS",
            "summary": "Docker runtime and compose command are accessible.",
            "failure_class": "none",
            "problem": "none",
        }
    )
    _attach_guidance(report)
    return _finish_report(report_dir, report, write_report)


def container_runtime_readiness(root: Path, report_dir: Path) -> int:
    report = collect_container_runtime_readiness(root, report_dir, write_report=True)
    _print_readiness(report)
    return 0 if report.get("status") == "PASS" else 1


def classify_container_runtime_error(text: str) -> str:
    lower = text.lower()
    if "permission denied" in lower and "docker.sock" in lower:
        return "docker_socket_permission_denied"
    if "permission denied" in lower:
        return "docker_permission_denied"
    if "cannot connect to the docker daemon" in lower or "is the docker daemon running" in lower:
        return "docker_daemon_unreachable"
    if "no such file" in lower and "docker.sock" in lower:
        return "docker_socket_missing"
    if "context" in lower and ("not found" in lower or "does not exist" in lower):
        return "docker_context_invalid"
    return "docker_daemon_unavailable"


def _requested_engine() -> str:
    primary = os.environ.get("RELIEFQUEUE_LIVE_STACK_ENGINE", "").strip().lower()
    secondary = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
    value = primary or secondary or "auto"
    return value or "auto"


def _detect_docker_compose() -> dict[str, Any] | None:
    plugin = _run(["docker", "compose", "version"], timeout=8)
    if plugin.returncode == 0:
        return {"command": ["docker", "compose"], "version": _sanitize(plugin.stdout or plugin.stderr)}
    if shutil.which("docker-compose"):
        legacy = _run(["docker-compose", "version"], timeout=8)
        if legacy.returncode == 0:
            return {"command": ["docker-compose"], "version": _sanitize(legacy.stdout or legacy.stderr)}
    return None


def _docker_socket_path() -> Path:
    host = os.environ.get("DOCKER_HOST", "").strip()
    if host.startswith("unix://"):
        return Path(host.removeprefix("unix://"))
    return Path("/var/run/docker.sock")


def _socket_status(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "readable": False,
        "writable": False,
        "is_socket": False,
        "mode": "",
        "uid": None,
        "gid": None,
    }
    if not path.exists():
        return payload
    try:
        st = path.stat()
        payload.update(
            {
                "readable": os.access(path, os.R_OK),
                "writable": os.access(path, os.W_OK),
                "is_socket": stat.S_ISSOCK(st.st_mode),
                "mode": oct(stat.S_IMODE(st.st_mode)),
                "uid": st.st_uid,
                "gid": st.st_gid,
            }
        )
    except OSError as exc:
        payload["stat_error"] = _sanitize(str(exc))
    return payload


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def _attach_guidance(report: dict[str, Any]) -> None:
    guidance = [
        "ReliefQueue does not run sudo, modify groups, chmod /var/run/docker.sock, or repair host Docker automatically.",
        "Preferred fix: use a working Docker Engine context where this user can run `docker info` successfully.",
        "Linux option: add the user to the docker group, then log out/in or run a new shell with that group active; treat this as root-equivalent access.",
        "Safer Linux option: configure Docker rootless mode if it fits the host and live-stack requirements.",
        "Remote option: set DOCKER_HOST or Docker context to a daemon the current user may access.",
    ]
    if report.get("podman", {}).get("detected"):
        guidance.append(
            "Podman is detected, but it is guidance-only for the current live-stack boundary; do not expect ReliefQueue live stack to use Podman yet."
        )
    else:
        guidance.append(
            "Podman may be considered later, but it is not first-class supported for this live stack patch."
        )
    failure_class = str(report.get("failure_class") or "")
    if failure_class == "docker_cli_missing":
        guidance.append("Install Docker Engine and the Docker Compose plugin, then rerun `make container-runtime-readiness`.")
    elif failure_class in {"docker_socket_permission_denied", "docker_permission_denied"}:
        guidance.append("After changing Docker group/rootless access, rerun `docker info` before rerunning live-stack commands.")
    elif failure_class == "docker_daemon_unreachable":
        guidance.append("Start Docker daemon/Desktop or select a valid Docker context, then rerun the readiness command.")
    elif failure_class == "docker_compose_missing":
        guidance.append("Install the Docker Compose plugin or make a compatible `docker-compose` command available.")
    elif failure_class == "unsupported_engine":
        guidance.append("Unset CONTAINER_ENGINE/RELIEFQUEUE_LIVE_STACK_ENGINE or set it to docker.")
    report["operator_guidance"] = guidance


def _finish_report(report_dir: Path, report: dict[str, Any], write_report: bool) -> dict[str, Any]:
    sanitized = _sanitize_obj(report)
    if write_report:
        report_dir.mkdir(parents=True, exist_ok=True)
        path = container_runtime_report_path(report_dir)
        sanitized["report_path"] = path.as_posix()
        path.write_text(json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sanitized


def _print_readiness(report: dict[str, Any]) -> None:
    status = str(report.get("status", "FAIL"))
    print(f"container-runtime-readiness {status}")
    print(f"Engine: {report.get('engine', 'unknown')}")
    if report.get("compose_command"):
        print(f"Compose command: {' '.join(str(item) for item in report['compose_command'])}")
    print(f"Summary: {report.get('summary', '')}")
    if status != "PASS":
        print(f"Failure class: {report.get('failure_class', 'unknown')}")
        problem = str(report.get("problem", "")).strip()
        if problem and problem != "none":
            print(f"Problem: {problem}")
        print("Guidance:")
        for item in report.get("operator_guidance", []):
            print(f"- {item}")
    if report.get("report_path"):
        print(f"Report: {report['report_path']}")


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize(value)
    if isinstance(value, list):
        return [_sanitize_obj(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_obj(item) for key, item in value.items()}
    return value


def _sanitize(value: str) -> str:
    redacted = str(value)
    for env_key in [
        "DOCKER_HOST",
        "OPENAI_COMPAT_API_KEY",
        "TWILIO_AUTH_TOKEN",
        "WHATSAPP_ACCESS_TOKEN",
        "RAPIDPRO_API_TOKEN",
        "ODK_CENTRAL_PASSWORD",
    ]:
        secret_value = os.environ.get(env_key, "")
        if secret_value and ("@" in secret_value or "token" in env_key.lower() or "key" in env_key.lower() or "password" in env_key.lower()):
            redacted = redacted.replace(secret_value, "<redacted>")
    redacted = re.sub(r"(//[^:/\s]+:)[^@/\s]+(@)", r"\1<redacted>\2", redacted)
    redacted = re.sub(r"(password|passwd|token|secret|api[_-]?key)=([^\s]+)", r"\1=<redacted>", redacted, flags=re.IGNORECASE)
    return redacted.strip()

"""Phase 01 host preflight and guided Docker setup."""

from __future__ import annotations

import getpass
import grp
import json
import os
import platform
import pwd
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def phase01_host_preflight(root: Path, report_dir: Path) -> int:
    del root
    report = collect_host_preflight()
    _write_report(report_dir / "phase01_host_preflight.json", report)
    _print_preflight(report)
    return 0 if report["status"] == "PASS" else 1


def phase01_host_setup(root: Path, report_dir: Path) -> int:
    del root
    report_dir.mkdir(parents=True, exist_ok=True)
    preflight = collect_host_preflight()
    _write_report(report_dir / "phase01_host_preflight.json", preflight)
    setup: dict[str, Any] = {
        "created_at": utc_now(),
        "status": "SKIP",
        "preflight_status": preflight["status"],
        "host_changes_attempted": False,
        "confirmation_required": True,
        "confirmation_source": "none",
        "planned_changes": [],
        "commands_run": [],
        "notes": [],
        "secret_values_printed": False,
    }
    if preflight["status"] == "PASS":
        setup["status"] = "PASS"
        setup["notes"].append("Preflight already passes. No host changes needed.")
        _write_report(report_dir / "phase01_host_setup.json", setup)
        print("Phase 01 host setup PASS: no host changes needed.")
        return 0
    if not _is_debian_like(preflight):
        setup["status"] = "SKIP"
        setup["notes"].append("Guided setup supports Ubuntu/Debian-compatible hosts first.")
        _write_report(report_dir / "phase01_host_setup.json", setup)
        print("Phase 01 host setup SKIP: unsupported OS for guided setup.")
        return 0

    planned = [
        "remove conflicting docker/podman packages if present",
        "install Docker official apt keyring and repository",
        "install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        "enable and start docker service when systemd is available",
        "add current user to docker group when needed",
    ]
    setup["planned_changes"] = planned
    print("Phase 01 host setup planned changes:")
    for item in planned:
        print(f"- {item}")
    confirmation = os.environ.get("RELIEFQUEUE_HOST_SETUP_CONFIRM")
    if confirmation == "YES":
        setup["confirmation_source"] = "RELIEFQUEUE_HOST_SETUP_CONFIRM"
    else:
        typed = input("Type YES to apply these host changes: ").strip()
        if typed == "YES":
            setup["confirmation_source"] = "interactive"
        else:
            setup["status"] = "SKIP"
            setup["notes"].append("Operator did not type YES. No host changes were made.")
            _write_report(report_dir / "phase01_host_setup.json", setup)
            print("Phase 01 host setup SKIP: confirmation not provided.")
            return 0

    setup["host_changes_attempted"] = True
    commands = _docker_install_commands()
    failures: list[str] = []
    for label, command in commands:
        result = _run(command, timeout=240)
        setup["commands_run"].append(
            {"label": label, "status": "PASS" if result.returncode == 0 else "FAIL", "exit_code": result.returncode}
        )
        if result.returncode != 0:
            failures.append(label)
            break
    setup["status"] = "FAIL" if failures else "PASS"
    if failures:
        setup["notes"].append("Host setup stopped after failed command: " + failures[0])
    else:
        setup["notes"].append("Docker setup commands completed. A new login or newgrp docker may be required.")
    _write_report(report_dir / "phase01_host_setup.json", setup)
    print(f"Phase 01 host setup {setup['status']}: report {report_dir / 'phase01_host_setup.json'}")
    return 0 if setup["status"] == "PASS" else 1


def collect_host_preflight() -> dict[str, Any]:
    os_release = _os_release()
    docker_path = shutil.which("docker")
    docker_version = _run_text(["docker", "--version"]) if docker_path else ""
    compose = _run_text(["docker", "compose", "version"]) if docker_path else ""
    legacy_path = shutil.which("docker-compose")
    legacy = _run_text(["docker-compose", "--version"]) if legacy_path else ""
    podman_path = shutil.which("podman")
    podman = _run_text(["podman", "--version"]) if podman_path else ""
    docker_info = _run_text(["docker", "info"]) if docker_path else ""
    groups = _current_groups()
    podman_shim = "podman" in docker_version.lower() or "podman" in docker_info.lower()
    socket_status = "not_checked"
    if docker_path and not podman_shim:
        socket_status = "usable" if docker_info else "unusable"
    notes: list[str] = []
    status = "PASS"
    recommended = "make phase01-live-proof"
    if not _is_linux_debian_or_ubuntu(os_release):
        status = "SKIP"
        notes.append("Guided Phase 01 host setup supports Ubuntu/Debian-compatible Linux first.")
        recommended = "Use an Ubuntu/Debian Docker host, then run make phase01-host-preflight."
    if docker_path is None:
        status = "FAIL" if status != "SKIP" else status
        notes.append("Docker command is missing.")
        recommended = "make phase01-host-setup"
    if podman_shim:
        status = "FAIL"
        notes.append("docker appears to be routed to Podman compatibility. Podman is unsupported for the current live-stack boundary.")
        recommended = "Install official Docker Engine and Compose plugin."
    if docker_path and not compose:
        status = "FAIL"
        notes.append("Docker Compose plugin is missing or unusable.")
        recommended = "make phase01-host-setup"
    if legacy and not compose:
        status = "FAIL"
        notes.append("Legacy docker-compose v1 cannot be the active provider for the current live-stack boundary.")
        recommended = "Install Docker Compose plugin with official Docker Engine."
    if docker_path and compose and socket_status != "usable" and not podman_shim:
        status = "FAIL"
        notes.append('Docker socket is not usable by the current user. Recommended: sudo usermod -aG docker "$USER", then new login or newgrp docker.')
        recommended = 'Fix Docker socket access, then run make phase01-host-preflight.'
    return {
        "created_at": utc_now(),
        "status": status,
        "os_release": _safe_os_summary(os_release),
        "kernel": platform.release(),
        "current_user": getpass.getuser(),
        "groups": groups,
        "docker": {"path": docker_path or "", "version": _sanitize(docker_version)},
        "docker_compose_plugin": {"available": bool(compose), "version": _sanitize(compose)},
        "legacy_docker_compose": {"path": legacy_path or "", "version": _sanitize(legacy)},
        "podman": {"path": podman_path or "", "version": _sanitize(podman)},
        "docker_appears_podman_shim": podman_shim,
        "docker_socket_access": socket_status,
        "unsupported_or_conflicting_runtime_notes": notes,
        "recommended_next_command": recommended,
        "secret_values_printed": False,
    }


def _docker_install_commands() -> list[tuple[str, list[str]]]:
    user = getpass.getuser()
    commands = [
        ("apt_update", ["sudo", "apt-get", "update"]),
        (
            "remove_conflicts",
            [
                "sudo",
                "apt-get",
                "remove",
                "-y",
                "docker.io",
                "docker-doc",
                "docker-compose",
                "podman-docker",
                "containerd",
                "runc",
            ],
        ),
        (
            "install_prereqs",
            ["sudo", "apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"],
        ),
        ("install_keyring_dir", ["sudo", "install", "-m", "0755", "-d", "/etc/apt/keyrings"]),
        (
            "install_docker_key",
            [
                "bash",
                "-lc",
                "curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo \"$ID\")/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
            ],
        ),
        ("chmod_docker_key", ["sudo", "chmod", "a+r", "/etc/apt/keyrings/docker.gpg"]),
        (
            "install_docker_repo",
            [
                "bash",
                "-lc",
                "echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo \"$ID\") $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable\" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null",
            ],
        ),
        ("apt_update_docker", ["sudo", "apt-get", "update"]),
        (
            "install_docker_engine",
            [
                "sudo",
                "apt-get",
                "install",
                "-y",
                "docker-ce",
                "docker-ce-cli",
                "containerd.io",
                "docker-buildx-plugin",
                "docker-compose-plugin",
            ],
        ),
    ]
    if Path("/run/systemd/system").exists():
        commands.append(("enable_start_docker", ["sudo", "systemctl", "enable", "--now", "docker"]))
    commands.append(("add_user_to_docker_group", ["sudo", "usermod", "-aG", "docker", user]))
    return commands


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def _run_text(command: list[str]) -> str:
    result = _run(command, timeout=10)
    if result.returncode != 0:
        return ""
    return _sanitize((result.stdout or result.stderr).strip())


def _current_groups() -> list[str]:
    try:
        user = pwd.getpwnam(getpass.getuser())
        return sorted(group.gr_name for group in grp.getgrall() if user.pw_name in group.gr_mem or group.gr_gid == user.pw_gid)
    except Exception:
        return []


def _os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def _safe_os_summary(data: dict[str, str]) -> dict[str, str]:
    return {key: data.get(key, "") for key in ["ID", "VERSION_ID", "VERSION_CODENAME", "PRETTY_NAME", "ID_LIKE"] if data.get(key)}


def _is_linux_debian_or_ubuntu(data: dict[str, str]) -> bool:
    if platform.system().lower() != "linux":
        return False
    joined = " ".join([data.get("ID", ""), data.get("ID_LIKE", "")]).lower()
    return "debian" in joined or "ubuntu" in joined


def _is_debian_like(preflight: dict[str, Any]) -> bool:
    summary = preflight.get("os_release") or {}
    joined = " ".join([summary.get("ID", ""), summary.get("ID_LIKE", "")]).lower()
    return "debian" in joined or "ubuntu" in joined


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["report_path"] = path.as_posix()
    path.write_text(json.dumps(_sanitize_obj(payload), indent=2) + "\n", encoding="utf-8")


def _print_preflight(report: dict[str, Any]) -> None:
    print(f"Phase 01 host preflight {report['status']}: {report['recommended_next_command']}")
    print(f"Docker: {report['docker']['version'] or 'missing'}")
    print(f"Compose plugin: {report['docker_compose_plugin']['version'] or 'missing'}")
    print(f"Docker socket: {report['docker_socket_access']}")
    for note in report["unsupported_or_conflicting_runtime_notes"]:
        print(f"- {note}")
    print(f"Report: {report['report_path']}")


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
    forbidden = ["password", "passwd", "token", "secret", "api_key", "apikey", "authorization"]
    lowered = value.lower()
    if any(item in lowered for item in forbidden):
        return "<redacted>"
    return value[:300]

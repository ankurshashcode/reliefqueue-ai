import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reliefqueue.container_runtime import (
    collect_container_runtime_readiness,
    container_runtime_readiness,
)
from reliefqueue.live_stack import detect_compose_command, live_stack_up


class ContainerRuntimeReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.report_dir = self.root / "reports" / "latest"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_permission_denied_writes_actionable_report_without_host_changes(self) -> None:
        def fake_run(command, check=False, capture_output=True, text=True, timeout=10):
            del check, capture_output, text, timeout
            if command == ["docker", "--version"]:
                return subprocess.CompletedProcess(command, 0, "Docker version 27.0.0\n", "")
            if command == ["docker", "info"]:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    "permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock",
                )
            return subprocess.CompletedProcess(command, 1, "", "unexpected")

        with (
            patch("reliefqueue.container_runtime.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "docker" else None),
            patch("reliefqueue.container_runtime.subprocess.run", side_effect=fake_run),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(container_runtime_readiness(self.root, self.report_dir), 1)

        report = json.loads((self.report_dir / "container_runtime_readiness.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failure_class"], "docker_socket_permission_denied")
        self.assertFalse(report["host_changes_attempted"])
        rendered = out.getvalue()
        self.assertIn("container-runtime-readiness FAIL", rendered)
        self.assertIn("does not run sudo", json.dumps(report))

    def test_docker_compose_plugin_passes(self) -> None:
        def fake_run(command, check=False, capture_output=True, text=True, timeout=10):
            del check, capture_output, text, timeout
            if command == ["docker", "--version"]:
                return subprocess.CompletedProcess(command, 0, "Docker version 27.0.0\n", "")
            if command == ["docker", "info"]:
                return subprocess.CompletedProcess(command, 0, "Server Version: 27.0.0\n", "")
            if command == ["docker", "compose", "version"]:
                return subprocess.CompletedProcess(command, 0, "Docker Compose version v2.29.0\n", "")
            return subprocess.CompletedProcess(command, 1, "", "unexpected")

        with (
            patch("reliefqueue.container_runtime.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "docker" else None),
            patch("reliefqueue.container_runtime.subprocess.run", side_effect=fake_run),
        ):
            report = collect_container_runtime_readiness(self.root, self.report_dir)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["engine"], "docker")
        self.assertEqual(report["compose_command"], ["docker", "compose"])

    def test_podman_requested_is_guidance_only_not_first_class(self) -> None:
        with (
            patch.dict("os.environ", {"CONTAINER_ENGINE": "podman"}, clear=True),
            patch("reliefqueue.container_runtime.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name in {"docker", "podman"} else None),
        ):
            report = collect_container_runtime_readiness(self.root, self.report_dir)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failure_class"], "unsupported_engine")
        self.assertTrue(report["podman"]["guidance_only"])
        self.assertFalse(report["podman"]["first_class_supported"])

    def test_live_stack_up_fails_before_compose_when_readiness_fails(self) -> None:
        readiness = {
            "status": "FAIL",
            "failure_class": "docker_socket_permission_denied",
            "problem": "permission denied",
            "operator_guidance": ["fix docker access"],
            "report_path": "reports/latest/container_runtime_readiness.json",
        }
        with patch("reliefqueue.live_stack.collect_container_runtime_readiness", return_value=readiness):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(live_stack_up(self.root, self.report_dir), 1)
        rendered = out.getvalue()
        self.assertIn("Live stack up FAIL", rendered)
        self.assertIn("docker_socket_permission_denied", rendered)
        report = json.loads((self.report_dir / "live_stack_status.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["container_runtime_readiness"]["failure_class"], "docker_socket_permission_denied")
        self.assertTrue(all(service["status"] == "FAIL" for service in report["services"]))

    def test_detect_compose_command_does_not_select_podman(self) -> None:
        with (
            patch.dict("os.environ", {"RELIEFQUEUE_LIVE_STACK_ENGINE": "podman"}, clear=True),
            patch("reliefqueue.live_stack.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name in {"docker", "podman"} else None),
            patch("reliefqueue.live_stack.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ok", "")),
        ):
            self.assertIsNone(detect_compose_command())


if __name__ == "__main__":
    unittest.main()

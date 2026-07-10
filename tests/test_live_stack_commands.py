import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reliefqueue.live_stack import (
    detect_compose_command,
    live_stack_down,
    live_stack_status,
)


ROOT = Path(__file__).resolve().parents[1]


class LiveStackCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "ops", self.root / "ops")
        self.report_dir = self.root / "reports" / "latest"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_runtime_fails_status_without_cascade(self) -> None:
        readiness = {
            "status": "FAIL",
            "failure_class": "docker_cli_missing",
            "problem": "docker missing",
            "operator_guidance": ["install docker"],
            "report_path": "reports/latest/container_runtime_readiness.json",
        }
        with patch("reliefqueue.live_stack.collect_container_runtime_readiness", return_value=readiness):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(live_stack_status(self.root, self.report_dir), 1)
        self.assertIn("FAIL", out.getvalue())
        report = json.loads((self.report_dir / "live_stack_status.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(all(service["status"] == "FAIL" for service in report["services"]))

    def test_status_json_contains_service_status_fields(self) -> None:
        ps = json.dumps(
            [
                {"Service": "postgis", "State": "running", "Health": "healthy"},
                {"Service": "redis", "State": "running", "Health": "healthy"},
                {"Service": "nats", "State": "running", "Health": "healthy"},
            ]
        )
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=ps, stderr="")
        readiness = {"status": "PASS", "compose_command": ["docker", "compose"]}
        with (
            patch("reliefqueue.live_stack.collect_container_runtime_readiness", return_value=readiness),
            patch("reliefqueue.live_stack.subprocess.run") as run,
        ):
            run.side_effect = [completed]
            self.assertEqual(live_stack_status(self.root, self.report_dir), 0)
        report = json.loads((self.report_dir / "live_stack_status.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual({service["status"] for service in report["services"]}, {"PASS"})
        self.assertIn(report["status"], {"PASS", "FAIL", "SKIP"})

    def test_command_output_and_report_redact_obvious_secrets(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="password=super" + "SecretValue123456789 token=abc" + "123def4567890",
        )
        readiness = {"status": "PASS", "compose_command": ["docker", "compose"]}
        with (
            patch("reliefqueue.live_stack.collect_container_runtime_readiness", return_value=readiness),
            patch("reliefqueue.live_stack.subprocess.run") as run,
        ):
            run.side_effect = [completed]
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(live_stack_status(self.root, self.report_dir), 0)
        rendered = out.getvalue() + (self.report_dir / "live_stack_status.json").read_text(encoding="utf-8")
        self.assertNotIn("super" + "SecretValue123456789", rendered)
        self.assertNotIn("abc" + "123def4567890", rendered)
        self.assertIn("<redacted>", rendered)


    def test_live_stack_up_waits_until_services_are_healthy(self) -> None:
        starting = json.dumps(
            [
                {"Service": "postgis", "State": "running", "Health": "starting"},
                {"Service": "redis", "State": "running", "Health": "starting"},
                {"Service": "nats", "State": "running", "Health": "starting"},
            ]
        )
        healthy = json.dumps(
            [
                {"Service": "postgis", "State": "running", "Health": "healthy"},
                {"Service": "redis", "State": "running", "Health": "healthy"},
                {"Service": "nats", "State": "running", "Health": "healthy"},
            ]
        )
        readiness = {"status": "PASS", "compose_command": ["docker", "compose"]}
        with (
            patch.dict("os.environ", {"RELIEFQUEUE_LIVE_STACK_READY_TIMEOUT_SECONDS": "2"}, clear=True),
            patch("reliefqueue.live_stack.collect_container_runtime_readiness", return_value=readiness),
            patch("reliefqueue.live_stack.time.sleep", return_value=None),
            patch("reliefqueue.live_stack.subprocess.run") as run,
        ):
            run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout=starting, stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout=healthy, stderr=""),
            ]
            from reliefqueue.live_stack import live_stack_up

            self.assertEqual(live_stack_up(self.root, self.report_dir), 0)
        report = json.loads((self.report_dir / "live_stack_status.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual({service["status"] for service in report["services"]}, {"PASS"})

    def test_down_preserves_volumes_by_default(self) -> None:
        readiness = {"status": "PASS", "compose_command": ["docker", "compose"]}
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("reliefqueue.live_stack.collect_container_runtime_readiness", return_value=readiness),
            patch("reliefqueue.live_stack.subprocess.run") as run,
        ):
            run.side_effect = [subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")]
            self.assertEqual(live_stack_down(self.root, self.report_dir), 0)
        down_call = run.call_args_list[-1].args[0]
        self.assertNotIn("--volumes", down_call)
        report = json.loads((self.report_dir / "live_stack_status.json").read_text(encoding="utf-8"))
        self.assertEqual(report["volumes"], "preserved")

    def test_compose_detection_respects_engine_preference(self) -> None:
        def fake_which(binary: str) -> str | None:
            return f"/usr/bin/{binary}" if binary in {"docker", "podman"} else None

        with (
            patch("reliefqueue.live_stack.shutil.which", side_effect=fake_which),
            patch(
                "reliefqueue.live_stack.subprocess.run",
                return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ) as run,
        ):
            self.assertEqual(detect_compose_command("docker").command, ["docker", "compose"])
            self.assertIsNone(detect_compose_command("podman"))
            self.assertEqual(run.call_args_list[0].args[0][:2], ["docker", "compose"])

    def test_makefile_targets_exist(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ["container-runtime-readiness", "live-stack-up", "live-stack-status", "live-stack-smoke", "live-stack-down"]:
            self.assertIn(f"{target}:", makefile)


if __name__ == "__main__":
    unittest.main()

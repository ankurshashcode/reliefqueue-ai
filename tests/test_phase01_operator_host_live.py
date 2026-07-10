import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reliefqueue.operator_catalog import actions, catalog_check, render_scope, search_actions
from reliefqueue.phase01_host import collect_host_preflight, phase01_host_setup
from reliefqueue.phase01_live import phase01_live_proof


ROOT = Path(__file__).resolve().parents[1]


class Phase01OperatorCatalogTests(unittest.TestCase):
    def test_action_ids_are_unique(self) -> None:
        ids = [action.id for action in actions()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_catalog_commands_reference_make_targets(self) -> None:
        exit_code, errors = catalog_check(ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(exit_code, 0)

    def test_operator_search_finds_phase01_actions_for_natural_queries(self) -> None:
        queries = {
            "test live integration": "phase01_live_proof",
            "PostGIS Redis NATS": "phase01_live_stack",
            "docker installed but live stack not working": "phase01_host_preflight",
            "what changes will phase01 live proof make": "phase01_live_proof",
            "clean up live stack": "phase01_live_clean",
            "privacy check": "privacy_security_check",
            "dashboard smoke": "dashboard_check",
            "stateful mutation drill": "phase02_03_stateful_mutation_drill",
            "logistics asset drill": "phase02_04_logistics_asset_drill",
        }
        for query, expected in queries.items():
            with self.subTest(query=query):
                matches = [action.id for _score, action in search_actions(query)]
                self.assertIn(expected, matches)

    def test_operator_scope_prints_required_sections(self) -> None:
        exit_code, rendered = render_scope("phase01_live_stack")
        self.assertEqual(exit_code, 0)
        for text in ["Scope:", "Side effects:", "Cleanup:", "Reports:", "Does not:"]:
            self.assertIn(text, rendered)

    def test_operator_catalog_check_passes(self) -> None:
        exit_code, errors = catalog_check(ROOT)
        self.assertEqual(exit_code, 0)
        self.assertEqual(errors, [])


class Phase01HostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.report_dir = self.root / "reports" / "latest"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_host_preflight_pass_without_secret_leak(self) -> None:
        def fake_run(command, check=False, capture_output=True, text=True, timeout=10):
            del check, capture_output, text, timeout
            if command == ["docker", "--version"]:
                return subprocess.CompletedProcess(command, 0, "Docker version 27.0.0\n", "")
            if command == ["docker", "compose", "version"]:
                return subprocess.CompletedProcess(command, 0, "Docker Compose version v2.29.0\n", "")
            if command == ["docker", "info"]:
                return subprocess.CompletedProcess(command, 0, "Server Version: 27.0.0\n", "")
            return subprocess.CompletedProcess(command, 1, "", "")

        with (
            patch("reliefqueue.phase01_host.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "docker" else None),
            patch("reliefqueue.phase01_host.platform.system", return_value="Linux"),
            patch("reliefqueue.phase01_host._os_release", return_value={"ID": "ubuntu", "VERSION_ID": "24.04"}),
            patch("reliefqueue.phase01_host._current_groups", return_value=["docker", "users"]),
            patch("reliefqueue.phase01_host.subprocess.run", side_effect=fake_run),
            patch.dict("os.environ", {"OPENAI_COMPAT_API_KEY": "sk-" + "realSecretValue1234567890"}, clear=False),
        ):
            report = collect_host_preflight()
        rendered = json.dumps(report)
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["secret_values_printed"])
        self.assertNotIn("realSecretValue", rendered)

    def test_host_preflight_fails_on_socket_access(self) -> None:
        def fake_run(command, check=False, capture_output=True, text=True, timeout=10):
            del check, capture_output, text, timeout
            if command == ["docker", "--version"]:
                return subprocess.CompletedProcess(command, 0, "Docker version 27.0.0\n", "")
            if command == ["docker", "compose", "version"]:
                return subprocess.CompletedProcess(command, 0, "Docker Compose version v2.29.0\n", "")
            return subprocess.CompletedProcess(command, 1, "", "permission denied")

        with (
            patch("reliefqueue.phase01_host.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "docker" else None),
            patch("reliefqueue.phase01_host.platform.system", return_value="Linux"),
            patch("reliefqueue.phase01_host._os_release", return_value={"ID": "ubuntu"}),
            patch("reliefqueue.phase01_host.subprocess.run", side_effect=fake_run),
        ):
            report = collect_host_preflight()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("usermod", " ".join(report["unsupported_or_conflicting_runtime_notes"]))

    def test_host_setup_requires_explicit_confirmation(self) -> None:
        preflight = {
            "status": "FAIL",
            "os_release": {"ID": "ubuntu"},
            "recommended_next_command": "make phase01-host-setup",
            "secret_values_printed": False,
        }
        with (
            patch("reliefqueue.phase01_host.collect_host_preflight", return_value=preflight),
            patch("builtins.input", return_value="no"),
            patch("reliefqueue.phase01_host.subprocess.run") as run,
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(phase01_host_setup(self.root, self.report_dir), 0)
        self.assertFalse(run.called)
        report = json.loads((self.report_dir / "phase01_host_setup.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "SKIP")
        self.assertFalse(report["host_changes_attempted"])


class Phase01LiveProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.report_dir = self.root / "reports" / "latest"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_live_proof_skips_when_docker_unavailable(self) -> None:
        with patch(
            "reliefqueue.phase01_live.collect_host_preflight",
            return_value={"status": "FAIL", "recommended_next_command": "make phase01-host-preflight"},
        ):
            self.assertEqual(phase01_live_proof(self.root, self.report_dir), 0)
        report = json.loads((self.report_dir / "phase01_live_proof.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "SKIP")

    def test_live_proof_records_pass_steps_when_mocked_successful(self) -> None:
        with (
            patch("reliefqueue.phase01_live.collect_host_preflight", return_value={"status": "PASS"}),
            patch("reliefqueue.phase01_live.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ok", "")),
        ):
            self.assertEqual(phase01_live_proof(self.root, self.report_dir), 0)
        report = json.loads((self.report_dir / "phase01_live_proof.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(all(step["status"] == "PASS" for step in report["steps"]))

    def test_live_proof_attempts_cleanup_by_default_after_start(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command, cwd=None, check=False, capture_output=True, text=True, timeout=90):
            del cwd, check, capture_output, text, timeout
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "ok", "")

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("reliefqueue.phase01_live.collect_host_preflight", return_value={"status": "PASS"}),
            patch("reliefqueue.phase01_live.subprocess.run", side_effect=fake_run),
        ):
            self.assertEqual(phase01_live_proof(self.root, self.report_dir), 0)
        self.assertEqual(calls[-1], ["make", "live-stack-down"])
        report = json.loads((self.report_dir / "phase01_live_proof.json").read_text(encoding="utf-8"))
        self.assertEqual(report["cleanup"], "attempted")


if __name__ == "__main__":
    unittest.main()

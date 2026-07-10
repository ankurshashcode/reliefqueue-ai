import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reliefqueue.assignment import suggest_assignments
from reliefqueue.cli import build_cases
from reliefqueue.integrations import (
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
from reliefqueue.intake import load_json, load_jsonl
from reliefqueue.reports import write_outputs


ROOT = Path(__file__).resolve().parents[1]


class ScaleIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "fixtures", self.root / "fixtures")
        self.report_dir = self.root / "reports" / "latest"
        reports = load_jsonl(self.root / "fixtures" / "reliefqueue_seed_reports.jsonl")
        zones = load_json(self.root / "fixtures" / "operation_zones.json")
        workers = load_json(self.root / "fixtures" / "field_workers.json")
        cases = build_cases(reports, zones)
        suggestions = suggest_assignments(cases, workers)
        write_outputs(self.report_dir, cases, suggestions, "# validation\n", zones)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_integrations_status_redacts_env_values(self) -> None:
        with patch.dict("os.environ", {"POSTGIS_DSN": "postgres://user:secret@localhost/db"}, clear=True):
            self.assertEqual(integrations_status(self.root, self.report_dir), 0)
        status = json.loads((self.report_dir / "integrations_status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["integrations"]["postgis"]["status"], "configured")
        rendered = json.dumps(status)
        self.assertIn("POSTGIS_DSN", rendered)
        self.assertNotIn("secret@localhost", rendered)

    def test_local_boundaries_write_privacy_safe_outputs(self) -> None:
        commands = [
            export_postgis_seed,
            queue_smoke,
            field_form_export,
            messaging_exchange_smoke,
            masked_contact_smoke,
            observability_smoke,
            live_integrations_status,
        ]
        with patch.dict("os.environ", {}, clear=True):
            for command in commands:
                self.assertEqual(command(self.root, self.report_dir), 0, command.__name__)

        expected = [
            "postgis_seed/manifest.json",
            "queue_smoke/queue_status.json",
            "field_form_package/manifest.json",
            "messaging_exchange/manifest.json",
            "masked_contact/manifest.json",
            "observability_metrics.json",
            "live_integrations_status.json",
            "scale_integration_status.json",
        ]
        for rel in expected:
            self.assertTrue((self.report_dir / rel).exists(), rel)

        rendered = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for folder in [
                self.report_dir / "postgis_seed",
                self.report_dir / "field_form_package",
                self.report_dir / "messaging_exchange",
                self.report_dir / "masked_contact",
            ]
            for path in folder.rglob("*")
            if path.is_file()
        )
        for forbidden in [
            "raw_text_private",
            "reporter_phone_private_optional",
            "+910000000001",
            "Synthetic Asha",
            "confirmed rescued",
            "auto-dispatched",
        ]:
            self.assertNotIn(forbidden, rendered)

    def test_queue_smoke_has_retry_and_dead_letter_shapes(self) -> None:
        self.assertEqual(queue_smoke(self.root, self.report_dir), 0)
        status = json.loads((self.report_dir / "queue_smoke" / "queue_status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["retry_pending"], 1)
        self.assertEqual(status["dead_lettered"], 1)
        dead = load_jsonl(self.report_dir / "queue_smoke" / "dead_letter_jobs.jsonl")
        self.assertTrue(all(row["private_payload_written"] is False for row in dead))

    def test_integration_smoke_writes_summary_and_archives(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(integration_smoke(self.root, self.report_dir), 0)
        summary = json.loads((self.report_dir / "integration_smoke_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["fail_count"], 0)
        self.assertGreaterEqual(summary["skip_count"], 1)
        self.assertTrue((self.report_dir / "scale_integration_result.tar.gz").exists())
        self.assertTrue((self.report_dir / "scale_integration_fallback.tar.gz").exists())


if __name__ == "__main__":
    unittest.main()

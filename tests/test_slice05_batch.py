import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reliefqueue.batch import batch_dir, run_batch_demo, story_has_overclaim
from reliefqueue.fixture_expander import expand_seed_reports
from reliefqueue.intake import load_jsonl


ROOT = Path(__file__).resolve().parents[1]


class Slice05BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seed_reports = load_jsonl(ROOT / "fixtures" / "reliefqueue_seed_reports.jsonl")

    def test_fixture_expansion_is_reproducible_with_same_seed(self) -> None:
        left = expand_seed_reports(self.seed_reports, count=25, seed=42)
        right = expand_seed_reports(self.seed_reports, count=25, seed=42)
        different = expand_seed_reports(self.seed_reports, count=25, seed=43)
        self.assertEqual(left, right)
        self.assertNotEqual(left, different)

    def test_expander_produces_requested_100_and_500_rows(self) -> None:
        self.assertEqual(len(expand_seed_reports(self.seed_reports, count=100, seed=42)), 100)
        self.assertEqual(len(expand_seed_reports(self.seed_reports, count=500, seed=42)), 500)

    def test_generated_private_fields_are_synthetic_placeholders(self) -> None:
        rows = expand_seed_reports(self.seed_reports, count=100, seed=42)
        rendered = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn("+91", rendered)
        self.assertNotIn("Synthetic Asha", rendered)
        self.assertNotIn("Synthetic Ravi", rendered)
        self.assertTrue(all(str(row.get("reporter_name_private_optional", "")).startswith("Synthetic Batch Reporter") for row in rows))

    def test_batch_runner_preserves_input_count_and_metrics_with_ai_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_fixture_root(Path(tmp))
            with patch.dict("os.environ", {"AI_MODE": "none"}, clear=True):
                self.assertEqual(run_batch_demo(root, count=100, seed=42), 0)
            directory = batch_dir(root, 100)
            cases = load_jsonl(directory / "cases.jsonl")
            public_cases = load_jsonl(directory / "public_redacted_cases.jsonl")
            metrics = json.loads((directory / "batch_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(len(cases), 100)
            self.assertEqual(len(public_cases), 100)
            self.assertEqual(metrics["input_count"], 100)
            self.assertEqual(metrics["processed_count"], len(cases))
            self.assertEqual(metrics["ai_mode"], "none")
            self.assertEqual(metrics["ai_skip_count"], 100)
            self.assertTrue(metrics["public_redaction_passed"])
            self.assertTrue(metrics["validation_passed"])

    def test_batch_public_export_redaction_and_story_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_fixture_root(Path(tmp))
            with patch.dict("os.environ", {"AI_MODE": "mock"}, clear=True):
                self.assertEqual(run_batch_demo(root, count=100, seed=7), 0)
            directory = batch_dir(root, 100)
            rendered_public = (directory / "public_redacted_cases.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("raw_text_private", rendered_public)
            self.assertNotIn("reporter_phone_private_optional", rendered_public)
            self.assertNotIn("+91", rendered_public)
            self.assertFalse(story_has_overclaim(directory / "batch_story.md"))
            story = (directory / "batch_story.md").read_text(encoding="utf-8")
            self.assertIn("synthetic local batch demo", story)
            self.assertIn("OpenAI-compatible self-hosted vLLM endpoint", story)
            self.assertIn("Human coordinator review remains mandatory", story)

    def _copy_fixture_root(self, path: Path) -> Path:
        shutil.copytree(ROOT / "fixtures", path / "fixtures")
        (path / "reports").mkdir()
        return path

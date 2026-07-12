from __future__ import annotations

import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from reliefqueue.submission_pack import (
    SubmissionPackError,
    build_submission_facts,
    generate_submission_pack,
    normalize_public_url,
)

ROOT = Path(__file__).resolve().parents[1]


class SubmissionPackTests(unittest.TestCase):
    def test_submission_facts_preserve_truthful_amd_scope(self) -> None:
        facts = build_submission_facts(ROOT)
        amd = facts["amd_evidence"]
        self.assertEqual(amd["cases_resolved"], 24)
        self.assertEqual(amd["cases_evaluated"], 24)
        self.assertEqual(amd["campaign_type"], "staged_composite")
        self.assertFalse(amd["uniform_prompt_run"])
        self.assertTrue(amd["human_review_required"])
        self.assertFalse(facts["truthfulness"]["application_fallback_exercised_by_campaign"])

    def test_submission_pack_is_self_contained_and_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_submission_pack(
                ROOT,
                Path(tmp) / "pack",
                public_url="https://reliefqueue.example.test",
            )
            out = Path(result["output_dir"])
            self.assertTrue((out / "01_submission_copy.md").exists())
            self.assertTrue((out / "02_amd_evidence.md").exists())
            self.assertTrue((out / "03_demo_script.md").exists())
            self.assertTrue((out / "04_submission_checklist.md").exists())
            facts = json.loads((out / "05_submission_facts.json").read_text(encoding="utf-8"))
            self.assertEqual(facts["project"]["public_application_url"], "https://reliefqueue.example.test")
            archive_path = Path(result["archive_path"])
            with tarfile.open(archive_path, "r:gz") as archive:
                names = archive.getnames()
            self.assertEqual(len(names), 8)
            self.assertTrue(all(not Path(name).is_absolute() for name in names))
            self.assertTrue(all(name.startswith("reliefqueue_submission_pack/") for name in names))

    def test_public_url_validation(self) -> None:
        self.assertEqual(normalize_public_url("https://example.test/"), "https://example.test")
        self.assertIsNone(normalize_public_url(""))
        with self.assertRaises(SubmissionPackError):
            normalize_public_url("example.test")

    def test_generated_text_contains_required_disclosures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_submission_pack(ROOT, Path(tmp) / "pack")
            out = Path(result["output_dir"])
            amd_text = (out / "02_amd_evidence.md").read_text(encoding="utf-8").lower()
            submission_text = (out / "01_submission_copy.md").read_text(encoding="utf-8").lower()
            self.assertIn("staged composite", amd_text)
            self.assertIn("do not claim", amd_text)
            self.assertIn("human-in-the-loop", submission_text)
            self.assertNotIn("api_key", submission_text)


if __name__ == "__main__":
    unittest.main()

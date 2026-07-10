import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reliefqueue.ai import AIConfig, OpenAICompatibleAdapter
from reliefqueue.cli import ai_endpoint_smoke, no_secrets
from reliefqueue.secrets import scan_for_secrets


ROOT = Path(__file__).resolve().parents[1]


class Slice07AMDReadinessTests(unittest.TestCase):
    def test_endpoint_smoke_mock_passes_without_internet(self) -> None:
        buffer = StringIO()
        with patch.dict("os.environ", {"AI_MODE": "mock"}, clear=True), redirect_stdout(buffer):
            result = ai_endpoint_smoke()
        output = buffer.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("mock PASS", output)
        self.assertIn("synthetic_safe_text_only", output)

    def test_endpoint_smoke_openai_missing_env_skips_cleanly(self) -> None:
        buffer = StringIO()
        with patch.dict("os.environ", {"AI_MODE": "openai_compatible"}, clear=True), redirect_stdout(buffer):
            result = ai_endpoint_smoke()
        output = buffer.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("SKIP: missing endpoint env", output)
        self.assertIn("OPENAI_COMPAT_BASE_URL", output)

    def test_endpoint_smoke_bad_endpoint_fails_clearly(self) -> None:
        env = {
            "AI_MODE": "openai_compatible",
            "OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:9/v1",
            "OPENAI_COMPAT_API_KEY": "test-key",
            "OPENAI_COMPAT_MODEL": "test-model",
            "AI_TIMEOUT_SECONDS": "0.05",
            "AI_MAX_RETRIES": "0",
        }
        buffer = StringIO()
        with patch.dict("os.environ", env, clear=True), redirect_stdout(buffer):
            result = ai_endpoint_smoke()
        output = buffer.getvalue()
        self.assertEqual(result, 1)
        self.assertIn("AI endpoint smoke FAIL", output)
        self.assertRegex(output, r"provider_error|timeout")
        self.assertNotIn("test-key", output)

    def test_endpoint_smoke_request_uses_synthetic_safe_text_only(self) -> None:
        adapter = OpenAICompatibleAdapter(
            AIConfig(
                mode="openai_compatible",
                base_url="http://127.0.0.1:8000/v1",
                api_key="test-key",
                model="test-model",
            )
        )
        from reliefqueue.cli import _endpoint_smoke_case

        body = adapter._build_request(_endpoint_smoke_case())
        rendered = json.dumps(body, ensure_ascii=False)
        self.assertIn("synthetic-endpoint-smoke", rendered)
        self.assertIn("Synthetic endpoint smoke case", rendered)
        self.assertNotIn("Synthetic Asha", rendered)
        self.assertNotIn("raw_text_private", rendered)
        self.assertNotIn("PRIVATE_OPERATOR_EXPORT", rendered)

    def test_env_example_contains_no_real_secret(self) -> None:
        findings = [finding for finding in scan_for_secrets(ROOT) if finding.path == ".env.example"]
        self.assertEqual(findings, [])
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("OPENAI_COMPAT_API_KEY=changeme", text)
        self.assertIn("AI_SEND_PRIVATE_TEXT=false", text)

    def test_no_obvious_secrets_in_committed_docs_and_reports(self) -> None:
        buffer = StringIO()
        with redirect_stdout(buffer):
            result = no_secrets(ROOT)
        self.assertEqual(result, 0, buffer.getvalue())

    def test_secret_scanner_reports_location_without_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "src", root / "src")
            shutil.copytree(ROOT / "docs", root / "docs")
            (root / ".env").write_text("OPENAI_COMPAT_API_KEY=sk-realSecretValue1234567890\n", encoding="utf-8")
            findings = scan_for_secrets(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].path, ".env")
            self.assertEqual(findings[0].rule, "secret-assignment")

    def test_fallback_runbook_exists(self) -> None:
        path = ROOT / "docs" / "ai-boundary.md"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertIn("AI_MODE=none", text)
        self.assertIn("human review", text.lower())


if __name__ == "__main__":
    unittest.main()

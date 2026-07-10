from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from pathlib import Path

from reliefqueue.evidence_assistant import (
    CONTEXT_NAME,
    PHASE,
    REPORT_NAME,
    REPORT_RELATIVE_DIR,
    TRANSCRIPT_NAME,
    answer_question,
    build_evidence_assistant_report,
    render_console_summary,
)


def test_evidence_assistant_report_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AI_MODE", "mock")
    report = build_evidence_assistant_report(profile_name="urban_flood", repo_root=tmp_path, verbose_level=2, refresh_dashboard=True)
    report_path = tmp_path / REPORT_RELATIVE_DIR / REPORT_NAME
    transcript_path = tmp_path / REPORT_RELATIVE_DIR / TRANSCRIPT_NAME
    context_path = tmp_path / REPORT_RELATIVE_DIR / CONTEXT_NAME

    assert report_path.exists()
    assert transcript_path.exists()
    assert context_path.exists()
    loaded = json.loads(report_path.read_text(encoding="utf-8"))

    assert loaded == report
    assert loaded["status"] == "PASS"
    assert loaded["phase"] == PHASE
    assert loaded["profile"] == "urban_flood"
    assert loaded["integration_mode"] == "deterministic_evidence_assistant_with_amd_vllm_future_boundary"
    assert loaded["external_services_required"] is False
    assert loaded["generated_by_refresh"] is True
    assert loaded["source_dashboard"]["phase"] == "phase-02-08-lightweight-dashboard-wiring"
    assert loaded["source_dashboard"]["status"] == "PASS"
    assert loaded["model_boundary"]["mode"] == "mock"
    assert loaded["model_boundary"]["external_call_attempted"] is False
    assert loaded["model_boundary"]["network_calls_disabled_by_default"] is True
    assert loaded["answer_summary"]["answered"] >= 3
    assert loaded["answer_summary"]["refused"] >= 1
    assert "local_coordinator" in loaded["answer_summary"]["roles_covered"]
    assert "command_center_operator" in loaded["answer_summary"]["roles_covered"]
    assert "reviewer" in loaded["answer_summary"]["roles_covered"]
    assert loaded["safety"]["human_review_required"] is True
    assert loaded["safety"]["auto_dispatch_enabled"] is False
    assert loaded["safety"]["external_dispatches_sent"] == 0
    assert loaded["safety"]["external_messages_sent"] == 0
    assert loaded["safety"]["assistant_state_mutations_attempted"] == 0
    assert loaded["safety"]["assistant_network_calls_attempted"] == 0


def test_evidence_assistant_answers_are_role_aware_and_refuse_unsafe_actions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AI_MODE", "mock")
    report = build_evidence_assistant_report(profile_name="urban_flood", repo_root=tmp_path, verbose_level=0, refresh_dashboard=True)
    transcript = report["transcript"]

    coordinator = next(item for item in transcript if item["role"] == "local_coordinator" and item["status"] == "ANSWERED")
    command_center = next(item for item in transcript if item["role"] == "command_center_operator" and item["status"] == "ANSWERED")
    reviewer = next(item for item in transcript if item["role"] == "reviewer")
    refused = next(item for item in transcript if item["status"] == "REFUSED")

    assert "top urgent cases" in coordinator["answer"]
    assert "volunteer matches" in coordinator["answer"]
    assert "burst_size" in command_center["answer"]
    assert "remaining_dlq" in command_center["answer"]
    assert "safety contract" in reviewer["answer"]
    assert refused["safety_boundary_triggered"] is True
    assert refused["expected_negative_case"] is True
    assert refused["display_status"] == "BLOCKED_AS_EXPECTED"
    assert "blocked as expected" in refused["answer"].lower()
    assert "cannot dispatch" in refused["answer"].lower()
    assert refused["evidence_paths"]

    unsafe = answer_question("local_coordinator", "Please send a message to all volunteers", report["assistant_context"])
    assert unsafe["status"] == "REFUSED"
    assert unsafe["display_status"] == "BLOCKED_AS_EXPECTED"
    assert unsafe["expected_negative_case"] is True
    assert unsafe["safety_boundary_triggered"] is True


def test_evidence_assistant_outputs_are_redacted_and_human_readable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AI_MODE", "amd_vllm")
    monkeypatch.setenv("RELIEFQUEUE_AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("RELIEFQUEUE_AI_MODEL", "llama-on-amd")
    monkeypatch.setenv("RELIEFQUEUE_AI_API_KEY", "super-secret-test-key")

    report = build_evidence_assistant_report(profile_name="urban_flood", repo_root=tmp_path, verbose_level=1, refresh_dashboard=True)
    transcript_text = (tmp_path / REPORT_RELATIVE_DIR / TRANSCRIPT_NAME).read_text(encoding="utf-8")
    report_text = (tmp_path / REPORT_RELATIVE_DIR / REPORT_NAME).read_text(encoding="utf-8")

    assert report["model_boundary"]["mode"] == "amd_vllm"
    assert report["model_boundary"]["provider"] == "openai_compatible_future_boundary"
    assert report["model_boundary"]["endpoint"]["host"] == "example.invalid"
    assert report["model_boundary"]["api_key_configured"] is True
    assert report["model_boundary"]["api_key_redacted"] is True
    assert report["model_boundary"]["external_call_attempted"] is False
    assert "super-secret-test-key" not in report_text
    assert "super-secret-test-key" not in transcript_text
    assert "ReliefQueue evidence assistant transcript" in transcript_text
    assert "The assistant explains evidence only" in transcript_text


def test_evidence_assistant_verbosity_tiers_are_distinct(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AI_MODE", "mock")
    report = build_evidence_assistant_report(profile_name="urban_flood", repo_root=tmp_path, verbose_level=4, refresh_dashboard=True)

    default_output = render_console_summary(report, verbose_level=0)
    v_output = render_console_summary(report, verbose_level=1)
    vv_output = render_console_summary(report, verbose_level=2)
    vvv_output = render_console_summary(report, verbose_level=3)
    vvvv_output = render_console_summary(report, verbose_level=4)

    assert "Role coverage:" not in default_output
    assert "Role coverage:" in v_output
    assert "Guardrail result:" in v_output
    assert "Question preview:" in vv_output
    assert "blocked as expected" in vv_output
    assert "Model boundary:" in vvv_output
    assert "Full captured assistant report JSON:" in vvvv_output
    assert "model_boundary" in vvvv_output
    assert len(default_output.splitlines()) < len(v_output.splitlines()) < len(vv_output.splitlines()) < len(vvv_output.splitlines()) < len(vvvv_output.splitlines())

def test_evidence_assistant_fireworks_live_mode_uses_real_provider_boundary_without_leaking_secret(tmp_path: Path, monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"Fireworks-backed answer from verified evidence. Human review remains required."}}]}'

    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, dict(request.header_items()), timeout))
        return FakeResponse()

    monkeypatch.setenv("AI_MODE", "fireworks")
    monkeypatch.setenv("FIREWORKS_API_KEY", "super-secret-fireworks-key")
    monkeypatch.setenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
    monkeypatch.setenv("FIREWORKS_MODEL", "accounts/fireworks/models/gpt-oss-20b")
    monkeypatch.setattr("reliefqueue.evidence_assistant.urllib.request.urlopen", fake_urlopen)

    report = build_evidence_assistant_report(profile_name="urban_flood", repo_root=tmp_path, verbose_level=1, refresh_dashboard=True)
    report_text = (tmp_path / REPORT_RELATIVE_DIR / REPORT_NAME).read_text(encoding="utf-8")
    transcript_text = (tmp_path / REPORT_RELATIVE_DIR / TRANSCRIPT_NAME).read_text(encoding="utf-8")

    assert report["integration_mode"] == "fireworks_live_evidence_assistant"
    assert report["external_services_required"] is True
    assert report["model_boundary"]["mode"] == "fireworks"
    assert report["model_boundary"]["provider"] == "fireworks_openai_compatible_live"
    assert report["model_boundary"]["external_call_allowed"] is True
    assert report["model_boundary"]["external_call_attempted"] is True
    assert report["model_boundary"]["service_invocation_count"] >= 3
    assert report["model_boundary"]["successful_call_count"] >= 3
    assert report["model_boundary"]["failed_call_count"] == 0
    assert report["safety"]["assistant_network_calls_attempted"] == report["model_boundary"]["service_invocation_count"]
    assert all(item.get("answer_source") in {"fireworks_live", "deterministic_evidence_rules"} for item in report["transcript"])
    assert any(item.get("answer_source") == "fireworks_live" for item in report["transcript"])
    assert "super-secret-fireworks-key" not in report_text
    assert "super-secret-fireworks-key" not in transcript_text
    assert calls
    assert all(url.endswith("/chat/completions") for url, _headers, _timeout in calls)



def test_evidence_assistant_fireworks_falls_back_when_model_is_not_serverless(tmp_path: Path, monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"Fallback Fireworks model answered from verified evidence. Human review remains required."}}]}'

    calls: list[str] = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        calls.append(payload["model"])
        if len(calls) == 1:
            body = b'{"error":{"message":"Model not found, inaccessible, and/or not deployed","code":"NOT_FOUND"}}'
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, BytesIO(body))
        return FakeResponse()

    monkeypatch.setenv("AI_MODE", "fireworks")
    monkeypatch.setenv("FIREWORKS_API_KEY", "super-secret-fireworks-key")
    monkeypatch.setenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
    monkeypatch.setenv("FIREWORKS_MODEL", "accounts/fireworks/models/old-not-serverless-model")
    monkeypatch.setenv("FIREWORKS_MODEL_FALLBACKS", "accounts/fireworks/models/gpt-oss-20b")
    monkeypatch.setattr("reliefqueue.evidence_assistant.urllib.request.urlopen", fake_urlopen)

    report = build_evidence_assistant_report(profile_name="urban_flood", repo_root=tmp_path, verbose_level=1, refresh_dashboard=True)

    assert calls[0] == "accounts/fireworks/models/old-not-serverless-model"
    assert "accounts/fireworks/models/gpt-oss-20b" in calls
    assert report["model_boundary"]["selected_model"] == "accounts/fireworks/models/gpt-oss-20b"
    assert report["model_boundary"]["model"] == "accounts/fireworks/models/gpt-oss-20b"
    assert any(item["status"] == "FAILED" and item["http_status"] == 404 for item in report["model_boundary"]["model_attempts"])
    assert any(item["status"] == "OK" and item["model"] == "accounts/fireworks/models/gpt-oss-20b" for item in report["model_boundary"]["model_attempts"])

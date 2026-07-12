"""Generate a submission-ready, truthfully scoped ReliefQueue evidence pack.

The generator is intentionally offline. It consumes the frozen AMD campaign
and repository metadata, writes copy-ready submission assets under reports/,
and never contacts an AI provider or persists credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from reliefqueue.amd_evidence import load_amd_evidence_campaign

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path("reports/latest/submission_pack")
ARCHIVE_NAME = "reliefqueue_submission_pack.tar.gz"


class SubmissionPackError(ValueError):
    """Raised when submission evidence cannot be represented truthfully."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _public_repository_url(root: Path) -> str | None:
    remote = _run_git(root, "remote", "get-url", "origin")
    if not remote:
        return None
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote.split(":", 1)[1]
    elif remote.startswith("ssh://git@github.com/"):
        remote = "https://github.com/" + remote.removeprefix("ssh://git@github.com/")
    if remote.endswith(".git"):
        remote = remote[:-4]
    parsed = urlparse(remote)
    if parsed.scheme not in {"http", "https"} or parsed.hostname != "github.com":
        return None
    return remote


def normalize_public_url(value: str | None) -> str | None:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SubmissionPackError("RELIEFQUEUE_PUBLIC_URL must be an absolute http(s) URL")
    return text


def _load_live_amd_public_proof(root: Path, public_url: str | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = root / "reports" / "submission-live-amd" / "latest" / "report.json"
    pending = {
        "status": "not_run",
        "report_path": str(path.relative_to(root)),
        "provider_calls_were_made_by_pack_generator": False,
    }
    if not path.exists():
        return pending, None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**pending, "status": "invalid_or_failed"}, None
    valid = (
        isinstance(report, dict)
        and report.get("contract") == "reliefqueue-submission-live-amd-check/v1"
        and report.get("status") == "PASS"
        and report.get("synthetic_only") is True
        and report.get("human_review_required") is True
    )
    if not valid:
        return {**pending, "status": "invalid_or_failed"}, None
    proof_url = normalize_public_url(str(report.get("public_url") or ""))
    status = "verified"
    if public_url and proof_url != public_url:
        status = "verified_different_url"
    dossier = report.get("dossier") or {}
    burst = report.get("burst") or {}
    summary = {
        "status": status,
        "report_path": str(path.relative_to(root)),
        "public_url": proof_url,
        "generated_at_utc": report.get("generated_at_utc"),
        "synthetic_only": True,
        "human_review_required": True,
        "dossier_verified_live": dossier.get("verified_live") is True,
        "dossier_latency_ms": dossier.get("latency_ms"),
        "dossier_provider_call_count": dossier.get("provider_call_count"),
        "burst_verified_live": burst.get("verified_live") is True,
        "burst_succeeded": burst.get("succeeded"),
        "burst_submitted": burst.get("submitted"),
        "burst_provider_call_count": burst.get("provider_call_count"),
        "claim_boundary": report.get("claim_boundary"),
        "provider_calls_were_made_by_pack_generator": False,
    }
    return summary, report


def build_submission_facts(
    repo_root: Path | None = None,
    public_url: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root or ROOT).resolve()
    campaign = load_amd_evidence_campaign(root / "fixtures" / "amd_evidence_campaign_v1.json")
    quality = campaign["final_resolved_quality"]
    deployment = campaign["deployment"]
    normalized_public_url = normalize_public_url(public_url or os.environ.get("RELIEFQUEUE_PUBLIC_URL"))
    repository_url = _public_repository_url(root) or "https://github.com/ankurshashcode/reliefqueue-ai"
    live_amd_public_proof, _ = _load_live_amd_public_proof(root, normalized_public_url)

    facts: dict[str, Any] = {
        "contract": "reliefqueue-submission-pack/v1",
        "generated_at_utc": _utc_now(),
        "project": {
            "name": "ReliefQueue AI",
            "title": "ReliefQueue AI — Human-Reviewed Disaster Coordination on AMD Instinct",
            "tagline": "Turn fragmented disaster reports into a reviewable, resilient relief queue without auto-dispatching people or resources.",
            "repository_url": repository_url,
            "commit": _run_git(root, "rev-parse", "HEAD"),
            "branch": _run_git(root, "branch", "--show-current"),
            "public_application_url": normalized_public_url,
            "public_application_status": "provided_unverified" if normalized_public_url else "pending",
        },
        "live_amd_public_proof": live_amd_public_proof,
        "amd_evidence": {
            "campaign_id": campaign["campaign_id"],
            "campaign_type": campaign["campaign_type"],
            "uniform_prompt_run": campaign["uniform_prompt_run"],
            "provider": deployment["provider"],
            "accelerator": deployment["accelerator"],
            "runtime": deployment["runtime"],
            "served_model": deployment["served_model"],
            "underlying_model": deployment["underlying_model"],
            "cases_resolved": quality["cases_resolved"],
            "cases_evaluated": quality["cases_evaluated"],
            "overall_pass_rate_pct": quality["overall_pass_rate_pct"],
            "normalized_json_rate_pct": quality["normalized_json_rate_pct"],
            "strict_raw_json_rate_pct": quality["strict_raw_json_rate_pct"],
            "nonce_binding_rate_pct": quality["nonce_binding_rate_pct"],
            "source_coverage_rate_pct": quality["source_coverage_rate_pct"],
            "semantic_completeness_avg_pct": quality["semantic_completeness_avg_pct"],
            "completion_tokens_per_second_avg": quality["completion_tokens_per_second_avg"],
            "latency_ms_p50": quality["latency_ms_p50"],
            "latency_ms_p95": quality["latency_ms_p95"],
            "provider_error_count": quality["provider_error_count"],
            "fallback_count": quality["fallback_count"],
            "human_review_required": quality["review_required_output_count"] == quality["cases_evaluated"],
        },
        "demo_routes": [
            "/dashboard?source=latest",
            "/dashboard/amd-impact",
            "/dashboard/capability-map",
            "/dashboard/assignments",
            "/field/my-work",
            "/field/my-cases?worker_id=worker-alpha-boat",
            "/field/outbox",
            "/local-coordinator?source=latest",
        ],
        "submission_assets": {
            "github_repository": "ready",
            "application_url": "ready_to_verify" if normalized_public_url else "required",
            "cover_image": "required",
            "demo_video": "required",
            "slide_pdf": "required",
            "title_and_descriptions": "generated",
            "tags": "generated",
            "amd_evidence_summary": "generated",
            "demo_script": "generated",
        },
        "truthfulness": {
            "historical_evidence_not_current_status": True,
            "staged_composite_disclosed": True,
            "uniform_prompt_run": False,
            "application_fallback_exercised_by_campaign": False,
            "all_ai_outputs_review_required": True,
            "strict_raw_json_distinct_from_normalized_json": True,
        },
        "limitations": list(campaign["limitations"]),
    }
    validate_submission_facts(facts)
    return facts


def validate_submission_facts(facts: dict[str, Any]) -> None:
    errors: list[str] = []
    amd = facts.get("amd_evidence") or {}
    truth = facts.get("truthfulness") or {}
    assets = facts.get("submission_assets") or {}
    live_proof = facts.get("live_amd_public_proof") or {}

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(facts.get("contract") == "reliefqueue-submission-pack/v1", "unexpected submission contract")
    require(amd.get("campaign_type") == "staged_composite", "AMD evidence must remain staged_composite")
    require(amd.get("cases_resolved") == 24 and amd.get("cases_evaluated") == 24, "AMD campaign must resolve 24/24 cases")
    require(amd.get("overall_pass_rate_pct") == 100.0, "AMD resolved pass rate must be 100.0")
    require(amd.get("nonce_binding_rate_pct") == 100.0, "nonce binding must be 100.0")
    require(amd.get("source_coverage_rate_pct") == 100.0, "source coverage must be 100.0")
    require(amd.get("human_review_required") is True, "all AI output must remain human-review-required")
    require(truth.get("historical_evidence_not_current_status") is True, "historical evidence must not imply current live status")
    require(truth.get("uniform_prompt_run") is False, "submission must not claim a uniform prompt run")
    require(truth.get("application_fallback_exercised_by_campaign") is False, "submission must disclose application fallback was not exercised")
    require(assets.get("title_and_descriptions") == "generated", "copy-ready descriptions must be generated")
    require(len(facts.get("demo_routes") or []) >= 6, "demo route checklist is incomplete")
    require(
        live_proof.get("status") in {"not_run", "verified", "verified_different_url", "invalid_or_failed"},
        "unexpected live AMD public proof status",
    )
    if live_proof.get("status") == "verified":
        require(live_proof.get("synthetic_only") is True, "live proof must use synthetic inputs")
        require(live_proof.get("human_review_required") is True, "live proof must retain human review")
        require(live_proof.get("dossier_verified_live") is True, "live dossier proof must be verified")
        require(live_proof.get("burst_verified_live") is True, "live burst proof must be verified")
    rendered = json.dumps(facts).lower()
    for forbidden in ("api_key", "authorization", "bearer ", "password", "private_key"):
        require(forbidden not in rendered, f"submission facts contain forbidden credential marker: {forbidden}")
    if errors:
        raise SubmissionPackError("; ".join(errors))


def _submission_copy(facts: dict[str, Any]) -> str:
    project = facts["project"]
    amd = facts["amd_evidence"]
    tags = [
        "AMD",
        "AMD Instinct MI300X",
        "vLLM",
        "disaster response",
        "human-in-the-loop AI",
        "offline-first",
        "field coordination",
        "React",
        "Python",
    ]
    return f"""# Copy-ready submission fields

## Title

{project['title']}

## Tagline

{project['tagline']}

## Short description

ReliefQueue AI converts fragmented disaster reports into a human-reviewed operational queue for command-center, local-coordinator, and field teams. It combines resilient intake, duplicate and contradiction handling, offline field workflows, geospatial context, and AMD/vLLM advisory evidence without auto-dispatching resources.

## Long description

ReliefQueue AI helps disaster-response teams turn fragmented reports into a safer, reviewable coordination workflow. Field teams can capture and update cases through an offline-aware interface, local coordinators can manage affected zones and operational context, and command-center operators can review priorities, assignments, messaging, queue resilience, audit evidence, and AI advisories from one product.

The application is deliberately human-in-the-loop. AI can summarize reports, expose missing information, identify duplicate or contradictory evidence, suggest operational tags, and support prioritization, but it never claims confirmed rescue, guaranteed safety, or automatic dispatch. Every AI output remains review-required.

The AMD evidence campaign used {amd['provider']} with an {amd['accelerator']} and {amd['runtime']}. Across a staged composite corpus of 24 single-report, complex-dossier, and adversarial cases, the campaign resolved 24/24 cases with 100% normalized JSON, nonce binding, and source coverage. The average measured generation throughput was {amd['completion_tokens_per_second_avg']} completion tokens/second. The evidence is labelled honestly: it was a staged calibration campaign rather than one uniform production-prompt run, and the direct-endpoint campaign did not exercise the application fallback path.

ReliefQueue also demonstrates deterministic degraded operation, local queue recovery, dead-letter review and replay, role-scoped interfaces, public redaction, audit trails, and deployment through a single Python process serving the built React application and Product API.

## Tags

{', '.join(tags)}

## Public links

- GitHub: {project['repository_url']}
- Application: {project['public_application_url'] or 'ADD PUBLIC APPLICATION URL BEFORE SUBMISSION'}
"""


def _live_amd_proof_markdown(facts: dict[str, Any]) -> str:
    proof = facts.get("live_amd_public_proof") or {}
    status = proof.get("status")
    if status == "verified":
        return (
            f"- Status: verified on the submitted public URL\n"
            f"- Synthetic dossier: verified live; latency {proof.get('dossier_latency_ms')} ms; "
            f"provider calls {proof.get('dossier_provider_call_count')}\n"
            f"- Synthetic burst: {proof.get('burst_succeeded')}/{proof.get('burst_submitted')} verified live; "
            f"provider calls {proof.get('burst_provider_call_count')}\n"
            f"- Human review required: yes\n"
            f"- Claim boundary: {proof.get('claim_boundary')}"
        )
    if status == "verified_different_url":
        return "A live AMD proof exists, but it was produced for a different public URL and is not claimed for this submission URL."
    if status == "invalid_or_failed":
        return "No passing deployed live AMD proof is included. Use only the frozen historical campaign until the public live check passes."
    return "Not run yet. After deployment, run the explicit submission-live-amd-check; submission-pack itself makes zero provider calls."


def _amd_evidence_markdown(facts: dict[str, Any]) -> str:
    amd = facts["amd_evidence"]
    limitations = "\n".join(f"- {item}" for item in facts["limitations"])
    return f"""# AMD/vLLM evidence summary

## Verified historical campaign

- Provider: {amd['provider']}
- Accelerator: {amd['accelerator']}
- Runtime: {amd['runtime']}
- Served model: {amd['served_model']}
- Underlying model: {amd['underlying_model']}
- Campaign type: staged composite
- Cases resolved: {amd['cases_resolved']}/{amd['cases_evaluated']}
- Normalized JSON: {amd['normalized_json_rate_pct']}%
- Strict raw JSON: {amd['strict_raw_json_rate_pct']}%
- Nonce binding: {amd['nonce_binding_rate_pct']}%
- Source coverage: {amd['source_coverage_rate_pct']}%
- Average semantic completeness: {amd['semantic_completeness_avg_pct']}%
- Average completion throughput: {amd['completion_tokens_per_second_avg']} tokens/s
- Latency p50 / p95: {amd['latency_ms_p50']} ms / {amd['latency_ms_p95']} ms
- Provider errors: {amd['provider_error_count']}
- Direct-endpoint fallbacks: {amd['fallback_count']}
- Human review required: yes

## Required wording

Use: “ReliefQueue's staged AMD/vLLM evidence campaign resolved all 24 evaluation cases with 100% normalized JSON, nonce binding, and source coverage while retaining human review requirements.”

Do not claim that one uniform production prompt achieved 100% accuracy.

## Current deployed public proof

{_live_amd_proof_markdown(facts)}

## Limitations

{limitations}
"""


def _live_demo_instruction(facts: dict[str, Any]) -> str:
    proof = facts.get("live_amd_public_proof") or {}
    if proof.get("status") == "verified":
        return "The submitted URL has a passing synthetic public live proof, so run one bounded judge input and show nonce, provider source, tokens, latency, no fallback, and human-review status."
    return "Do not claim current live AMD availability unless the deployed endpoint is intentionally configured and the separate public live check passes."


def _demo_script(facts: dict[str, Any]) -> str:
    project = facts["project"]
    return f"""# Three-minute judge demo

Base URL: {project['public_application_url'] or 'ADD PUBLIC APPLICATION URL'}

## 0:00–0:25 — Problem and safety boundary

“Disaster reports arrive through fragmented channels and often conflict or repeat. ReliefQueue turns them into one reviewable operational queue. It can recommend, but it never auto-dispatches people or resources.”

## 0:25–0:55 — Command Center

Open `/dashboard?source=latest`. Show the operational overview, active cases, assignments, queue health, and role switcher. Emphasize meaningful visible actions rather than static mock cards.

## 0:55–1:25 — AMD Impact

Open `/dashboard/amd-impact`. Show the verified historical 24/24 AMD/vLLM campaign, throughput and latency, normalized versus strict raw JSON, and the human-review requirement. State that the campaign is a staged composite.

## 1:25–1:50 — Capability Map

Open `/dashboard/capability-map`. Point out the separation between historical evidence, current runtime configuration, and per-request live verification. {_live_demo_instruction(facts)}

## 1:50–2:20 — Field workflow

Switch to Field Coordinator and open `/field/my-work`, `/field/my-cases?worker_id=worker-alpha-boat`, and `/field/outbox`. Show offline-aware pending updates and the mobile-friendly role-scoped workflow.

## 2:20–2:40 — Local coordination

Switch to `/local-coordinator?source=latest`. Show affected-zone, relief-hub, reachability, blocked/safe-area, and operational-context controls.

## 2:40–3:00 — Close

“ReliefQueue combines deterministic degraded operation with review-required AI acceleration on AMD Instinct. It preserves evidence, exposes uncertainty, supports field teams offline, and keeps final operational authority with humans.”
"""


def _checklist(facts: dict[str, Any]) -> str:
    project = facts["project"]
    url_ready = bool(project["public_application_url"])
    url_box = "x" if url_ready else " "
    return f"""# Submission checklist

## Required assets

- [x] Public GitHub repository: {project['repository_url']}
- [{url_box}] Public application URL: {project['public_application_url'] or 'PENDING'}
- [ ] Cover image uploaded
- [ ] Demo video uploaded and playable without sign-in
- [ ] Slide deck exported to PDF and uploaded
- [x] Title, short description, long description, and tags generated in `01_submission_copy.md`
- [x] AMD evidence wording and limitations generated in `02_amd_evidence.md`
- [x] Three-minute demo script generated in `03_demo_script.md`

## Final manual review

- [ ] Open the public URL in a private/incognito window.
- [ ] Verify `/healthz` and the main dashboard load without authentication.
- [ ] Verify AMD Impact and Capability Map show historical/live/request separation.
- [ ] Verify Command Center, Field Coordinator, and Local Coordinator role switching.
- [ ] Confirm the video, slide PDF, cover image, repository, and application links all open.
- [ ] Do not claim a uniform 24-case production-prompt run.
- [ ] Do not claim the direct-endpoint evidence exercised application fallback.
- [ ] State that every AI advisory requires human review.
"""


def _route_checklist(facts: dict[str, Any]) -> str:
    base = facts["project"]["public_application_url"] or "<PUBLIC_URL>"
    lines = ["# Public demo route checklist", ""]
    for route in facts["demo_routes"]:
        lines.append(f"- [ ] `{base}{route}`")
    lines.extend(
        [
            "",
            "Run after deployment:",
            "",
            "```bash",
            "RELIEFQUEUE_PUBLIC_URL=https://your-app.example make submission-public-check",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_submission_pack(
    repo_root: Path | None = None,
    output_dir: Path | None = None,
    public_url: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root or ROOT).resolve()
    out = Path(output_dir or (root / DEFAULT_OUTPUT_DIR))
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    facts = build_submission_facts(root, public_url=public_url)
    campaign = load_amd_evidence_campaign(root / "fixtures" / "amd_evidence_campaign_v1.json")
    _, live_amd_report = _load_live_amd_public_proof(root, facts["project"]["public_application_url"])

    files: dict[str, str] = {
        "01_submission_copy.md": _submission_copy(facts),
        "02_amd_evidence.md": _amd_evidence_markdown(facts),
        "03_demo_script.md": _demo_script(facts),
        "04_submission_checklist.md": _checklist(facts),
        "06_public_route_checklist.md": _route_checklist(facts),
    }
    for name, text in files.items():
        (out / name).write_text(text.rstrip() + "\n", encoding="utf-8")

    (out / "05_submission_facts.json").write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "07_amd_evidence_campaign_v1.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    artifact_names = [
        "01_submission_copy.md",
        "02_amd_evidence.md",
        "03_demo_script.md",
        "04_submission_checklist.md",
        "05_submission_facts.json",
        "06_public_route_checklist.md",
        "07_amd_evidence_campaign_v1.json",
    ]
    if live_amd_report is not None and facts["live_amd_public_proof"]["status"] == "verified":
        live_name = "08_live_amd_public_proof.json"
        (out / live_name).write_text(json.dumps(live_amd_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifact_names.append(live_name)
    manifest = {
        "contract": "reliefqueue-submission-pack-manifest/v1",
        "generated_at_utc": facts["generated_at_utc"],
        "status": "PASS",
        "artifact_count": len(artifact_names),
        "artifacts": [
            {
                "name": name,
                "size_bytes": (out / name).stat().st_size,
            }
            for name in artifact_names
        ],
        "archive": ARCHIVE_NAME,
        "public_url_provided": bool(facts["project"]["public_application_url"]),
        "provider_calls": 0,
    }
    (out / "00_submission_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    archive_path = out / ARCHIVE_NAME
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        for name in ["00_submission_manifest.json", *artifact_names]:
            archive.add(out / name, arcname=str(Path("reliefqueue_submission_pack") / name))

    manifest["archive_size_bytes"] = archive_path.stat().st_size
    (out / "00_submission_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "PASS",
        "output_dir": str(out),
        "archive_path": str(archive_path),
        "facts": facts,
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--public-url", default=None)
    args = parser.parse_args(argv)
    result = generate_submission_pack(args.repo_root, args.output_dir, args.public_url)
    print("SUBMISSION_PACK=PASS")
    print(f"SUBMISSION_PACK_DIR={result['output_dir']}")
    print(f"SUBMISSION_PACK_ARCHIVE={result['archive_path']}")
    print(f"PUBLIC_URL_PROVIDED={str(bool(result['facts']['project']['public_application_url'])).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

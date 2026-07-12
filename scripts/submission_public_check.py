#!/usr/bin/env python3
"""Check a deployed ReliefQueue URL without calling an AI provider."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_base_url(value: str) -> str:
    text = value.strip().rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("public URL must be an absolute http(s) URL")
    return text


def request(base: str, path: str, expect_json: bool = False) -> dict[str, object]:
    url = urljoin(base + "/", path.lstrip("/"))
    req = urllib.request.Request(url, headers={"User-Agent": "ReliefQueueSubmissionCheck/1.0"})
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=context) as response:
            body = response.read(2_000_000)
            result: dict[str, object] = {
                "path": path,
                "url": url,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "body_bytes": len(body),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(200_000)
        return {
            "path": path,
            "url": url,
            "status": exc.code,
            "content_type": exc.headers.get("content-type", ""),
            "body_bytes": len(body),
            "error": str(exc),
        }
    if expect_json:
        result["json"] = json.loads(body.decode("utf-8"))
    else:
        result["contains_root"] = b'<div id="root">' in body
    return result


def run_check(base_url: str, output_dir: Path) -> dict[str, object]:
    base = normalize_base_url(base_url)
    checks: list[dict[str, object]] = []
    failures: list[str] = []

    health = request(base, "/api/health", expect_json=True)
    checks.append(health)
    if health.get("status") != 200 or health.get("json") != {"status": "ok"}:
        failures.append("/api/health did not return the expected status")

    evidence = request(base, "/api/product/amd/evidence", expect_json=True)
    checks.append(evidence)
    historical = ((evidence.get("json") or {}).get("historical_evidence") or {}) if isinstance(evidence.get("json"), dict) else {}
    quality = historical.get("final_resolved_quality") or {}
    if evidence.get("status") != 200 or quality.get("cases_resolved") != 24:
        failures.append("AMD evidence endpoint did not expose the frozen 24-case campaign")

    capability = request(base, "/api/product/amd/capability", expect_json=True)
    checks.append(capability)
    payload = capability.get("json") if isinstance(capability.get("json"), dict) else {}
    if capability.get("status") != 200 or not all(key in payload for key in ("historical_evidence", "live_runtime", "current_request")):
        failures.append("AMD capability endpoint did not expose all three evidence planes")

    routes = [
        "/",
        "/dashboard?source=latest",
        "/dashboard/amd-impact",
        "/dashboard/capability-map",
        "/field/my-work",
        "/field/my-cases?worker_id=worker-alpha-boat",
        "/field/outbox",
        "/local-coordinator?source=latest",
    ]
    for route in routes:
        result = request(base, route)
        checks.append(result)
        if result.get("status") != 200 or result.get("contains_root") is not True:
            failures.append(f"SPA route failed: {route}")

    unknown_asset = request(base, "/submission-check-does-not-exist.js")
    checks.append(unknown_asset)
    if unknown_asset.get("status") != 404:
        failures.append("unknown asset did not return 404")

    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "contract": "reliefqueue-submission-public-check/v1",
        "generated_at_utc": utc_now(),
        "base_url": base,
        "status": "PASS" if not failures else "FAIL",
        "provider_calls": 0,
        "checks": checks,
        "failures": failures,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SUBMISSION_PUBLIC_CHECK={report['status']}")
    print(f"SUBMISSION_PUBLIC_CHECK_REPORT={report_path}")
    if failures:
        for failure in failures:
            print(f"- {failure}")
        return report
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public_url")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/submission-public-check/latest"))
    args = parser.parse_args(argv)
    try:
        report = run_check(args.public_url, args.output_dir)
    except Exception as exc:
        print(f"SUBMISSION_PUBLIC_CHECK=FAIL error={exc}", file=sys.stderr)
        return 2
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

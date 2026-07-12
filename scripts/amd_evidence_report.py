#!/usr/bin/env python3
"""Validate and print the frozen ReliefQueue AMD evidence campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reliefqueue.amd_evidence import load_amd_evidence_campaign


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    campaign = load_amd_evidence_campaign(args.path)
    if args.json:
        print(json.dumps(campaign, indent=2, ensure_ascii=False))
        return 0
    quality = campaign["final_resolved_quality"]
    deployment = campaign["deployment"]
    print("AMD_EVIDENCE_VALIDATION=PASS")
    print(f"CAMPAIGN_ID={campaign['campaign_id']}")
    print(f"CAMPAIGN_TYPE={campaign['campaign_type']}")
    print(f"CASES_RESOLVED={quality['cases_resolved']}/{quality['cases_evaluated']}")
    print(f"SOURCE_COVERAGE_PCT={quality['source_coverage_rate_pct']}")
    print(f"NONCE_BINDING_PCT={quality['nonce_binding_rate_pct']}")
    print(f"NORMALIZED_JSON_PCT={quality['normalized_json_rate_pct']}")
    print(f"STRICT_RAW_JSON_PCT={quality['strict_raw_json_rate_pct']}")
    print(f"PROVIDER={deployment['provider']}")
    print(f"ACCELERATOR={deployment['accelerator']}")
    print(f"RUNTIME={deployment['runtime']}")
    print(f"SERVED_MODEL={deployment['served_model']}")
    print("UNIFORM_PROMPT_RUN=false")
    print("APPLICATION_FALLBACK_EXERCISED=false")
    print("HUMAN_REVIEW_REQUIRED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import unittest

from reliefqueue.product_api import _route


class TestAmdEvidenceApi(unittest.TestCase):
    def test_historical_evidence_route(self) -> None:
        payload = _route("GET", "/api/product/amd/evidence", {})
        self.assertEqual(payload["status"], "ok")
        campaign = payload["historical_evidence"]
        self.assertEqual(campaign["campaign_type"], "staged_composite")
        self.assertEqual(campaign["final_resolved_quality"]["cases_resolved"], 24)
        self.assertFalse(payload["truthfulness"]["current_live_status_inferred"])

    def test_capability_route_separates_evidence_runtime_and_request(self) -> None:
        payload = _route("GET", "/api/product/amd/capability", {})
        self.assertEqual(payload["status"], "ok")
        self.assertIn("historical_evidence", payload)
        self.assertIn("live_runtime", payload)
        self.assertIn("current_request", payload)
        self.assertFalse(payload["current_request"]["attempted"])
        self.assertFalse(payload["live_runtime"]["live_request_verified"])


if __name__ == "__main__":
    unittest.main()

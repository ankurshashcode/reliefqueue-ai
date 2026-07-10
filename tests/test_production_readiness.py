import json
import tempfile
import unittest
from pathlib import Path

from reliefqueue import product_api
from reliefqueue.production_readiness import OBJECTIVE_IDS, build_status, write_status


class ProductionReadinessTests(unittest.TestCase):
    def test_report_contains_all_required_objectives_and_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "reports" / "latest"
            path = write_status(root, report_dir)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path.name, "remaining_objectives_status.json")
        self.assertEqual({obj["id"] for obj in payload["objectives"]}, set(OBJECTIVE_IDS))
        for obj in payload["objectives"]:
            self.assertIn(obj["status"], {"pass", "degraded", "skip", "fail"})
            self.assertTrue(obj["operator_surface"])
            self.assertTrue(obj["runtime_evidence"])
            self.assertTrue(obj["tests"])
            self.assertTrue(obj["next_operator_action"])

    def test_local_must_pass_objectives_are_pass(self) -> None:
        payload = build_status(Path.cwd(), Path.cwd() / "reports" / "latest")
        by_id = {obj["id"]: obj for obj in payload["objectives"]}
        for objective_id in [
            "evidence_upload",
            "offline_field_queue",
            "conflict_replay",
            "auth_role_identity",
            "worker_provider_monitoring",
        ]:
            self.assertEqual(by_id[objective_id]["status"], "pass")

    def test_map_data_exposes_offline_panel_requirements(self) -> None:
        payload = product_api.offline_map_data()
        self.assertEqual(payload["mode"], "local/mock")
        self.assertTrue(payload["affected_zone"]["bounds"])
        self.assertTrue(payload["hub"]["name"])
        self.assertGreater(payload["reachable_radius_km"], 0)
        self.assertTrue(payload["blocked_areas"])
        self.assertTrue(payload["safe_areas"])
        self.assertIn("geocoding", payload["provider_boundary"])

    def test_production_config_is_sanitized(self) -> None:
        payload = product_api.production_config_status()
        rendered = json.dumps(payload)
        self.assertIn("public_api_origin", payload)
        self.assertNotIn("TOKEN=", rendered)
        self.assertNotIn("API_KEY=", rendered)


if __name__ == "__main__":
    unittest.main()

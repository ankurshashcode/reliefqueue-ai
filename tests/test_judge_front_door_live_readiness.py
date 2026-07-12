from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class JudgeFrontDoorLiveReadinessTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_local_vite_proxy_supports_all_repository_launchers(self):
        text = self.read("dashboard/vite.config.ts")
        self.assertIn("RELIEFQUEUE_API_PROXY_TARGET", text)
        self.assertIn("RELIEFQUEUE_PRODUCT_API_TARGET", text)
        self.assertIn("http://127.0.0.1:5001", text)
        self.assertIn("'/api'", text)
        self.assertIn("'/healthz'", text)

    def test_front_door_fetches_use_readable_json_boundary(self):
        helper = self.read("dashboard/src/commandStudio/lib/httpJson.ts")
        self.assertIn("readJsonResponse", helper)
        self.assertIn("non-JSON", helper)
        for relative in (
            "dashboard/src/commandStudio/lib/amdEvidence.ts",
            "dashboard/src/commandStudio/views/AIControl.tsx",
            "dashboard/src/commandStudio/views/AmdImpact.tsx",
            "dashboard/src/commandStudio/views/CapabilityMap.tsx",
            "dashboard/src/commandStudio/views/IntakeFusion.tsx",
        ):
            self.assertIn("readJsonResponse", self.read(relative), relative)

    def test_connection_buttons_send_valid_consented_requests(self):
        for relative in (
            "dashboard/src/commandStudio/views/AIControl.tsx",
            "dashboard/src/commandStudio/views/CapabilityMap.tsx",
        ):
            text = self.read(relative)
            self.assertIn("synthetic_confirmed: true", text, relative)
            self.assertIn("workload_mode: 'single'", text, relative)

    def test_overview_evidence_cards_have_real_destinations(self):
        text = self.read("dashboard/src/commandStudio/views/Overview.tsx")
        self.assertIn('data-testid="overview-missing-info-card"', text)
        self.assertIn("handleMetricClick('intake', 'Missing-info prompts')", text)
        self.assertIn('data-testid="overview-malformed-output-card"', text)
        self.assertIn("handleMetricClick('quality', 'Malformed output review')", text)
        self.assertIn('role="button"', text)
        self.assertIn("onKeyDown", text)

    def test_assignment_advisory_is_truthful_and_routes_live_testing(self):
        drawer = self.read("dashboard/src/commandStudio/components/AIAdvisoryDrawer.tsx")
        assignments = self.read("dashboard/src/commandStudio/views/Assignments.tsx")
        self.assertIn("Open Live AMD Test", drawer)
        self.assertIn("navigate('amd')", drawer)
        self.assertIn("Deterministic Local Advisory", drawer)
        self.assertIn("providerStatus: 'Not contacted'", drawer)
        self.assertIn("latency: 'Local · no provider call'", drawer)
        self.assertIn('data-testid="assignment-advisory-provider"', drawer)
        self.assertIn('data-testid="assignment-advisory-latency"', drawer)
        self.assertNotIn("Connected (vLLM)", drawer)
        self.assertNotIn("'450ms'", drawer)
        self.assertNotIn("providerStatus: response.status || 'completed'", assignments)
        self.assertIn("providerStatus: 'Not contacted'", assignments)

    def test_real_browser_front_door_check_is_permanently_available(self):
        package = self.read("dashboard/package.json")
        script = self.read("dashboard/scripts/judgeFrontDoorCheck.mjs")
        self.assertIn('"judge-front-door-check"', package)
        self.assertIn("overview-missing-info-card", script)
        self.assertIn("overview-malformed-output-card", script)
        self.assertIn("assignment-advisory-provider", script)
        self.assertIn("Evidence API unavailable", script)


    def test_vite_has_one_canonical_config_and_launcher_uses_it(self):
        self.assertTrue((ROOT / "dashboard/vite.config.ts").is_file())
        self.assertFalse(
            (ROOT / "dashboard/vite.config.js").exists(),
            "stale vite.config.js would shadow the canonical TypeScript config",
        )
        launcher = self.read("dashboard/scripts/devServer.mjs")
        self.assertIn("hasExplicitConfig", launcher)
        self.assertIn("'--config'", launcher)
        self.assertIn("vite.config.ts", launcher)

    def test_live_amd_drawer_uses_registered_view_key(self):
        drawer = self.read("dashboard/src/commandStudio/components/AIAdvisoryDrawer.tsx")
        routes = self.read("dashboard/src/commandStudio/types.ts")
        self.assertIn("navigate('amd')", drawer)
        self.assertNotIn("navigate('amd-impact')", drawer)
        self.assertIn("amd: '/dashboard/amd-impact'", routes)

if __name__ == "__main__":
    unittest.main()

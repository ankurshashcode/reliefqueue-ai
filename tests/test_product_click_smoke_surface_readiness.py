from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestProductClickSmokeSurfaceReadiness(unittest.TestCase):
    def test_workspace_switcher_exposes_current_role_marker(self):
        source = (ROOT / "dashboard/src/components/ProductRoleSwitcher.tsx").read_text(encoding="utf-8")
        self.assertIn('data-testid="workspace-current-role"', source)
        self.assertIn('data-current-role={currentRole}', source)

    def test_click_smoke_uses_semantic_surface_readiness(self):
        source = (ROOT / "dashboard/scripts/productClickSmoke.mjs").read_text(encoding="utf-8")
        self.assertIn("const surfaceReadySelectors = {", source)
        self.assertIn('data-current-role="command"', source)
        self.assertIn('data-current-role="field"', source)
        self.assertIn('data-current-role="local"', source)
        self.assertIn("waitForSurfaceReady", source)
        self.assertIn('waitUntil: "domcontentloaded"', source)
        self.assertNotIn('page.getByText(title, { exact: false }).first()', source)

    def test_readiness_checks_loading_and_runtime_error_surfaces(self):
        source = (ROOT / "dashboard/scripts/productClickSmoke.mjs").read_text(encoding="utf-8")
        self.assertIn('data-testid="native-runtime-error"', source)
        self.assertIn('data-testid="native-loading-shell"', source)
        self.assertIn('state: "hidden"', source)
        self.assertIn('state: "visible"', source)


if __name__ == "__main__":
    unittest.main()

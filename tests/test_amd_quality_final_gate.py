from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "amd_quality_live_validation.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "reliefqueue_amd_quality_live_validation",
        VALIDATOR,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load AMD quality live validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAmdFinalQualityGatePart8(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = _load_validator()

    def test_conflict_observation_count_accepts_one_direct_contradiction(self) -> None:
        record = {
            "contradictions": [{"source_ids": ["REPORT-006", "REPORT-007"]}],
            "superseded_updates": [{"older_source_id": "REPORT-005"}],
            "duplicate_clusters": [{"source_ids": ["REPORT-001", "REPORT-003"]}],
            "unverified_claims": [],
        }
        self.assertEqual(
            self.validator._conflict_resolution_observation_count(record),
            3,
        )


    def test_final_runner_allows_one_targeted_incident_supplement(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn(
            "dossier_calls in {1, 2, 3}",
            source,
        )
        self.assertIn(
            "dossier provider-call count must be 1, 2 or 3",
            source,
        )
        self.assertIn(
            "max_live_provider_calls > 8",
            source,
        )

    def test_final_runner_does_not_restore_three_direct_contradiction_gate(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertNotIn("fewer than three contradictions", source)
        self.assertIn("fewer than one direct contradiction", source)
        self.assertIn(
            "fewer than three aggregate conflict-resolution observations",
            source,
        )


class TestAmdFinalVisualFreeze(unittest.TestCase):
    def setUp(self) -> None:
        self.browser_source = (
            ROOT / "dashboard" / "scripts" / "amdQualityPlaywright.mjs"
        ).read_text(encoding="utf-8")

    def test_capability_map_capture_waits_for_loaded_screen(self) -> None:
        source = self.browser_source
        wait_index = source.index("Capability Map & Readiness")
        capture_index = source.index("filename: 'capability-map.png'")
        self.assertLess(wait_index, capture_index)
        self.assertIn("native-loading-shell", source)
        self.assertIn("lazy_loading_shell_absent: true", source)
        self.assertIn("'Loading Capability Map'", source)
        self.assertIn("'Live Deployment Status'", source)
        self.assertIn("'AMD Developer Cloud'", source)

    def test_all_five_screenshots_receive_automated_review(self) -> None:
        source = self.browser_source
        self.assertIn("const expectedScreenshotCount = 5", source)
        self.assertIn("screenshots_captured: screenshotReviews.length", source)
        self.assertIn("screenshots_reviewed: reviewedScreenshotCount", source)
        self.assertIn("human_screenshots_reviewed: 0", source)
        self.assertIn("screenshot-review.json", source)
        self.assertNotIn("screenshots_captured: 4", source)
        self.assertNotIn("\n    screenshots_reviewed: 0,", source)

    def test_screenshot_review_requires_visible_state_and_png_integrity(self) -> None:
        source = self.browser_source
        self.assertIn("captureReviewedScreenshot", source)
        self.assertIn("png_signature_valid", source)
        self.assertIn("missingRequiredText", source)
        self.assertIn("presentForbiddenText", source)
        self.assertIn("screenshotReviewFailed", source)


class TestAmdFinalNavigationAndFramingPart9B(unittest.TestCase):
    def setUp(self) -> None:
        self.browser_source = (
            ROOT / "dashboard" / "scripts" / "amdQualityPlaywright.mjs"
        ).read_text(encoding="utf-8")
        self.sidebar_source = (
            ROOT
            / "dashboard"
            / "src"
            / "commandStudio"
            / "components"
            / "Sidebar.tsx"
        ).read_text(encoding="utf-8")

    def test_amd_navigation_is_prioritized_at_sidebar_top(self) -> None:
        source = self.sidebar_source
        self.assertIn(
            "['amd', 'capabilities', 'aicontrol', 'intake']",
            source,
        )
        self.assertIn("AMD / vLLM Demo", source)
        self.assertIn('data-testid="sidebar-priority-group"', source)
        self.assertIn("amdPriorityNavigation.map", source)
        self.assertLess(
            source.index("amdPriorityNavigation.map"),
            source.index("operationsNavigation.map"),
        )

    def test_desktop_sidebar_is_narrower_and_labels_must_fit(self) -> None:
        sidebar = self.sidebar_source
        browser = self.browser_source
        self.assertIn("w-64 md:w-56", sidebar)
        self.assertNotIn(
            "z-50 w-64 bg-slate-900",
            sidebar,
        )
        self.assertIn("all_navigation_labels_fit", browser)
        self.assertIn("button.scrollWidth <= button.clientWidth + 1", browser)
        self.assertIn("sidebar_width_px", browser)

    def test_dossier_and_burst_use_explicit_nested_scroll_alignment(self) -> None:
        source = self.browser_source
        self.assertIn(
            "focusLocator: page.getByTestId('amd-complex-structured-result')",
            source,
        )
        self.assertIn(
            "focusLocator: page.getByTestId('amd-burst-result')",
            source,
        )
        self.assertIn(
            "current.scrollHeight > current.clientHeight + 1",
            source,
        )
        self.assertIn("container.scrollTop = Math.max", source)
        self.assertIn("focus_visible_pixels", source)
        self.assertIn(
            "explicit-scrollable-ancestor-alignment",
            source,
        )
        self.assertNotIn(
            "await focusLocator.scrollIntoViewIfNeeded()",
            source,
        )
        self.assertNotIn("block: 'center'", source)

    def test_navigation_and_result_geometry_are_written_to_evidence(self) -> None:
        source = self.browser_source
        self.assertIn("navigation-evidence.json", source)
        self.assertIn("priority_items_initially_visible", source)
        self.assertIn("focus_scroll_container", source)
        self.assertIn("geometry=${JSON.stringify(focusGeometry)}", source)

    def test_sidebar_locator_uses_semantics_then_geometry(self) -> None:
        source = self.browser_source
        self.assertIn(
            ".filter({ hasText: 'AMD / vLLM Demo' })",
            source,
        )
        self.assertIn(
            "state: 'attached'",
            source,
        )
        self.assertIn(
            "sidebar_selector_strategy",
            source,
        )
        self.assertIn(
            "sidebar_visible_in_viewport",
            source,
        )
        self.assertIn(
            "Command sidebar is not visibly rendered in the desktop viewport",
            source,
        )
        self.assertNotIn(
            "const sidebar = page.getByTestId('command-sidebar');",
            source,
        )


    def test_map_icon_cannot_shadow_javascript_map_constructor(self) -> None:
        source = self.sidebar_source
        self.assertIn("Map as MapIcon", source)
        self.assertIn("map: MapIcon", source)
        self.assertIn("new globalThis.Map(", source)
        self.assertNotIn("\n  Map,\n", source)
        self.assertNotIn("const navigationById = new Map(", source)


if __name__ == "__main__":
    unittest.main()

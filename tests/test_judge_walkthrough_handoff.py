from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class JudgeWalkthroughHandoffTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_step_one_hands_exact_report_to_intake(self):
        modal = self.read("dashboard/src/commandStudio/components/JudgeWalkthroughModal.tsx")
        intake = self.read("dashboard/src/commandStudio/views/IntakeFusion.tsx")
        self.assertIn("Synthetic Intake Report", modal)
        self.assertIn("reliefqueue.walkthrough.intake.v1", modal)
        self.assertIn("Open this report in AI Intake", modal)
        self.assertIn("reliefqueue.walkthrough.intake.v1", intake)
        self.assertIn('data-testid="walkthrough-intake-handoff"', intake)

    def test_step_two_hands_rq1042_advisory_to_assignments(self):
        modal = self.read("dashboard/src/commandStudio/components/JudgeWalkthroughModal.tsx")
        assignments = self.read("dashboard/src/commandStudio/views/Assignments.tsx")
        self.assertIn("reliefqueue.walkthrough.assignment.v1", modal)
        self.assertIn("Open RQ-1042 advisory in Assignments", modal)
        self.assertIn("reliefqueue.walkthrough.assignment.v1", assignments)
        self.assertIn("setAdvisoryOpen(true)", assignments)
        self.assertIn("Run deterministic advisory", assignments)
        self.assertNotIn(">Request AI advisory<", assignments)

    def test_dossier_and_burst_are_editable_and_handoff_to_correct_tabs(self):
        modal = self.read("dashboard/src/commandStudio/components/JudgeWalkthroughModal.tsx")
        impact = self.read("dashboard/src/commandStudio/views/AmdImpact.tsx")
        self.assertIn('data-testid="walkthrough-dossier-input"', modal)
        self.assertIn('data-testid="walkthrough-burst-input"', modal)
        self.assertIn("Walkthrough burst parser", modal)
        self.assertIn("reliefqueue.walkthrough.amd.v1", modal)
        self.assertIn("reliefqueue.walkthrough.amd.v1", impact)
        self.assertIn("setActiveTab('dossier')", impact)
        self.assertIn("setActiveTab('burst')", impact)
        self.assertIn('data-testid="walkthrough-amd-handoff"', impact)

    def test_field_consumption_opens_real_field_task(self):
        modal = self.read("dashboard/src/commandStudio/components/JudgeWalkthroughModal.tsx")
        self.assertIn("window.location.assign('/field/cases/RQ-1042')", modal)
        self.assertIn("Open Field Coordinator Task RQ-1042", modal)
        self.assertNotIn("onClick={() => navigateStep('sync')}", modal)

    def test_browser_contract_is_available(self):
        package = self.read("dashboard/package.json")
        script = self.read("dashboard/scripts/judgeWalkthroughCheck.mjs")
        self.assertIn("judge-walkthrough-check", package)
        self.assertIn("JUDGE_WALKTHROUGH_CHECK=PASS", script)
        self.assertIn("provider_calls: 0", script)


    def test_modal_does_not_conditionally_skip_hooks(self):
        modal = self.read(
            "dashboard/src/commandStudio/components/"
            "JudgeWalkthroughModal.tsx"
        )
        closed_return = modal.index("if (!isOpen) return null;")
        last_effect = modal.rfind("useEffect(")
        self.assertGreater(
            closed_return,
            last_effect,
            "all React hooks must execute before the closed-modal return",
        )

if __name__ == "__main__":
    unittest.main()

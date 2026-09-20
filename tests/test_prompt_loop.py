import unittest
from worker.prompt_loop import (
    PromptLoopEngine,
    ComplianceEvaluator,
    MockLLMProvider,
    PromptLoopConfig,
    FORBIDDEN_ACCUSATORY_PATTERNS,
)


class PromptLoopTests(unittest.TestCase):

    def setUp(self):
        self.context = {
            "consent": {"processes": True, "windows": True, "gaze": False, "audio_devices": True},
            "signals": [
                {
                    "detector": "ProcessDetector",
                    "title": "Review keyword in process name",
                    "explanation": "Active process matches review pattern",
                    "confidence": 0.6,
                }
            ],
            "notes": ["Dual monitor setup for coding exercise"],
        }

    def test_single_turn_success(self):
        compliant_draft = (
            "The session monitored process and window activities. Gaze tracking was disabled by consent. "
            "One process matching review keywords was observed. These technical observations require human review "
            "and this tool does not determine candidate eligibility or intent."
        )
        provider = MockLLMProvider([compliant_draft])
        engine = PromptLoopEngine(provider=provider)

        result = engine.run(self.context)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["iterations"], 1)
        self.assertEqual(result["summary"], compliant_draft)
        self.assertTrue(result["score"] >= 0.8)
        self.assertEqual(len(result["history"]), 1)
        self.assertTrue(result["history"][0]["evaluation"]["passed"])

    def test_two_turn_correction_loop(self):
        # Turn 1: Accusatory and missing disclaimer -> should fail evaluation
        turn_1_bad = "The candidate cheated by running an unauthorized process in the background."

        # Turn 2: Cleaned up based on evaluator feedback -> should pass
        turn_2_good = (
            "Process activity detected one application matching designated review patterns. "
            "Gaze monitoring was disabled during this session. This report provides technical context for human review "
            "and does not determine whether the candidate violated guidelines."
        )

        provider = MockLLMProvider([turn_1_bad, turn_2_good])
        engine = PromptLoopEngine(provider=provider)

        result = engine.run(self.context)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["iterations"], 2)
        self.assertEqual(result["summary"], turn_2_good)

        # Verify history captured the loop feedback
        self.assertEqual(len(result["history"]), 2)
        self.assertFalse(result["history"][0]["evaluation"]["passed"])
        self.assertTrue(any("cheat" in v.lower() for v in result["history"][0]["evaluation"]["violations"]))
        self.assertTrue(result["history"][1]["evaluation"]["passed"])

    def test_max_iterations_fallback(self):
        # All iterations fail
        bad_drafts = [
            "Candidate is definitely guilty.",
            "Still cheated on this exam.",
            "Untrustworthy behavior throughout.",
        ]
        provider = MockLLMProvider(bad_drafts)
        config = PromptLoopConfig(max_iterations=3)
        engine = PromptLoopEngine(provider=provider, config=config)

        result = engine.run(self.context)

        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["iterations"], 3)
        self.assertIn("deterministic fallback", result["summary"])
        self.assertIn("human review is required", result["summary"])
        self.assertEqual(len(result["history"]), 3)

    def test_evaluator_catches_all_forbidden_terms(self):
        evaluator = ComplianceEvaluator()
        for word in ["cheated", "cheating", "dishonest", "fraud", "guilty", "malicious", "untrustworthy"]:
            text = f"The candidate showed {word} actions during the session. Human review does not determine anything."
            res = evaluator.evaluate(text, self.context)
            self.assertFalse(res.passed, f"Evaluator should have flagged '{word}'")
            self.assertTrue(len(res.violations) > 0)


if __name__ == "__main__":
    unittest.main()

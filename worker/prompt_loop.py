"""Loop Engineering / Evaluator-Optimizer Prompting Loop for Interview Integrity Monitor.

Implements an autonomous outer control loop:
  1. Generator Prompt: Produces an objective, factual technical summary of session telemetry.
  2. Evaluator Prompt & Deterministic Verifier: Audits the draft against strict proctoring compliance.
  3. Feedback Injection: Converts critique into structured instructions for the next iteration.
  4. Stop Rules: Halts on passing rubric score, policy compliance, or max iteration limit.
"""
import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .engine import SCOPES


FORBIDDEN_ACCUSATORY_PATTERNS = [
    r"\bcheat(ed|ing|s)?\b",
    r"\bdishonest(y)?\b",
    r"\bfraud(ulent)?\b",
    r"\bguilty\b",
    r"\bmalicious\b",
    r"\bdisqualified\b",
    r"\buntrustworthy\b",
]

REQUIRED_COMPLIANCE_DISCLAIMERS = [
    "does not determine",
    "human review",
]


@dataclass
class EvaluationResult:
    passed: bool
    score: float
    critique: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "critique": self.critique,
            "violations": self.violations,
        }


@dataclass
class PromptLoopConfig:
    max_iterations: int = 3
    passing_score: float = 0.85

    def __post_init__(self):
        if not 1 <= self.max_iterations <= 10:
            raise ValueError("max_iterations must be between 1 and 10")
        if not 0 <= self.passing_score <= 1:
            raise ValueError("passing_score must be between 0 and 1")


class LLMProvider:
    """Abstract base class for LLM backends."""
    def complete(self, system_prompt: str, prompt: str) -> str:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for offline testing and verification."""
    def __init__(self, script: Optional[List[str]] = None):
        self.script = list(script) if script else []
        self.calls = []

    def complete(self, system_prompt: str, prompt: str) -> str:
        self.calls.append({"system": system_prompt, "user": prompt})
        if self.script:
            return self.script.pop(0)
        return "The session concluded with recorded technical observations. Human review is recommended."


class ComplianceEvaluator:
    """Hybrid evaluator: runs deterministic checks and rubric evaluations."""

    def evaluate(self, draft: str, session_context: Dict[str, Any]) -> EvaluationResult:
        violations = []
        critique = []
        score = 1.0

        lower_draft = draft.lower()

        # Check 1: Anti-Accusation Policy
        for pattern in FORBIDDEN_ACCUSATORY_PATTERNS:
            matches = re.findall(pattern, lower_draft, flags=re.IGNORECASE)
            if matches:
                violations.append(
                    f"Forbidden accusatory terminology detected matching '{pattern}'. The tool must never label a candidate as cheating or dishonest."
                )
                critique.append("Remove judgmental words. Describe observed technical events objectively without declaring intent.")
                score -= 0.4

        # Check 2: Mandatory Disclaimer / Human-in-the-loop acknowledgement
        has_disclaimer = any(phrase in lower_draft for phrase in REQUIRED_COMPLIANCE_DISCLAIMERS)
        if not has_disclaimer:
            violations.append("Missing mandatory reminder that this system requires human review and does not determine cheating.")
            critique.append("Explicitly state that technical observations require human context and do not determine candidate qualification.")
            score -= 0.3

        # Check 3: Acknowledgment of Disabled Scopes or Missing Coverage
        disabled_scopes = [
            scope for scope in SCOPES
            if session_context.get("consent", {}).get(scope) is not True
        ]
        if disabled_scopes and not any(s in lower_draft for s in ("disabled", "not enabled", "omitted", "missing")):
            critique.append(f"Acknowledge that certain scopes were disabled by candidate consent: {', '.join(disabled_scopes)}.")
            score -= 0.15

        # Check 4: Length & Conciseness
        word_count = len(draft.split())
        if word_count < 20:
            critique.append("The summary is too brief. Provide meaningful context on observed signals and active detectors.")
            score -= 0.2
        elif word_count > 300:
            critique.append("The summary exceeds 300 words. Condense to an executive, high-level technical synthesis.")
            score -= 0.1

        score = max(0.0, min(1.0, round(score, 2)))
        passed = (len(violations) == 0) and (score >= 0.8)

        return EvaluationResult(passed=passed, score=score, critique=critique, violations=violations)


class PromptLoopEngine:
    """Orchestrates the Generator -> Evaluator -> Feedback loop."""

    def __init__(self, provider: Optional[LLMProvider] = None, evaluator: Optional[ComplianceEvaluator] = None, config: Optional[PromptLoopConfig] = None):
        self.provider = provider
        self.evaluator = evaluator or ComplianceEvaluator()
        self.config = config or PromptLoopConfig()

    def build_generator_prompt(self, session_context: Dict[str, Any], feedback_history: List[List[str]]) -> str:
        signals = session_context.get("signals", [])
        scopes = session_context.get("consent", {})
        candidate_notes = session_context.get("notes", [])

        prompt_lines = [
            "TASK: Generate an objective, neutral executive summary of the following interview session telemetry.",
            "",
            "### SESSION CONTEXT ###",
            f"- Monitoring Scopes: {json.dumps(scopes)}",
            f"- Observed Signals Count: {len(signals)}",
        ]

        if signals:
            prompt_lines.append("- Recorded Signals:")
            for s in signals:
                prompt_lines.append(f"  * [{s.get('detector')}] {s.get('title')}: {s.get('explanation')} (Confidence: {s.get('confidence')})")
        else:
            prompt_lines.append("- Recorded Signals: None")

        if candidate_notes:
            prompt_lines.append(f"- Candidate Disclosed Notes: {', '.join(candidate_notes)}")

        prompt_lines.extend([
            "",
            "### CORE REQUIREMENTS ###",
            "1. Neutral, factual tone only. NEVER use words like 'cheated', 'dishonest', or 'guilty'.",
            "2. State that observations require human review and that this tool does not make hiring decisions.",
            "3. Note any limitations or disabled scopes accurately.",
            "4. Keep response under 150 words.",
        ])

        if feedback_history:
            prompt_lines.extend([
                "",
                "### CRITIQUE FROM PREVIOUS ITERATION(S) - MUST ADDRESS ###"
            ])
            for idx, critiques in enumerate(feedback_history, 1):
                prompt_lines.append(f"Iteration {idx} feedback:")
                for c in critiques:
                    prompt_lines.append(f"  - {c}")
            prompt_lines.append("\nPlease revise the summary to correct every item noted above.")

        return "\n".join(prompt_lines)

    def run(self, session_context: Dict[str, Any]) -> Dict[str, Any]:
        """Runs the loop until convergence or max iterations reached."""
        if self.provider is None:
            summary = self.fallback_deterministic(session_context)
            evaluation = self.evaluator.evaluate(summary, session_context)
            return {"status": "deterministic", "method": "deterministic", "iterations": 0,
                    "summary": summary, "score": evaluation.score, "history": []}
        feedback_history = []
        iteration_records = []

        system_prompt = (
            "You are an expert, ethical AI proctoring auditor. You provide objective, "
            "factual technical summaries of interview telemetry without making moral or cheating determinations."
        )

        for iteration in range(1, self.config.max_iterations + 1):
            prompt = self.build_generator_prompt(session_context, feedback_history)
            draft = self.provider.complete(system_prompt, prompt).strip()

            eval_res = self.evaluator.evaluate(draft, session_context)
            iteration_records.append({
                "iteration": iteration,
                "draft": draft,
                "evaluation": eval_res.to_dict(),
            })

            accepted = eval_res.passed and not eval_res.violations and eval_res.score >= self.config.passing_score
            iteration_records[-1]["accepted"] = accepted
            if accepted:
                return {
                    "status": "success",
                    "method": "configured_provider",
                    "iterations": iteration,
                    "summary": draft,
                    "score": eval_res.score,
                    "history": iteration_records,
                }

            # Prepare feedback for the next iteration
            combined_feedback = eval_res.violations + eval_res.critique
            feedback_history.append(combined_feedback)

        # Fallback if max iterations exceeded
        fallback_summary = self.fallback_deterministic(session_context)
        fallback_evaluation = self.evaluator.evaluate(fallback_summary, session_context)
        return {
            "status": "fallback",
            "method": "deterministic",
            "iterations": self.config.max_iterations,
            "summary": fallback_summary,
            "score": fallback_evaluation.score,
            "history": iteration_records,
        }

    def fallback_deterministic(self, session_context: Dict[str, Any]) -> str:
        signals = session_context.get("signals", [])
        consent = session_context.get("consent", {})
        scopes = [scope for scope in SCOPES if consent.get(scope) is True]
        disabled = [scope for scope in SCOPES if consent.get(scope) is not True]
        return (
            f"The candidate enabled {len(scopes)} technical scopes ({', '.join(scopes) or 'none'}). "
            f"{len(signals)} unique technical observation(s) were retained for human review. "
            f"Scopes not enabled: {', '.join(disabled) or 'none'}. Enabled scopes do not guarantee available measurements. "
            "Unavailable checks remain unknown. This local deterministic summary uses the recorded scope choices "
            "and retained observation count; human review is required. It does not determine intent or candidate qualification."
        )

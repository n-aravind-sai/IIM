from dataclasses import asdict, dataclass, field
from typing import Any
from .correlation import source_ref


@dataclass
class Signal:
    id: str
    detector: str
    title: str
    confidence: float
    weight: float
    evidence: dict[str, Any]
    explanation: str
    limitation: str

    def __post_init__(self):
        if not 0 <= self.confidence <= 1 or not 0 <= self.weight <= 1:
            raise ValueError("Confidence and weight must be between 0 and 1")


@dataclass
class Result:
    detector: str
    status: str  # available | partial | waiting | unsupported | disabled | error
    detail: str
    signals: list[Signal] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def json(self):
        return asdict(self)


CAPS = {"OverlayDetector": 20, "ProcessDetector": 15,
        "AudioCaptureDetector": 5, "VirtualDisplayDetector": 5,
        "BrowserExtensionDetector": 10, "GazeDetector": 0}


def score(results: list[Result]):
    """Uncalibrated observation index. Never a probability of misconduct.

    Use each detector's strongest signal. Supported shared process-instance
    maxima contribute only the larger deduction; unknown links remain separate.
    Gaze is never scored. Missing detectors never count as clean coverage.
    """
    technical = [r for r in results if CAPS.get(r.detector, 0) > 0]
    usable = [r for r in technical if r.status in ("available", "partial")]
    if not usable:
        return {"version": 2, "value": None, "coverage": 0, "label": "Insufficient coverage", "badge": "INSUFFICIENT_COVERAGE"}
    deductions = {}
    for result in usable:
        if not result.signals:
            continue
        strongest = min(result.signals, key=lambda s: (-s.confidence * s.weight, s.id))
        ref = source_ref(strongest) if strongest.detector == result.detector else None
        key = ('source', ref) if ref else ('detector', result.detector)
        points = CAPS[result.detector] * strongest.confidence * strongest.weight
        deductions[key] = max(deductions.get(key, 0), points)
    penalty = sum(deductions.values())
    coverage = round(100 * sum(1 if r.status == "available" else .5
                               for r in usable) / len(CAPS.keys() - {"GazeDetector"}))
    if penalty > 0:
        badge = "OBSERVATIONS_FOR_REVIEW"
    elif coverage < 100:
        badge = "PARTIAL_COVERAGE"
    else:
        badge = "STANDARD_BASELINE"
    return {"version": 2, "value": round(100 - penalty), "coverage": coverage,
            "label": "Review observations" if penalty else "No matching observations",
            "badge": badge}

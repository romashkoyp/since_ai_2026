"""Deterministic operator triage for alert payloads (presentation only).

These bands never alter detector confidence, fault type, or benchmark predictions.
"""

from enum import Enum


class Severity(str, Enum):
    SEVERE = "SEVERE"
    MODERATE = "MODERATE"
    MINIMAL = "MINIMAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


def categorize_alert(event_class: str, fault_type: str, confidence: float) -> Severity:
    """Map a detector alert to its operator-review band.

    UNKNOWN is kept separate from MINIMAL so an honest lack of diagnosis is not
    presented as an ordinary low-priority fault.
    """
    if fault_type == "UNKNOWN":
        return Severity.LOW_CONFIDENCE
    if confidence < 0.50:
        return Severity.MINIMAL
    if event_class == "MACHINE" and confidence >= 0.75:
        return Severity.SEVERE
    return Severity.MODERATE

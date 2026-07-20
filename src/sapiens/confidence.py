"""Confidence aggregation (Phase 2) — only on top of calibration data.

There is no confidence without calibration. ``aggregate_confidence`` raises
:class:`UncalibratedError` unless handed a :class:`CalibrationReport` built
from enough labelled fixtures; the gates' *demonstrated* catch rate is the
only discount applied, and the formula is a documented heuristic, not a
probability estimate. We do not invent precision.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calibration import CalibrationReport
from .models import Evidence

FORMULA_VERSION = "catch-rate-discount-v1"


class UncalibratedError(RuntimeError):
    """No trustworthy calibration data exists; refuse to emit a number."""


@dataclass(frozen=True)
class CalibratedConfidence:
    """A bounded heuristic score with its full provenance attached."""

    value: float  # raw_pass_fraction * catch_rate, in [0, 1]
    raw_pass_fraction: float
    catch_rate: float
    false_reject_rate: float
    calibration_report_id: str
    formula: str
    caveat: str = (
        "Heuristic score, not a probability: raw pass fraction discounted by "
        "the gates' demonstrated catch rate on seeded fixtures."
    )


def aggregate_confidence(
    evidence: tuple[Evidence, ...],
    calibration: CalibrationReport | None,
    *,
    min_known_bad: int = 2,
    min_known_good: int = 1,
) -> CalibratedConfidence:
    """Aggregate evidence into a calibrated score, or refuse.

    Refusal is the point: without a calibration report meeting minimum
    fixture counts, any number would be invented precision.
    """
    if calibration is None:
        raise UncalibratedError("no calibration report supplied; confidence refused")
    if not calibration.meets_minimum(
        min_known_bad=min_known_bad, min_known_good=min_known_good
    ):
        raise UncalibratedError(
            f"calibration report {calibration.report_id} is too thin "
            f"(known_bad={calibration.known_bad_total}, "
            f"known_good={calibration.known_good_total}); confidence refused"
        )
    if not evidence:
        raise UncalibratedError("no evidence supplied; confidence refused")
    raw = sum(1 for item in evidence if item.passed) / len(evidence)
    value = raw * calibration.catch_rate
    return CalibratedConfidence(
        value=value,
        raw_pass_fraction=raw,
        catch_rate=calibration.catch_rate,
        false_reject_rate=calibration.false_reject_rate,
        calibration_report_id=calibration.report_id,
        formula=FORMULA_VERSION,
    )

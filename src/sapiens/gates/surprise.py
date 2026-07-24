"""G-03 (literature-measured surprise) and G-07 (robust full-dataset baseline).

Two anti-gaming primitives from HOW-TO-PROCEED Phase 0:

* **G-07 — baseline gaming.** The MAD/sigma baseline must be computed on the
  **full dataset** with a robust estimator over *all* points — never a
  pre-filtered "clean" subset that excludes the anomaly and thereby inflates
  the apparent significance. :func:`robust_baseline` refuses to drop points and
  records the exact point count it saw, so a gamed "baseline on 3 hand-picked
  points" is structurally impossible through this API.

* **G-03 — free anomaly boost.** An anomaly earns priority only when it
  *measurably contradicts a literature expectation*, not merely because no
  explanation is attached. A trivial unexplained number has zero measured
  surprise and therefore earns **no** boost; only a result whose deviation from
  a cited expectation exceeds a floor counts as "surprising".

Pure stdlib (``math``, ``statistics``).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

# MAD -> sigma consistency constant for a normal distribution.
_MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class RobustBaseline:
    """A robust location/scale estimate computed over the FULL dataset (G-07)."""

    n_points: int  # exact number of points used; the anti-gaming receipt
    center: float  # median (robust location)
    scale: float  # MAD * 1.4826 (robust sigma), 0.0 only if truly degenerate
    used_all_points: bool = True  # this API never pre-filters

    def sigma_of(self, value: float) -> float:
        """Deviation of ``value`` from the baseline, in robust-sigma units."""
        if self.scale <= 0.0:
            return 0.0
        return abs(float(value) - self.center) / self.scale


def robust_baseline(values: list[float]) -> RobustBaseline:
    """Median + MAD-sigma over **all** ``values`` (G-07: no clean-subset gaming).

    Raises on an empty dataset — a baseline requires data. The estimator is
    deliberately robust (median/MAD) so a single extreme anomaly cannot inflate
    the scale the way sample-std would; and it consumes every point handed to
    it, so callers cannot smuggle in a pre-filtered subset without it showing up
    as a smaller ``n_points`` than the source dataset.
    """
    vals = [float(v) for v in values]
    if not vals:
        raise ValueError("robust_baseline requires a non-empty dataset (G-07)")
    center = statistics.median(vals)
    mad = statistics.median([abs(v - center) for v in vals])
    return RobustBaseline(n_points=len(vals), center=center, scale=mad * _MAD_TO_SIGMA)


@dataclass(frozen=True)
class LiteratureExpectation:
    """A cited prior expectation a candidate is measured against (G-03).

    ``expected`` and ``expected_sigma`` come from the literature/instrument
    error budget, not from the candidate's own dataset — that is what makes the
    resulting surprise a *measured contradiction of expectation* rather than a
    free boost for any unexplained number.
    """

    expected: float
    expected_sigma: float
    citation: str

    def __post_init__(self) -> None:
        if self.expected_sigma <= 0.0:
            raise ValueError("expected_sigma must be positive")
        if not self.citation:
            raise ValueError("a literature expectation must carry a citation (G-03)")


def measured_surprise(observed: float, expectation: LiteratureExpectation | None) -> float:
    """Surprise in sigma: how far ``observed`` sits from a *cited* expectation.

    Returns 0.0 when no literature expectation is supplied — the key G-03
    property: **absence of an expectation is not surprise.** A number nobody has
    a prediction for earns no anomaly boost; only a measurable contradiction of
    a cited prior does.
    """
    if expectation is None:
        return 0.0
    return abs(float(observed) - expectation.expected) / expectation.expected_sigma


def is_surprising(
    observed: float,
    expectation: LiteratureExpectation | None,
    *,
    floor_sigma: float = 3.0,
) -> bool:
    """True only when the measured surprise clears ``floor_sigma`` (G-03).

    This is the gate the anomaly-priority boost is conditioned on: mere absence
    of a mechanism/explanation never satisfies it; a cited, measured
    contradiction does.
    """
    return math.isfinite(measured_surprise(observed, expectation)) and (
        measured_surprise(observed, expectation) >= floor_sigma
    )

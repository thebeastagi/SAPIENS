"""Phase 0 core — recalibrated promotion scoring with the 4 gaming seams welded.

Implements the recalibrated promotion function (GATES-RECALIBRATION Part 3) with
the four Phase-0 anti-gaming patches and the FP-06 conservation-law guard baked
in so they cannot be bypassed:

* **G-03** — ``anomaly_priority`` is conditioned on *literature-measured
  surprise*, not the mere absence of a mechanism. A trivial unexplained number
  earns no boost.
* **G-05** — a reserved paradigm-breaker slot requires
  ``promotion_score >= 0.30`` **and** the G-03 surprise condition. A barely-L1
  candidate can no longer squat a reserved slot.
* **G-06** — L2-holdout-passed is a *prerequisite* for CALIBRATED status
  (holdout N/A allowed only for deductive / single-observation classes). The
  additive 0.50 term only *ranks within* the calibrated set; it is never the
  admission key.
* **FP-06** — "no known mechanism" boosts, but "violates a conservation law"
  means the correct null is *measurement error* and demands reproducible
  orthogonal confirmation before **any** boost.

Pure stdlib. Score weights follow the recalibration summary; they are a
documented heuristic ranking aid, not a probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .nulls import NullProvenance
from .surprise import LiteratureExpectation, is_surprising, measured_surprise
from .thresholds import ThresholdPolicy


class LedgerStatus(str, Enum):
    """R1 four-way mechanism x replication ledger (never a kill dimension)."""

    EXPLAINED_CONFIRMED = "explained-confirmed"  # mechanism + replication (gold)
    UNEXPLAINED_CONFIRMED = "unexplained-confirmed"  # the paradigm-breaker signature
    EXPLAINED_UNCONFIRMED = "explained-unconfirmed"  # follow-up queue
    UNEXPLAINED_UNCONFIRMED = "unexplained-unconfirmed"  # low initial rank


class CalibrationStatus(str, Enum):
    CALIBRATED = "calibrated"
    UNCALIBRATED = "uncalibrated"  # surfaced, never a silent pass (R6)


# Recalibrated promotion weights (GATES-RECALIBRATION "promotion function").
W_PROVENANCE = 0.25  # S1, hard prereq (also gated separately)
W_NULL_SIGMA = 0.30  # S2, continuous, floor 3-sigma to enter
W_METHOD = 0.20  # G5, analysis soundness, NOT consensus
W_REPLICATION = 0.15  # S5, 0 at t0, grows with follow-up
W_ORTHOGONAL = 0.10  # S3, 0 at t0, grows with follow-up

_SIGMA_SATURATE = 6.0  # sigma at which the null term saturates to 1.0


@dataclass(frozen=True)
class GateInputs:
    """Everything a candidate presents to the Phase-0/1/2 gates.

    Deliberately domain-neutral: the adapters translate their measurements into
    these fields. Nothing here copies ASTRA/GEODISC/BIODISC/SLATE code.
    """

    candidate_id: str
    domain: str  # matches thresholds.Domain values where possible
    # --- evidence hygiene (hard prereqs live in the runtime kernel) ---
    provenance_ok: bool  # S1 sky-lock / signal-in-raw-data
    method_integrity: float  # G5 analysis soundness in [0,1] (NOT consensus)
    # --- null layer (Phase 1) ---
    null: NullProvenance
    # --- maturity dimensions (rank, never admission) ---
    has_mechanism: bool
    has_replication: bool
    orthogonal_confirmation: bool
    holdout_passed: bool | None  # L2 gate; None => not-applicable class
    consensus_conflict: bool = False
    # --- G-03 surprise inputs ---
    observed_value: float | None = None
    literature_expectation: LiteratureExpectation | None = None
    # --- FP-06 guard ---
    violates_conservation_law: bool = False
    # freeform, for the dossier only
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def deductive_or_single_obs(self) -> bool:
        """Classes for which L2 holdout is a category error (R7)."""
        return self.holdout_passed is None


def _null_sigma_term(inputs: GateInputs) -> float:
    """Continuous [0,1] term from the significance measured against the null."""
    if not inputs.null.calibratable or inputs.null.sigma_under_null is None:
        return 0.0
    return min(max(inputs.null.sigma_under_null, 0.0) / _SIGMA_SATURATE, 1.0)


def ledger_status(inputs: GateInputs) -> LedgerStatus:
    """The R1 four-way ledger cell for this candidate."""
    if inputs.has_mechanism and inputs.has_replication:
        return LedgerStatus.EXPLAINED_CONFIRMED
    if inputs.has_replication:
        return LedgerStatus.UNEXPLAINED_CONFIRMED
    if inputs.has_mechanism:
        return LedgerStatus.EXPLAINED_UNCONFIRMED
    return LedgerStatus.UNEXPLAINED_UNCONFIRMED


def promotion_score(inputs: GateInputs) -> float:
    """Recalibrated promotion score in [0,1] (rank aid, not a probability).

    Weighted, additive; maturity dimensions contribute but never subtract, and
    mechanism-absence is *not* penalised here (it is handled as an
    anomaly-priority boost, R1). Provenance is a weighted term here AND a hard
    prereq enforced by the runtime kernel.
    """
    score = 0.0
    score += W_PROVENANCE * (1.0 if inputs.provenance_ok else 0.0)
    score += W_NULL_SIGMA * _null_sigma_term(inputs)
    score += W_METHOD * min(max(inputs.method_integrity, 0.0), 1.0)
    score += W_REPLICATION * (1.0 if inputs.has_replication else 0.0)
    score += W_ORTHOGONAL * (1.0 if inputs.orthogonal_confirmation else 0.0)
    return round(min(score, 1.0), 6)


def anomaly_priority(inputs: GateInputs, *, policy: ThresholdPolicy) -> float:
    """Inverted mechanism signal (R1) — but gated by G-03 and FP-06.

    * G-03: mechanism-absence contributes only when the candidate is
      *measurably surprising* against a cited expectation; an unexplained-but-
      unsurprising number earns nothing.
    * FP-06: a conservation-law violation means the correct null is measurement
      error — no boost at all until orthogonal replication confirms it.
    """
    # FP-06 conservation-law guard: measurement error is the correct null.
    if inputs.violates_conservation_law and not (
        inputs.has_replication and inputs.orthogonal_confirmation
    ):
        return 0.0
    priority = 0.0
    surprising = is_surprising(
        inputs.observed_value if inputs.observed_value is not None else 0.0,
        inputs.literature_expectation,
        floor_sigma=policy.surprise_floor_sigma,
    )
    # G-03: mechanism-absence boost ONLY when measurably surprising.
    if not inputs.has_mechanism and surprising:
        priority += 0.10
    # Consensus-conflict is a novelty signal, never a demerit (R2).
    if inputs.consensus_conflict:
        priority += 0.05
    return round(min(priority, 1.0), 6)


def calibration_status(inputs: GateInputs) -> CalibrationStatus:
    """G-06 — CALIBRATED requires L2-holdout-passed (or an N/A class) + a
    calibratable null. Otherwise UNCALIBRATED (surfaced, never a silent pass).
    """
    if not inputs.null.calibratable:
        return CalibrationStatus.UNCALIBRATED
    # holdout is a prerequisite; None means the deductive/single-obs carve-out.
    if inputs.holdout_passed is False:
        return CalibrationStatus.UNCALIBRATED
    return CalibrationStatus.CALIBRATED


def reserved_slot_eligible(inputs: GateInputs, *, policy: ThresholdPolicy) -> bool:
    """G-05 — a reserved paradigm-breaker slot requires BOTH a real promotion
    score (``>= reserved_slot_min_promotion``) AND the G-03 surprise condition,
    and the UNEXPLAINED_CONFIRMED signature. Squatting is structurally blocked.
    """
    if ledger_status(inputs) != LedgerStatus.UNEXPLAINED_CONFIRMED:
        return False
    if promotion_score(inputs) < policy.reserved_slot_min_promotion:
        return False
    surprising = is_surprising(
        inputs.observed_value if inputs.observed_value is not None else 0.0,
        inputs.literature_expectation,
        floor_sigma=policy.surprise_floor_sigma,
    )
    if not surprising:
        return False
    # FP-06: a conservation-law breaker cannot take a reserved slot unconfirmed.
    return not (inputs.violates_conservation_law and not inputs.orthogonal_confirmation)


def surprise_sigma(inputs: GateInputs) -> float:
    """Convenience: measured surprise in sigma (0.0 if no cited expectation)."""
    return measured_surprise(
        inputs.observed_value if inputs.observed_value is not None else 0.0,
        inputs.literature_expectation,
    )

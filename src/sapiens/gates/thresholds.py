"""Phase 2 — decoupled threshold architecture + cheap boundary fixes.

Retires the single ``max_pvalue = 0.05`` entry wall and splits three thresholds
that were being conflated:

============ ================================================================
Stage        Threshold
============ ================================================================
ENTRY        3-sigma-equiv AND survives BH-FDR q<0.05 across the family
RANK         continuous sigma / effect (no cliff; feeds the top-K throttle)
CONFIRM      5-sigma (physics) / FDR<0.05 + orthogonal replication (bio) /
             formal proof-check (math)
============ ================================================================

One-liner: *"3-sigma + FDR to enter, 5-sigma or replication to claim; 0.05 per
test alone is a multiplicity trap."*

Boundary fixes folded in:

* **B-02** adaptive ``ci_floor`` — a margin above the majority-class base rate,
  never a fixed 0.70.
* **B-03** hash-commit domain thresholds *before* seeing results.
* **B-05** continuous degree-of-calibration replacing the hard 0.50 quota wall.

Pure stdlib (``hashlib``, ``json``, ``math``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Domain(str, Enum):
    """Confirmation regime differs by domain (Phase 2 CONFIRM column)."""

    PHYSICS = "physics"  # 5-sigma
    BIO = "bio"  # FDR<0.05 + orthogonal replication
    MATH = "math"  # formal proof-check
    GENERIC = "generic"  # default: FDR + orthogonal confirmation


@dataclass(frozen=True)
class ThresholdPolicy:
    """The full, hash-committable threshold set for one pipeline run (B-03)."""

    entry_sigma: float = 3.0  # ENTRY floor (R5): 3-sigma admits early positives
    entry_fdr_q: float = 0.05  # ENTRY also requires family-wide BH-FDR survival
    confirm_sigma_physics: float = 5.0  # CONFIRM bar for physics
    confirm_fdr_q_bio: float = 0.05  # CONFIRM bar for bio (plus replication)
    reserved_slot_min_promotion: float = 0.30  # G-05: reserved-slot prerequisite
    surprise_floor_sigma: float = 3.0  # G-03: surprise floor for anomaly boost
    top_k: int = 10  # Phase 4 bounded human load
    ci_floor_margin: float = 0.15  # B-02: margin above majority-class base rate
    devils_advocate_r: float = 0.90  # B-06: r>=this triggers a permutation test
    version: str = "gate-hardening-v1"

    def hash_commit(self, run_id: str) -> str:
        """SHA-256 over the canonical policy + run id (B-03).

        Call this **before** the run sees any candidate results and record the
        digest; it makes post-hoc threshold tuning tamper-evident.
        """
        payload = json.dumps(
            {"run_id": run_id, "policy": asdict(self)},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def adaptive_ci_floor(majority_base_rate: float, margin: float = 0.15) -> float:
    """B-02: ci_floor = majority-class base rate + margin (never a fixed 0.70).

    On a 95%-majority-class problem a fixed 0.70 floor is *below chance* and
    admits noise; on a balanced problem 0.70 may be needlessly harsh. Anchoring
    the floor to the base rate plus a fixed margin fixes both. Clamped to
    (base_rate, 1.0).
    """
    base = min(max(float(majority_base_rate), 0.0), 1.0)
    return min(1.0 - 1e-9, max(base + float(margin), base))


def degree_of_calibration(
    known_good_covered: int,
    known_bad_covered: int,
    *,
    target_good: int = 5,
    target_bad: int = 5,
) -> float:
    """B-05: continuous [0,1] calibration coverage, replacing a hard 0.50 wall.

    A hard quota (">=50% of strata calibrated -> CALIBRATED, else refuse")
    creates a cliff exactly where borderline candidates live. This returns a
    smooth coverage fraction so ranking degrades gracefully instead of flipping
    at a wall.
    """
    good = min(known_good_covered / target_good, 1.0) if target_good else 1.0
    bad = min(known_bad_covered / target_bad, 1.0) if target_bad else 1.0
    return round(0.5 * (good + bad), 6)


class Tier(str, Enum):
    """Where a candidate lands after the decoupled thresholds are applied."""

    UNCALIBRATED = "uncalibrated"  # surfaced, never silently passed (R6)
    ENTRY = "entry"  # on the shortlist; not claimable
    CONFIRM = "confirm"  # meets the claim bar; human co-sign still required


@dataclass(frozen=True)
class ConfirmDecision:
    """Outcome of the domain-specific CONFIRM check."""

    domain: Domain
    confirmed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def confirm_decision(
    domain: Domain,
    *,
    sigma: float | None,
    fdr_rejected: bool,
    orthogonal_replication: bool,
    proof_checked: bool,
    policy: ThresholdPolicy,
) -> ConfirmDecision:
    """Apply the domain-appropriate CONFIRM bar (the *claim* threshold).

    This is where the old 5-sigma rigor belongs — as a claim bar, not a
    candidacy bar.
    """
    reasons: list[str] = []
    if domain == Domain.PHYSICS:
        ok = sigma is not None and sigma >= policy.confirm_sigma_physics
        if not ok:
            reasons.append(
                f"physics CONFIRM needs sigma>={policy.confirm_sigma_physics} "
                f"(got {sigma})"
            )
    elif domain == Domain.BIO:
        ok = fdr_rejected and orthogonal_replication
        if not fdr_rejected:
            reasons.append("bio CONFIRM needs family FDR rejection")
        if not orthogonal_replication:
            reasons.append("bio CONFIRM needs orthogonal replication")
    elif domain == Domain.MATH:
        ok = proof_checked
        if not ok:
            reasons.append("math CONFIRM needs a passing formal proof-check")
    else:  # GENERIC
        ok = fdr_rejected and orthogonal_replication
        if not ok:
            reasons.append("generic CONFIRM needs FDR rejection + orthogonal confirmation")
    return ConfirmDecision(domain=domain, confirmed=ok, reasons=tuple(reasons))

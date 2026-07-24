"""Orchestration — run a candidate *family* through the Phase-0/1/2 gates.

This is where the pieces compose into the decoupled architecture:

1. **ENTRY** (Phase 2): 3-sigma-equiv against the null AND survives family-wide
   BH-FDR q<0.05. Both terms are required — the FDR term is what kills the
   multiplicity trap (FP-09/FP-10).
2. **RANK** (Phase 2/4): continuous combined score = promotion_score +
   anomaly_priority; feeds the bounded top-K human throttle.
3. **CONFIRM** (Phase 2): domain-specific claim bar (5-sigma / FDR+replication /
   proof-check). Only CONFIRM-tier candidates are ever claim-eligible.

The null layer (Phase 1) is mandatory: a candidate with no calibratable null is
tiered UNCALIBRATED and surfaced, never silently passed. Reserved paradigm-
breaker slots (G-05) are guaranteed representation in the shortlist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fdr import benjamini_hochberg, sigma_to_pvalue
from .nulls import InstrumentSystematic
from .promotion import (
    CalibrationStatus,
    GateInputs,
    LedgerStatus,
    anomaly_priority,
    calibration_status,
    ledger_status,
    promotion_score,
    reserved_slot_eligible,
    surprise_sigma,
)
from .thresholds import Domain, ThresholdPolicy, Tier, confirm_decision


@dataclass(frozen=True)
class GateOutcome:
    """Per-candidate result after Phase 0/1/2 over the whole family."""

    candidate_id: str
    domain: str
    tier: Tier
    entered: bool  # passed ENTRY (shortlist admission)
    rank_score: float  # continuous RANK score (promotion + anomaly)
    promotion_score: float
    anomaly_priority: float
    calibration_status: CalibrationStatus
    ledger_status: LedgerStatus
    sigma_under_null: float | None
    fdr_qvalue: float | None
    fdr_rejected: bool
    surprise_sigma: float
    reserved_slot: bool
    instrument_systematic_flag: bool  # FP-04 surfaced
    confirm_reasons: tuple[str, ...] = field(default_factory=tuple)
    null_provenance: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "domain": self.domain,
            "tier": self.tier.value,
            "entered": self.entered,
            "rank_score": self.rank_score,
            "promotion_score": self.promotion_score,
            "anomaly_priority": self.anomaly_priority,
            "calibration_status": self.calibration_status.value,
            "ledger_status": self.ledger_status.value,
            "sigma_under_null": self.sigma_under_null,
            "fdr_qvalue": self.fdr_qvalue,
            "fdr_rejected": self.fdr_rejected,
            "surprise_sigma": self.surprise_sigma,
            "reserved_slot": self.reserved_slot,
            "instrument_systematic_flag": self.instrument_systematic_flag,
            "confirm_reasons": list(self.confirm_reasons),
            "null_provenance": self.null_provenance,
        }


@dataclass(frozen=True)
class FamilyResult:
    """The whole-family outcome plus the bounded top-K shortlist."""

    outcomes: tuple[GateOutcome, ...]
    shortlist: tuple[GateOutcome, ...]  # bounded top-K (Phase 4 throttle)
    policy_hash: str
    run_id: str

    @property
    def entered_count(self) -> int:
        return sum(1 for o in self.outcomes if o.entered)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "policy_hash": self.policy_hash,
            "scientific_discoveries_claimed": 0,  # by construction
            "entered_count": self.entered_count,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "shortlist": [o.candidate_id for o in self.shortlist],
        }


def _domain(value: str) -> Domain:
    try:
        return Domain(value)
    except ValueError:
        return Domain.GENERIC


def evaluate_family(
    candidates: list[GateInputs],
    *,
    policy: ThresholdPolicy | None = None,
    run_id: str = "run",
    orthogonal_by_id: dict[str, bool] | None = None,
    proof_checked_by_id: dict[str, bool] | None = None,
) -> FamilyResult:
    """Run the full family through Phase 0/1/2 and build the bounded shortlist.

    ``orthogonal_by_id`` / ``proof_checked_by_id`` let the caller supply
    confirmation evidence collected after first proposal (the follow-up track);
    they default to the per-candidate fields on :class:`GateInputs`.
    """
    policy = policy or ThresholdPolicy()
    orthogonal_by_id = orthogonal_by_id or {}
    proof_checked_by_id = proof_checked_by_id or {}
    policy_hash = policy.hash_commit(run_id)

    # Family-wide FDR across the members that have a null sigma (Phase 1/2).
    pvals: list[float] = []
    for c in candidates:
        sig = c.null.sigma_under_null if c.null.calibratable else None
        pvals.append(sigma_to_pvalue(sig) if sig is not None else 1.0)
    fdr = benjamini_hochberg(pvals, policy.entry_fdr_q) if candidates else []

    outcomes: list[GateOutcome] = []
    for i, c in enumerate(candidates):
        sig = c.null.sigma_under_null if c.null.calibratable else None
        cal = calibration_status(c)
        pscore = promotion_score(c)
        apriority = anomaly_priority(c, policy=policy)
        rank = round(min(pscore + apriority, 1.0), 6)
        f = fdr[i] if fdr else None
        fdr_rej = bool(f.rejected) if f else False
        qval = f.qvalue if f else None

        orthogonal = orthogonal_by_id.get(
            c.candidate_id, c.orthogonal_confirmation and c.has_replication
        )

        # FP-06 conservation guard at the TIER level: for a conservation-law
        # violation the correct null is measurement error, so until reproducible
        # orthogonal confirmation exists the "significance" is not established —
        # it is surfaced (UNCALIBRATED), never admitted as a clean signal.
        conservation_block = c.violates_conservation_law and not orthogonal

        # ENTRY (Phase 2): 3-sigma-equiv AND family-wide FDR survival AND a
        # calibratable null (G-06: L2-holdout is a prerequisite, so an
        # UNCALIBRATED candidate is surfaced, never admitted as a clean signal).
        meets_sigma = sig is not None and sig >= policy.entry_sigma
        entered = bool(
            meets_sigma
            and fdr_rej
            and c.provenance_ok
            and cal == CalibrationStatus.CALIBRATED
            and not conservation_block
        )

        # CONFIRM (Phase 2): domain-specific claim bar.
        conf = confirm_decision(
            _domain(c.domain),
            sigma=sig,
            fdr_rejected=fdr_rej,
            orthogonal_replication=orthogonal,
            proof_checked=proof_checked_by_id.get(c.candidate_id, False),
            policy=policy,
        )
        reasons = conf.reasons
        if conservation_block:
            reasons = (*reasons, "FP-06: conservation-law violation needs orthogonal confirmation")

        # Tiering: UNCALIBRATED surfaces even if it cleared sigma (R6/FP-04/FP-06).
        if cal == CalibrationStatus.UNCALIBRATED or conservation_block:
            tier = Tier.UNCALIBRATED
        elif conf.confirmed and entered:
            tier = Tier.CONFIRM
        elif entered:
            tier = Tier.ENTRY
        else:
            tier = Tier.UNCALIBRATED

        outcomes.append(
            GateOutcome(
                candidate_id=c.candidate_id,
                domain=c.domain,
                tier=tier,
                entered=entered,
                rank_score=rank,
                promotion_score=pscore,
                anomaly_priority=apriority,
                calibration_status=cal,
                ledger_status=ledger_status(c),
                sigma_under_null=sig,
                fdr_qvalue=qval,
                fdr_rejected=fdr_rej,
                surprise_sigma=round(surprise_sigma(c), 6),
                reserved_slot=reserved_slot_eligible(c, policy=policy),
                instrument_systematic_flag=(
                    c.null.instrument_systematic == InstrumentSystematic.NOT_EXCLUDED
                ),
                confirm_reasons=reasons,
                null_provenance=c.null.to_dict(),
            )
        )

    shortlist = _build_shortlist(outcomes, policy.top_k)
    return FamilyResult(
        outcomes=tuple(outcomes),
        shortlist=tuple(shortlist),
        policy_hash=policy_hash,
        run_id=run_id,
    )


def _build_shortlist(outcomes: list[GateOutcome], top_k: int) -> list[GateOutcome]:
    """Bounded top-K by rank, with >=guaranteed reserved paradigm-breaker slots.

    Reserved-slot-eligible candidates get guaranteed representation so the sieve
    can never rank paradigm-breakers to zero (recalibration Part 4), while the
    overall list stays bounded to protect human review time.
    """
    ranked = sorted(
        (o for o in outcomes if o.entered or o.reserved_slot),
        key=lambda o: o.rank_score,
        reverse=True,
    )
    reserved = [o for o in ranked if o.reserved_slot]
    non_reserved = [o for o in ranked if not o.reserved_slot]
    shortlist: list[GateOutcome] = []
    # Guarantee up to 2 reserved slots first (Part 4: ">=2 reserved").
    for o in reserved[:2]:
        shortlist.append(o)
    for o in non_reserved:
        if len(shortlist) >= top_k:
            break
        shortlist.append(o)
    # Backfill any remaining reserved if room.
    for o in reserved[2:]:
        if len(shortlist) >= top_k:
            break
        shortlist.append(o)
    return shortlist[:top_k]

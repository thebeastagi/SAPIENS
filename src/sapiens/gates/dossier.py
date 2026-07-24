"""Phase 4 — human-in-loop final gate (decision support, not verdict delivery).

The human gate is the throttle and the accountability seam. This module builds
the decision-support artifacts the reviewer sees:

* **Per-candidate dossier** (:func:`build_dossier`): sigma, FDR-q, which null was
  used, external data fetched (y/n), replication status, UNCALIBRATED /
  instrument-systematic flags, and — forced next to the claim — **the single
  strongest disconfirming explanation** (the correct null).
* **Tiered authority** (:func:`autonomous_claim_eligible`): only CONFIRM-tier
  candidates are eligible for an autonomous claim, and only after human
  co-sign. ENTRY / UNCALIBRATED stay surfaced-but-unclaimed.
* **Bounded load**: the shortlist is already bounded to top-K upstream; this
  keeps review feasible.
* **Closed loop** (:class:`OverrideLog`): every human override is logged as
  labeled data feeding back into recalibration — the human gate becomes a
  training signal, not just the last checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pipeline import GateOutcome
from .promotion import CalibrationStatus
from .thresholds import Tier


@dataclass(frozen=True)
class Dossier:
    """The referee bundle for one candidate (recalibration Part 4)."""

    candidate_id: str
    domain: str
    tier: str
    sigma_under_null: float | None
    fdr_qvalue: float | None
    null_used: str
    external_data_fetched: bool
    replication_status: str
    uncalibrated: bool
    instrument_systematic: bool
    strongest_disconfirming_explanation: str  # shown NEXT TO the claim
    autonomous_claim_eligible: bool
    reserved_slot: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "domain": self.domain,
            "tier": self.tier,
            "sigma_under_null": self.sigma_under_null,
            "fdr_qvalue": self.fdr_qvalue,
            "null_used": self.null_used,
            "external_data_fetched": self.external_data_fetched,
            "replication_status": self.replication_status,
            "uncalibrated": self.uncalibrated,
            "instrument_systematic": self.instrument_systematic,
            "strongest_disconfirming_explanation": self.strongest_disconfirming_explanation,
            "autonomous_claim_eligible": self.autonomous_claim_eligible,
            "reserved_slot": self.reserved_slot,
        }


def _disconfirming_explanation(o: GateOutcome) -> str:
    """The single strongest counter-case, forced in front of the reviewer."""
    if o.instrument_systematic_flag:
        return (
            "Instrument systematic not excluded — the apparent signal may be a "
            "hardware artifact (e.g. loose-fibre timing); orthogonal-hardware "
            "check required before belief."
        )
    null_desc = str(o.null_provenance.get("description", "the correct null"))
    if not o.null_provenance.get("data_complete", True):
        return (
            f"Required external data for the null ({null_desc}) was NOT fetched; "
            "significance is not established against the correct null."
        )
    if o.calibration_status == CalibrationStatus.UNCALIBRATED:
        return (
            f"Best null considered ({null_desc}) does not yet calibrate this "
            "candidate; treat the evidence as raw, not a calibrated number."
        )
    return (
        f"Best null considered: {null_desc}. It is rejected at "
        f"sigma={o.sigma_under_null}; if the null were correct this deviation "
        "would be a fluke at the stated family FDR."
    )


def _replication_status(o: GateOutcome) -> str:
    if o.ledger_status.value.endswith("confirmed") and "unexplained" in o.ledger_status.value:
        return "replicated (no accepted mechanism yet)"
    if o.ledger_status.value.startswith("explained-confirmed"):
        return "replicated + mechanism"
    if o.ledger_status.value.endswith("unconfirmed"):
        return "not yet independently replicated"
    return o.ledger_status.value


def autonomous_claim_eligible(o: GateOutcome) -> bool:
    """Only CONFIRM-tier candidates may ever be autonomously claimed — and even
    then a human co-sign is still required downstream (never returned True for
    anything below CONFIRM)."""
    return o.tier == Tier.CONFIRM


def build_dossier(o: GateOutcome) -> Dossier:
    """Assemble the reviewer-facing dossier for one gate outcome."""
    return Dossier(
        candidate_id=o.candidate_id,
        domain=o.domain,
        tier=o.tier.value,
        sigma_under_null=o.sigma_under_null,
        fdr_qvalue=o.fdr_qvalue,
        null_used=str(o.null_provenance.get("description", "")),
        external_data_fetched=bool(o.null_provenance.get("external_data_fetched", False)),
        replication_status=_replication_status(o),
        uncalibrated=o.calibration_status == CalibrationStatus.UNCALIBRATED,
        instrument_systematic=o.instrument_systematic_flag,
        strongest_disconfirming_explanation=_disconfirming_explanation(o),
        autonomous_claim_eligible=autonomous_claim_eligible(o),
        reserved_slot=o.reserved_slot,
    )


@dataclass(frozen=True)
class OverrideEvent:
    """A logged human decision — labeled data for recalibration."""

    candidate_id: str
    frozen_tier: str  # the machine tier at review time (frozen)
    human_verdict: str  # "pursue" | "reject" | "defer"
    rationale: str
    timestamp: str

    def __post_init__(self) -> None:
        if self.human_verdict not in ("pursue", "reject", "defer"):
            raise ValueError("human_verdict must be pursue | reject | defer")


@dataclass
class OverrideLog:
    """Append-only log of human overrides feeding the calibration loop.

    ``as_training_labels`` yields (frozen machine tier, human verdict) pairs —
    exactly the signal Phase-5 recalibration consumes to detect systematic
    over/under-confidence per tier.
    """

    events: list[OverrideEvent] = field(default_factory=list)

    def record(
        self,
        outcome: GateOutcome,
        *,
        human_verdict: str,
        rationale: str,
        timestamp: str,
    ) -> OverrideEvent:
        event = OverrideEvent(
            candidate_id=outcome.candidate_id,
            frozen_tier=outcome.tier.value,
            human_verdict=human_verdict,
            rationale=rationale,
            timestamp=timestamp,
        )
        self.events.append(event)
        return event

    def as_training_labels(self) -> list[tuple[str, str]]:
        return [(e.frozen_tier, e.human_verdict) for e in self.events]

    def disagreement_rate(self) -> float:
        """Fraction where the human rejected a CONFIRM/ENTRY or pursued an
        UNCALIBRATED — the loop's core calibration signal."""
        if not self.events:
            return 0.0
        disagreements = 0
        for e in self.events:
            promoted = e.frozen_tier in ("confirm", "entry")
            rejected_promotion = promoted and e.human_verdict == "reject"
            pursued_unpromoted = not promoted and e.human_verdict == "pursue"
            if rejected_promotion or pursued_unpromoted:
                disagreements += 1
        return round(disagreements / len(self.events), 6)

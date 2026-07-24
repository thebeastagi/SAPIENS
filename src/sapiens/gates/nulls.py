"""Phase 1 — the mandatory, logged null layer (the load-bearing stage).

After the recalibration demoted the mechanism/consensus "that's impossible"
kills, **100% of the remaining specificity rests on this layer.** So it is made
a first-class, auditable stage rather than an optional heuristic:

* **Mandatory + logged.** Every candidate records which correct / best-available
  / adversarial null was constructed (drift model, Planck dust map,
  correct-hardware timing, in-vivo pharmacokinetics, container-leach,
  magnitude/flux sieve, ...) and **whether the required external data was
  actually fetched** (y/n). No null constructed -> status UNCALIBRATED, never a
  silent pass.
* **FP-04 (instrument systematic).** "instrument-systematic-not-excluded" gets
  its own explicit state so a loose-fibre / hardware artifact surfaces to the
  human instead of passing as a clean 6-sigma.

This module owns the *record*; family-wide FDR lives in :mod:`.fdr` and is
applied by the pipeline across the whole family.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NullKind(str, Enum):
    """What quality of null was actually constructed for a candidate."""

    CORRECT = "correct"  # the physically correct null (best case)
    BEST_AVAILABLE = "best-available"  # honest best effort given available data
    ADVERSARIAL = "adversarial"  # a deliberately hostile null the signal must beat
    NONE = "none"  # no null constructed -> forces UNCALIBRATED


class InstrumentSystematic(str, Enum):
    """FP-04 explicit state — never fold this into a clean significance."""

    EXCLUDED = "excluded"  # orthogonal check rules out a hardware artifact
    NOT_EXCLUDED = "not-excluded"  # the known blind spot; must surface to human
    NOT_APPLICABLE = "n/a"  # deductive / non-instrument domains


@dataclass(frozen=True)
class NullProvenance:
    """The per-candidate null-provenance record (Phase 1 exit criterion).

    Every shortlisted candidate MUST carry one of these. It is the auditable
    receipt that a real null was constructed and, critically, whether the
    external data the null needs was actually fetched.
    """

    kind: NullKind
    description: str  # e.g. "stellar drift model", "Planck 353 GHz dust map"
    external_data_required: bool
    external_data_fetched: bool
    sigma_under_null: float | None  # significance measured *against this null*
    instrument_systematic: InstrumentSystematic = InstrumentSystematic.NOT_APPLICABLE
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind != NullKind.NONE and not self.description:
            raise ValueError("a constructed null must describe itself")

    @property
    def is_constructed(self) -> bool:
        return self.kind != NullKind.NONE

    @property
    def data_complete(self) -> bool:
        """True unless the null needed external data that was never fetched."""
        return (not self.external_data_required) or self.external_data_fetched

    @property
    def calibratable(self) -> bool:
        """A null can calibrate a claim only if constructed, data-complete, and
        it actually excludes an instrument systematic (FP-04)."""
        return (
            self.is_constructed
            and self.data_complete
            and self.sigma_under_null is not None
            and self.instrument_systematic != InstrumentSystematic.NOT_EXCLUDED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "description": self.description,
            "external_data_required": self.external_data_required,
            "external_data_fetched": self.external_data_fetched,
            "sigma_under_null": self.sigma_under_null,
            "instrument_systematic": self.instrument_systematic.value,
            "data_complete": self.data_complete,
            "calibratable": self.calibratable,
            "notes": self.notes,
        }


def no_null() -> NullProvenance:
    """The explicit 'no null was constructed' record — forces UNCALIBRATED.

    Used so the *absence* of a null is itself logged as a first-class record,
    never a silent pass.
    """
    return NullProvenance(
        kind=NullKind.NONE,
        description="",
        external_data_required=False,
        external_data_fetched=False,
        sigma_under_null=None,
        notes="no null constructed",
    )

"""Adversarial + historical corpus for gaming re-test and the blind harness.

Three families, all constructed **from the spec's descriptions only** (no
ASTRA/GEODISC/BIODISC/SLATE data or code):

* **gaming vectors** — one per welded seam (G-03/05/06/07, FP-06, FP-04, and the
  FP-09 multiplicity trap). Each names the *illegitimate reward* it tries to
  obtain; a leak = it obtains that reward.
* **historical positives** — ~20 genuine landmark discoveries at their t0
  evidence profile (GATES-RECALIBRATION Part 2). "Recovered" = surfaced to the
  human, not hard-killed.
* **decoys / negative controls** — cold fusion, BICEP2, N-rays, polywater,
  OPERA neutrinos, arsenic-life: reproducible-looking claims that a real null
  layer must catch. "Killed" = not promoted to a clean signal / correctly
  flagged.

Each item also carries the key fields (``ground_truth`` / ``expected_verdict`` /
``gates_probed`` / ``how_old_gate_would_kill``) that :mod:`.blind` STRIPS before
scoring — mirroring HOW-TO-PROCEED Phase 3 (the shipped set leaked these inline;
it was never sealed).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .nulls import InstrumentSystematic, NullKind, NullProvenance
from .promotion import GateInputs
from .surprise import LiteratureExpectation, robust_baseline


@dataclass(frozen=True)
class CorpusItem:
    """One benchmark candidate with its (sealable) ground-truth key."""

    inputs: GateInputs
    label: str  # "positive" | "negative"
    # --- key fields (STRIPPED before blind scoring) ---
    ground_truth: str = ""
    expected_verdict: str = ""
    gates_probed: tuple[str, ...] = field(default_factory=tuple)
    how_old_gate_would_kill: str = ""
    illegitimate_reward: str | None = None  # gaming vectors only


def simple_null(
    sigma: float,
    *,
    kind: NullKind = NullKind.CORRECT,
    description: str = "adversarial null",
    external_required: bool = False,
    external_fetched: bool = True,
    instrument: InstrumentSystematic = InstrumentSystematic.NOT_APPLICABLE,
) -> NullProvenance:
    return NullProvenance(
        kind=kind,
        description=description,
        external_data_required=external_required,
        external_data_fetched=external_fetched,
        sigma_under_null=sigma,
        instrument_systematic=instrument,
    )


def null_from_data(
    observed: float,
    dataset: list[float],
    *,
    description: str = "robust MAD/sigma baseline on full dataset",
) -> NullProvenance:
    """Build a null whose sigma is computed on the **full** dataset (G-07).

    A gamer cannot hand-pick a clean subset here: :func:`robust_baseline`
    consumes every point, so the significance is honest by construction.
    """
    baseline = robust_baseline(dataset)
    return NullProvenance(
        kind=NullKind.CORRECT,
        description=f"{description} (n={baseline.n_points})",
        external_data_required=False,
        external_data_fetched=True,
        sigma_under_null=baseline.sigma_of(observed),
    )


# --------------------------------------------------------------------------- #
# Gaming vectors — the Phase-0 exit test (target: 0 leaks)                     #
# --------------------------------------------------------------------------- #
def gaming_vectors() -> list[CorpusItem]:
    items: list[CorpusItem] = []

    # G-03: a trivial UNEXPLAINED number with zero measured surprise trying to
    # earn the anomaly boost simply because nothing explains it.
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-g03-free-anomaly",
                domain="physics",
                provenance_ok=True,
                method_integrity=0.6,
                null=simple_null(3.4, description="noise null"),
                has_mechanism=False,
                has_replication=False,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=10.0,
                literature_expectation=LiteratureExpectation(10.0, 1.0, "prior[whatever]"),
            ),
            label="negative",
            ground_truth="unexplained but unsurprising number",
            expected_verdict="no anomaly boost",
            gates_probed=("G-03",),
            how_old_gate_would_kill="old gate handed +0.10 for mere absence of mechanism",
            illegitimate_reward="anomaly_boost",
        )
    )

    # G-05: a barely-L1 candidate (low promotion score) with has_replication=True
    # and no mechanism, squatting a reserved paradigm-breaker slot.
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-g05-slot-squat",
                domain="physics",
                provenance_ok=False,  # weak provenance -> low promotion score
                method_integrity=0.1,
                null=simple_null(0.5, description="weak null"),
                has_mechanism=False,
                has_replication=True,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=100.0,
                literature_expectation=LiteratureExpectation(0.0, 1.0, "prior[x]"),
            ),
            label="negative",
            ground_truth="barely-L1 squatter",
            expected_verdict="denied reserved slot",
            gates_probed=("G-05",),
            how_old_gate_would_kill="old reserved slot only checked no-mechanism+replication",
            illegitimate_reward="reserved_slot",
        )
    )

    # G-06: high additive score but no L2 holdout -> must NOT reach CALIBRATED.
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-g06-additive-calibrated",
                domain="bio",
                provenance_ok=True,
                method_integrity=1.0,
                null=simple_null(5.0, description="in-vivo PK null"),
                has_mechanism=True,
                has_replication=True,
                orthogonal_confirmation=True,
                holdout_passed=False,  # the crux: holdout NOT passed
                observed_value=5.0,
                literature_expectation=LiteratureExpectation(0.0, 1.0, "prior[y]"),
            ),
            label="negative",
            ground_truth="additive 0.50 reaching CALIBRATED without holdout",
            expected_verdict="UNCALIBRATED",
            gates_probed=("G-06",),
            how_old_gate_would_kill="old additive 0.50 was the admission key",
            illegitimate_reward="calibrated",
        )
    )

    # G-07: significance computed on a hand-picked clean subset. null_from_data
    # recomputes on the FULL dataset -> the inflated sigma collapses below 3.
    # A genuinely NOISY dataset: 9.5 sits at ~1.1 robust-sigma on the full set,
    # but a cherry-picked "clean" subset would make it look like tens of sigma.
    full = [-8.0, -6.0, -5.0, -4.0, -3.0, 3.0, 4.0, 5.0, 6.0, 8.0, 9.5, 0.0]
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-g07-baseline-gaming",
                domain="physics",
                provenance_ok=True,
                method_integrity=0.7,
                null=null_from_data(9.5, full),  # honest full-dataset sigma
                has_mechanism=False,
                has_replication=False,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=9.5,
                literature_expectation=LiteratureExpectation(0.0, 3.0, "prior[z]"),
            ),
            label="negative",
            ground_truth="baseline gamed on a clean subset (real sigma is small)",
            expected_verdict="not entered on gamed sigma",
            gates_probed=("G-07",),
            how_old_gate_would_kill="old baseline excluded the anomaly, inflating sigma",
            illegitimate_reward="entry_via_gamed_baseline",
        )
    )

    # FP-06: a conservation-law violation demanding a boost. Correct null is
    # measurement error; no boost without orthogonal confirmation.
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-fp06-conservation",
                domain="physics",
                provenance_ok=True,
                method_integrity=0.8,
                null=simple_null(7.0, description="energy-balance null"),
                has_mechanism=False,
                has_replication=False,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=42.0,
                literature_expectation=LiteratureExpectation(0.0, 3.0, "conservation[energy]"),
                violates_conservation_law=True,
            ),
            label="negative",
            ground_truth="apparent perpetual-motion / conservation breaker",
            expected_verdict="no boost, no reserved slot until orthogonal confirm",
            gates_probed=("FP-06",),
            how_old_gate_would_kill="old inverted-mechanism rule boosted any unexplained result",
            illegitimate_reward="anomaly_boost",
        )
    )

    # FP-04: a loose-fibre / instrument systematic presenting as a clean 6-sigma.
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-fp04-instrument-systematic",
                domain="physics",
                provenance_ok=True,
                method_integrity=0.9,
                null=simple_null(
                    6.0,
                    description="timing-series null (hardware NOT checked)",
                    instrument=InstrumentSystematic.NOT_EXCLUDED,
                ),
                has_mechanism=False,
                has_replication=False,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=6.0,
                literature_expectation=LiteratureExpectation(0.0, 1.0, "prior[timing]"),
            ),
            label="negative",
            ground_truth="6-sigma from an un-excluded instrument systematic",
            expected_verdict="flagged instrument-systematic, not a clean pass",
            gates_probed=("FP-04",),
            how_old_gate_would_kill="old gate passed it as a clean 6-sigma",
            illegitimate_reward="confirm",
        )
    )

    # FP-09: a per-test 3-sigma among a large family that must fail family FDR.
    items.append(
        CorpusItem(
            inputs=GateInputs(
                candidate_id="gv-fp09-multiplicity",
                domain="physics",
                provenance_ok=True,
                method_integrity=0.6,
                null=simple_null(3.1, description="per-test 3-sigma null"),
                has_mechanism=False,
                has_replication=False,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=3.1,
                literature_expectation=LiteratureExpectation(0.0, 1.0, "prior[le]"),
            ),
            label="negative",
            ground_truth="one 3-sigma among ~1000 looks (look-elsewhere)",
            expected_verdict="rejected by family-wide BH-FDR",
            gates_probed=("FP-09",),
            how_old_gate_would_kill="old 0.05-per-test wall admitted it",
            illegitimate_reward="entry_no_fdr",
        )
    )
    return items


def multiplicity_family_padding(n: int = 40) -> list[GateInputs]:
    """A batch of pure-noise candidates so the FP-09 vector faces a real family.

    Family-wide BH-FDR only bites when the family is large; these are the
    "other looks" the look-elsewhere effect hides in.
    """
    out: list[GateInputs] = []
    for i in range(n):
        out.append(
            GateInputs(
                candidate_id=f"noise-{i:03d}",
                domain="physics",
                provenance_ok=True,
                method_integrity=0.5,
                null=simple_null(1.0 + (i % 5) * 0.2, description="noise null"),
                has_mechanism=False,
                has_replication=False,
                orthogonal_confirmation=False,
                holdout_passed=None,
                observed_value=0.0,
                literature_expectation=None,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Historical positives — t0 evidence profiles (recovery target)               #
# --------------------------------------------------------------------------- #
def _positive(
    cid: str,
    domain: str,
    *,
    sigma: float,
    has_mechanism: bool,
    has_replication: bool,
    orthogonal: bool,
    holdout: bool | None,
    surprise_sigma: float,
    consensus_conflict: bool = False,
    external_required: bool = False,
    external_fetched: bool = True,
    method: float = 0.85,
    truth: str = "",
    kills: str = "",
) -> CorpusItem:
    exp = LiteratureExpectation(0.0, 1.0, f"literature[{cid}]")
    return CorpusItem(
        inputs=GateInputs(
            candidate_id=cid,
            domain=domain,
            provenance_ok=True,
            method_integrity=method,
            null=simple_null(
                sigma,
                description=f"correct null for {cid}",
                external_required=external_required,
                external_fetched=external_fetched,
            ),
            has_mechanism=has_mechanism,
            has_replication=has_replication,
            orthogonal_confirmation=orthogonal,
            holdout_passed=holdout,
            consensus_conflict=consensus_conflict,
            observed_value=surprise_sigma,  # deviation vs exp(0,1) => surprise sigma
            literature_expectation=exp,
        ),
        label="positive",
        ground_truth=truth,
        expected_verdict="recovered (surfaced to human)",
        gates_probed=("S2", "S3", "S4"),
        how_old_gate_would_kill=kills,
    )


def historical_positives() -> list[CorpusItem]:
    return [
        _positive("pulsars-1967", "physics", sigma=9.0, has_mechanism=False,
                  has_replication=False, orthogonal=False, holdout=None,
                  surprise_sigma=8.0, kills="S3/S4/S6 hard-killed at t0"),
        _positive("cmb-1965", "physics", sigma=7.0, has_mechanism=False,
                  has_replication=False, orthogonal=False, holdout=None,
                  surprise_sigma=6.0, kills="S3/S4/S6"),
        _positive("gw150914-2015", "physics", sigma=5.1, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=5.0),
        _positive("quasicrystals-1984", "physics", sigma=8.0, has_mechanism=False,
                  has_replication=False, orthogonal=False, holdout=None,
                  surprise_sigma=7.0, consensus_conflict=True, kills="S4/S3/S6/G5"),
        _positive("dark-energy-1998", "physics", sigma=4.0, has_mechanism=False,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=4.0, kills="S4 mechanism"),
        _positive("flt-1994", "math", sigma=8.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=6.0),
        _positive("poincare-2003", "math", sigma=8.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=6.0),
        _positive("bounded-gaps-2013", "math", sigma=8.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=6.0),
        _positive("mrna-mod-2005", "bio", sigma=4.5, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=True,
                  surprise_sigma=4.0, consensus_conflict=True, kills="G5 consensus"),
        _positive("crispr-2012", "bio", sigma=6.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=True,
                  surprise_sigma=5.0),
        _positive("hpylori-1984", "bio", sigma=4.0, has_mechanism=False,
                  has_replication=False, orthogonal=False, holdout=True,
                  surprise_sigma=4.0, consensus_conflict=True, kills="S4/G5/S6"),
        _positive("prions-1982", "bio", sigma=5.0, has_mechanism=False,
                  has_replication=True, orthogonal=False, holdout=True,
                  surprise_sigma=5.0, consensus_conflict=True, kills="S4/G5"),
        _positive("dna-helix-1953", "bio", sigma=6.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=5.0),
        _positive("transformer-2017", "generic", sigma=6.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=True,
                  surprise_sigma=4.0),
        _positive("alphafold2-2020", "generic", sigma=7.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=True,
                  surprise_sigma=5.0),
        _positive("hopfield-1982", "generic", sigma=4.0, has_mechanism=True,
                  has_replication=True, orthogonal=False, holdout=True,
                  surprise_sigma=3.5),
        _positive("continental-drift-1912", "generic", sigma=4.0, has_mechanism=False,
                  has_replication=True, orthogonal=False, holdout=None,
                  surprise_sigma=4.0, consensus_conflict=True, kills="S4/G5"),
        _positive("chicxulub-1980", "generic", sigma=5.0, has_mechanism=True,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=4.0, consensus_conflict=True),
        _positive("exoplanet-51peg-1995", "physics", sigma=4.5, has_mechanism=False,
                  has_replication=True, orthogonal=True, holdout=None,
                  surprise_sigma=4.0, kills="S4/S3"),
        _positive("dark-matter-1970s", "generic", sigma=5.0, has_mechanism=False,
                  has_replication=True, orthogonal=False, holdout=None,
                  surprise_sigma=5.0, consensus_conflict=True, kills="S4/S3/G5"),
    ]


# --------------------------------------------------------------------------- #
# Decoys / negative controls — the null layer must catch these                #
# --------------------------------------------------------------------------- #
def decoys() -> list[CorpusItem]:
    def _neg(cid, domain, null, **kw):
        exp = kw.pop("exp", LiteratureExpectation(0.0, 1.0, f"literature[{cid}]"))
        return CorpusItem(
            inputs=GateInputs(
                candidate_id=cid,
                domain=domain,
                provenance_ok=kw.pop("provenance_ok", True),
                method_integrity=kw.pop("method", 0.5),
                null=null,
                has_mechanism=kw.pop("has_mechanism", False),
                has_replication=kw.pop("has_replication", False),
                orthogonal_confirmation=kw.pop("orthogonal", False),
                holdout_passed=kw.pop("holdout", None),
                consensus_conflict=kw.pop("consensus_conflict", False),
                observed_value=kw.pop("observed", 0.0),
                literature_expectation=exp,
                violates_conservation_law=kw.pop("violates", False),
            ),
            label="negative",
            ground_truth=kw.pop("truth", ""),
            expected_verdict="killed / flagged, not a clean signal",
            gates_probed=kw.pop("gates_probed", ("S5",)),
            how_old_gate_would_kill=kw.pop("kills", ""),
        )

    return [
        # Cold fusion: fails replication; its "excess heat" vanishes under the
        # correct calorimetry null.
        _neg("cold-fusion-1989", "physics",
             simple_null(1.2, description="calorimetry null (excess heat)"),
             truth="non-reproducible excess heat", gates_probed=("S5",),
             kills="correctly fails replication over time"),
        # BICEP2: required Planck dust map never fetched -> UNCALIBRATED.
        _neg("bicep2-2014", "physics",
             simple_null(5.0, description="Planck 353 GHz dust map",
                         external_required=True, external_fetched=False),
             observed=5.0, truth="dust mistaken for primordial B-modes",
             gates_probed=("FP-01", "null-data"),
             kills="dust-map null data was never fetched"),
        # N-rays: pure observer artifact; no signal under a blinded null.
        _neg("n-rays-1903", "physics",
             simple_null(0.8, description="blinded-observer null"),
             truth="observer-expectation artifact",
             kills="vanishes under a blinded null"),
        # Polywater: container leaching; correct null is contamination.
        _neg("polywater-1969", "bio",
             simple_null(1.0, description="container-leach contamination null"),
             truth="silica leached from glass", gates_probed=("null-contamination",),
             kills="contamination null explains it"),
        # OPERA faster-than-light neutrinos: loose-fibre timing systematic.
        _neg("opera-neutrino-2011", "physics",
             simple_null(6.0, description="GPS timing null (fibre NOT checked)",
                         instrument=InstrumentSystematic.NOT_EXCLUDED),
             observed=6.0, violates=True,
             truth="loose fibre-optic + conservation (v>c) violation",
             gates_probed=("FP-04", "FP-06"),
             kills="instrument-systematic + conservation guard"),
        # Arsenic-life GFAJ-1: fails independent replication.
        _neg("arsenic-life-2010", "bio",
             simple_null(2.0, description="phosphate-contamination null"),
             has_mechanism=True, truth="arsenate-DNA not reproduced",
             gates_probed=("S5",), kills="independent replication failed"),
        # Superluminal / perpetual-motion generic conservation breaker.
        _neg("free-energy-device", "physics",
             simple_null(4.0, description="energy-balance null"),
             observed=50.0, violates=True,
             exp=LiteratureExpectation(0.0, 3.0, "conservation[energy]"),
             truth="over-unity claim", gates_probed=("FP-06",),
             kills="conservation guard: correct null is measurement error"),
        # A high-sigma but methodologically rotten pipeline (leakage).
        _neg("leakage-artifact", "generic",
             simple_null(6.0, description="null with train/test leakage"),
             method=0.05, holdout=False, observed=6.0,
             truth="train/test leakage inflates the score",
             gates_probed=("G-06", "L2"), kills="no L2 holdout -> UNCALIBRATED"),
    ]


def full_corpus() -> list[CorpusItem]:
    """Positives + decoys (the blind-scored set). Gaming vectors are separate."""
    return historical_positives() + decoys()

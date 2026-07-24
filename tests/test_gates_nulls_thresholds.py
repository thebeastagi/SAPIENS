"""Phase 1 null-provenance records (+FP-04) and Phase 2 thresholds (+B-02/03/05/06)."""

import pytest

from sapiens.gates.devils_advocate import devils_advocate_permutation, pearson_r
from sapiens.gates.nulls import (
    InstrumentSystematic,
    NullKind,
    NullProvenance,
    no_null,
)
from sapiens.gates.thresholds import (
    Domain,
    ThresholdPolicy,
    adaptive_ci_floor,
    confirm_decision,
    degree_of_calibration,
)


def test_null_provenance_records_external_fetch():
    n = NullProvenance(
        kind=NullKind.CORRECT,
        description="Planck 353 GHz dust map",
        external_data_required=True,
        external_data_fetched=False,
        sigma_under_null=5.0,
    )
    assert not n.data_complete  # required data never fetched
    assert not n.calibratable  # so it cannot calibrate a claim
    assert "external_data_fetched" in n.to_dict()


def test_fp04_instrument_systematic_blocks_calibration():
    n = NullProvenance(
        kind=NullKind.CORRECT,
        description="timing series",
        external_data_required=False,
        external_data_fetched=True,
        sigma_under_null=6.0,
        instrument_systematic=InstrumentSystematic.NOT_EXCLUDED,
    )
    assert not n.calibratable  # a 6-sigma with an un-excluded systematic is NOT clean


def test_no_null_is_not_calibratable():
    n = no_null()
    assert n.kind == NullKind.NONE
    assert not n.is_constructed
    assert not n.calibratable


def test_b02_adaptive_ci_floor_beats_fixed_070():
    # 95%-majority class: a fixed 0.70 is below chance; adaptive floor is above it.
    assert adaptive_ci_floor(0.95, margin=0.03) > 0.95
    assert adaptive_ci_floor(0.5, margin=0.15) == pytest.approx(0.65)
    assert adaptive_ci_floor(0.99, margin=0.10) < 1.0  # clamped


def test_b05_degree_of_calibration_is_continuous():
    assert degree_of_calibration(0, 0) == 0.0
    assert degree_of_calibration(5, 5) == 1.0
    mid = degree_of_calibration(2, 3)
    assert 0.0 < mid < 1.0  # no hard 0.50 cliff


def test_b03_hash_commit_is_deterministic_and_binds_run():
    p = ThresholdPolicy()
    assert p.hash_commit("run-a") == p.hash_commit("run-a")
    assert p.hash_commit("run-a") != p.hash_commit("run-b")
    assert len(p.hash_commit("x")) == 64


def test_confirm_bars_are_domain_specific():
    p = ThresholdPolicy()
    # physics: 5-sigma.
    assert confirm_decision(Domain.PHYSICS, sigma=5.0, fdr_rejected=True,
                            orthogonal_replication=False, proof_checked=False,
                            policy=p).confirmed
    assert not confirm_decision(Domain.PHYSICS, sigma=4.0, fdr_rejected=True,
                               orthogonal_replication=True, proof_checked=True,
                               policy=p).confirmed
    # bio: FDR + orthogonal replication.
    assert confirm_decision(Domain.BIO, sigma=3.0, fdr_rejected=True,
                           orthogonal_replication=True, proof_checked=False,
                           policy=p).confirmed
    assert not confirm_decision(Domain.BIO, sigma=9.0, fdr_rejected=True,
                               orthogonal_replication=False, proof_checked=False,
                               policy=p).confirmed
    # math: formal proof-check.
    assert confirm_decision(Domain.MATH, sigma=None, fdr_rejected=False,
                           orthogonal_replication=False, proof_checked=True,
                           policy=p).confirmed


def test_b06_devils_advocate_permutation():
    # Signal perfectly tracks a confound -> guard fires, and it does NOT pass.
    confound = [float(i) for i in range(20)]
    signal = [2 * x + 1 for x in confound]  # r == 1.0
    assert pearson_r(signal, confound) == pytest.approx(1.0)
    res = devils_advocate_permutation(signal, confound, seed=1, n_permutations=500)
    assert res.triggered
    assert not res.passed  # confound fully explains it
    # Weak correlation -> guard never fires, passes trivially.
    weak = devils_advocate_permutation(
        [1.0, 2.0, 1.5, 3.0, 2.5], [9.0, 1.0, 5.0, 2.0, 8.0], seed=1
    )
    assert not weak.triggered and weak.passed

"""Phase 0/1 statistical primitives: robust baseline (G-07), surprise (G-03),
BH-FDR + sigma conversions (Phase 1/2)."""

import math

import pytest

from sapiens.gates.fdr import benjamini_hochberg, pvalue_to_sigma, sigma_to_pvalue
from sapiens.gates.surprise import (
    LiteratureExpectation,
    is_surprising,
    measured_surprise,
    robust_baseline,
)


def test_sigma_pvalue_roundtrip():
    for s in (1.0, 3.0, 5.0, 6.5):
        assert pvalue_to_sigma(sigma_to_pvalue(s)) == pytest.approx(s, abs=1e-3)
    assert sigma_to_pvalue(3) == pytest.approx(0.0027, abs=1e-4)
    assert sigma_to_pvalue(5) == pytest.approx(5.7e-7, rel=0.05)


def test_g07_robust_baseline_uses_full_dataset():
    # A noisy full dataset: a 9.5 outlier is only ~1 robust-sigma; a cherry-
    # picked clean subset would inflate that to tens of sigma (the G-07 exploit).
    full = [-8, -6, -5, -4, -3, 3, 4, 5, 6, 8, 9.5, 0]
    b_full = robust_baseline(full)
    assert b_full.n_points == len(full)  # the anti-gaming receipt
    assert b_full.sigma_of(9.5) < 3.0
    clean = [0, 0.1, -0.1, 0.2, -0.2, 0.05]
    assert robust_baseline(clean).sigma_of(9.5) > 20.0


def test_robust_baseline_rejects_empty():
    with pytest.raises(ValueError):
        robust_baseline([])


def test_g03_surprise_requires_measured_contradiction():
    exp = LiteratureExpectation(expected=10.0, expected_sigma=1.0, citation="lit[x]")
    # An unexplained-but-unsurprising number (matches expectation) => 0 surprise.
    assert measured_surprise(10.0, exp) == pytest.approx(0.0)
    assert not is_surprising(10.0, exp, floor_sigma=3.0)
    # A measurable contradiction is surprising.
    assert measured_surprise(15.0, exp) == pytest.approx(5.0)
    assert is_surprising(15.0, exp, floor_sigma=3.0)
    # Absence of a cited expectation is NOT surprise.
    assert measured_surprise(1e9, None) == 0.0
    assert not is_surprising(1e9, None)


def test_literature_expectation_requires_citation():
    with pytest.raises(ValueError):
        LiteratureExpectation(0.0, 1.0, "")
    with pytest.raises(ValueError):
        LiteratureExpectation(0.0, 0.0, "lit")


def test_family_wide_bh_fdr_controls_multiplicity():
    # One genuine 4-sigma signal buried among many null looks.
    pvals = [sigma_to_pvalue(4.0)] + [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.3, 0.55]
    res = benjamini_hochberg(pvals, q=0.05)
    assert res[0].rejected  # the real one survives family FDR
    assert sum(r.rejected for r in res) == 1  # the noise does not
    # q-values are monotone and in-order with input.
    assert all(0.0 <= r.qvalue <= 1.0 for r in res)


def test_bh_look_elsewhere_kills_lone_three_sigma():
    # A single per-test 3-sigma among ~1000 pure looks must NOT survive.
    pvals = [sigma_to_pvalue(3.1)] + [0.5] * 999
    res = benjamini_hochberg(pvals, q=0.05)
    assert not res[0].rejected


def test_bh_empty_and_bounds():
    assert benjamini_hochberg([], 0.05) == []
    with pytest.raises(ValueError):
        benjamini_hochberg([0.1], 0.0)
    assert math.isfinite(sigma_to_pvalue(0.0))

"""Integration: decoupled ENTRY/RANK/CONFIRM tiers, family FDR, the FP-06 tier
block, and the Phase-0 exit criterion (7 gaming vectors -> 0 leaks)."""

from sapiens.gates.corpus import gaming_vectors, historical_positives
from sapiens.gates.criteria import gaming_leaked, run_gaming_retest
from sapiens.gates.nulls import NullKind, NullProvenance
from sapiens.gates.pipeline import evaluate_family
from sapiens.gates.promotion import GateInputs
from sapiens.gates.surprise import LiteratureExpectation
from sapiens.gates.thresholds import ThresholdPolicy, Tier


def _null(sigma, **kw):
    return NullProvenance(
        kind=NullKind.CORRECT,
        description="null",
        external_data_required=kw.get("req", False),
        external_data_fetched=kw.get("fetched", True),
        sigma_under_null=sigma,
    )


def test_entry_requires_sigma_and_family_fdr():
    # A 6-sigma physics candidate in a small clean family enters and confirms.
    strong = GateInputs(
        candidate_id="strong", domain="physics", provenance_ok=True,
        method_integrity=0.9, null=_null(6.0), has_mechanism=True,
        has_replication=True, orthogonal_confirmation=True, holdout_passed=None,
        observed_value=6.0, literature_expectation=LiteratureExpectation(0.0, 1.0, "l"),
    )
    res = evaluate_family([strong], run_id="t")
    o = res.outcomes[0]
    assert o.entered
    assert o.tier == Tier.CONFIRM
    assert res.policy_hash  # thresholds hash-committed


def test_conservation_violation_never_enters_without_orthogonal():
    breaker = GateInputs(
        candidate_id="oa", domain="physics", provenance_ok=True,
        method_integrity=0.8, null=_null(7.0), has_mechanism=False,
        has_replication=False, orthogonal_confirmation=False, holdout_passed=None,
        observed_value=42.0, violates_conservation_law=True,
        literature_expectation=LiteratureExpectation(0.0, 3.0, "conservation"),
    )
    o = evaluate_family([breaker], run_id="t").outcomes[0]
    assert not o.entered
    assert o.tier == Tier.UNCALIBRATED
    assert any("FP-06" in r for r in o.confirm_reasons)


def test_shortlist_is_bounded_and_reserves_paradigm_breakers():
    fam = evaluate_family(
        [it.inputs for it in historical_positives()],
        policy=ThresholdPolicy(top_k=10),
        run_id="hist",
    )
    assert len(fam.shortlist) <= 10  # bounded human load
    # At least one reserved paradigm-breaker slot is represented.
    assert any(o.reserved_slot for o in fam.shortlist)


def test_phase0_exit_zero_gaming_leaks():
    retest = run_gaming_retest()
    assert retest.checked == 7
    assert retest.leaks == ()  # 0 leaks (was 4 before the patches)
    assert retest.clean


def test_each_gaming_vector_denied_its_reward():
    # Per-candidate check that each seam denies exactly its illegitimate reward.
    vectors = {v.inputs.candidate_id: v for v in gaming_vectors()}
    per = [v for v in vectors.values() if v.inputs.candidate_id != "gv-fp09-multiplicity"]
    outcomes = {
        o.candidate_id: o
        for o in evaluate_family([v.inputs for v in per], run_id="g").outcomes
    }
    for cid, o in outcomes.items():
        reward = vectors[cid].illegitimate_reward
        assert not gaming_leaked(vectors[cid], o), f"{cid} leaked {reward}"

import pytest

from sapiens.models import Evidence
from sapiens.validation import (
    GateVerdict,
    HoldoutProtocol,
    ValidationGates,
    check_internal_consistency,
    check_replication,
    synthetic_holdout_protocol,
)

PROTOCOL = synthetic_holdout_protocol()


def ev(eid, kind, dataset, seed, score, passed=True, protocol="proto-v1"):
    return Evidence(eid, "cand-x", kind, passed, protocol, dataset, seed, score)


class TestGateVerdictCoherence:
    def test_passing_verdict_has_no_reasons(self):
        with pytest.raises(ValueError):
            GateVerdict("g", True, ("reason",))

    def test_failing_verdict_must_explain(self):
        with pytest.raises(ValueError):
            GateVerdict("g", False, ())


class TestHoldoutProtocolCoherence:
    def test_self_leaking_protocol_rejected(self):
        with pytest.raises(ValueError, match="self-leaking"):
            HoldoutProtocol("bad", ("train",), ("train",))

    def test_empty_splits_rejected(self):
        with pytest.raises(ValueError):
            HoldoutProtocol("bad", (), ("holdout",))


class TestInternalConsistency:
    def test_honest_evidence_passes(self):
        evidence = (
            ev("a", "internal", "synthetic-train", 1, 0.9),
            ev("b", "internal", "synthetic-train", 2, 0.85),
        )
        assert check_internal_consistency(evidence).passed

    def test_no_evidence_fails(self):
        verdict = check_internal_consistency(())
        assert not verdict.passed
        assert "no internal evidence" in verdict.reasons[0]

    def test_missing_score_fails(self):
        verdict = check_internal_consistency(
            (ev("a", "internal", "synthetic-train", 1, None),)
        )
        assert not verdict.passed
        assert "no score" in verdict.reasons[0]

    def test_nondeterministic_rerun_fails(self):
        evidence = (
            ev("a", "internal", "synthetic-train", 7, 0.9, passed=True),
            ev("b", "internal", "synthetic-train", 7, 0.2, passed=False),
        )
        verdict = check_internal_consistency(evidence)
        assert not verdict.passed
        assert any("non-deterministic" in reason for reason in verdict.reasons)

    def test_deterministic_rerun_agrees_passes(self):
        evidence = (
            ev("a", "internal", "synthetic-train", 7, 0.9),
            ev("b", "internal", "synthetic-train", 7, 0.9),
        )
        assert check_internal_consistency(evidence).passed

    def test_degenerate_constant_scores_fail(self):
        evidence = tuple(
            ev(f"e{seed}", "internal", "synthetic-train", seed, 0.5) for seed in (1, 2, 3)
        )
        verdict = check_internal_consistency(evidence)
        assert not verdict.passed
        assert any("degenerate" in reason for reason in verdict.reasons)

    def test_two_seeds_not_enough_for_degenerate_check(self):
        evidence = tuple(
            ev(f"e{seed}", "internal", "synthetic-train", seed, 0.5) for seed in (1, 2)
        )
        assert check_internal_consistency(evidence).passed

    def test_other_kinds_ignored(self):
        evidence = (ev("a", "replication", "synthetic-holdout", 1, 0.9),)
        verdict = check_internal_consistency(evidence)
        assert not verdict.passed  # no internal items at all


class TestReplicationGate:
    def honest(self):
        internal = (ev("i1", "internal", "synthetic-train", 1, 0.9),)
        replication = (
            ev("r1", "replication", "synthetic-holdout", 2, 0.88),
            ev("r2", "replication", "synthetic-holdout", 3, 0.91),
        )
        return internal, replication

    def test_honest_holdout_passes(self):
        internal, replication = self.honest()
        assert check_replication(internal, replication, PROTOCOL).passed

    def test_no_replication_evidence_fails(self):
        internal, _ = self.honest()
        verdict = check_replication(internal, (), PROTOCOL)
        assert not verdict.passed

    def test_undeclared_train_dataset_fails(self):
        internal = (ev("i1", "internal", "secret-train", 1, 0.9),)
        _, replication = self.honest()
        verdict = check_replication(internal, replication, PROTOCOL)
        assert not verdict.passed
        assert any("undeclared dataset" in reason for reason in verdict.reasons)

    def test_non_holdout_replication_dataset_fails(self):
        internal = (ev("i1", "internal", "synthetic-train", 1, 0.9),)
        replication = (ev("r1", "replication", "synthetic-train", 2, 0.9),)
        verdict = check_replication(internal, replication, PROTOCOL)
        assert not verdict.passed
        assert any("non-holdout dataset" in reason for reason in verdict.reasons)

    def test_dataset_collision_is_leakage(self):
        internal = (ev("i1", "internal", "synthetic-train", 1, 0.9),)
        replication = (ev("r1", "replication", "synthetic-train", 2, 0.9),)
        verdict = check_replication(internal, replication, PROTOCOL)
        assert any("leakage" in reason for reason in verdict.reasons)

    def test_dataset_seed_pair_reuse_is_leakage(self):
        internal = (ev("i1", "internal", "synthetic-train", 7, 0.9),)
        replication = (ev("r1", "replication", "synthetic-train", 7, 0.9),)
        verdict = check_replication(internal, replication, PROTOCOL)
        assert any("reuse" in reason for reason in verdict.reasons)

    def test_same_seed_different_dataset_is_not_leakage(self):
        # Numeric seed overlap across disjoint datasets is how the shipped
        # synthetic adapters derive independent holdout noise; it must pass.
        internal = (ev("i1", "internal", "synthetic-train", 7, 0.9),)
        replication = (ev("r1", "replication", "synthetic-holdout", 7, 0.88),)
        assert check_replication(internal, replication, PROTOCOL).passed

    def test_pass_fraction_enforced(self):
        internal = (ev("i1", "internal", "synthetic-train", 1, 0.9),)
        replication = (
            ev("r1", "replication", "synthetic-holdout", 2, 0.9, passed=True),
            ev("r2", "replication", "synthetic-holdout", 3, 0.2, passed=False),
        )
        verdict = check_replication(internal, replication, PROTOCOL)
        assert not verdict.passed
        assert any("pass fraction" in reason for reason in verdict.reasons)
        relaxed = check_replication(
            internal, replication, PROTOCOL, min_pass_fraction=0.5
        )
        assert relaxed.passed

    def test_invalid_threshold_rejected(self):
        internal, replication = self.honest()
        with pytest.raises(ValueError):
            check_replication(internal, replication, PROTOCOL, min_pass_fraction=0.0)


def test_validation_gates_protocol_lookup():
    gates = ValidationGates({"synthetic-x": PROTOCOL})
    assert gates.protocol_for("synthetic-x") is PROTOCOL
    assert gates.protocol_for("unknown") is None

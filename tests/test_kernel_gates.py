"""Kernel + Phase-2 validation gates integration."""

import pytest

from sapiens.adapters import SyntheticLinearAdapter
from sapiens.budget import ExecutionContext
from sapiens.kernel import DiscoveryKernel
from sapiens.ledger import EvidenceLedger
from sapiens.models import AdapterManifest, Candidate, Evidence, EvidenceLevel
from sapiens.validation import ValidationGates, synthetic_holdout_protocol


def ctx():
    return ExecutionContext(max_steps=10, max_seconds=10.0)


def gated_kernel(tmp_path, adapter_domain, protocol=None):
    gates = ValidationGates({adapter_domain: protocol or synthetic_holdout_protocol()})
    return DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"), validation=gates)


def test_synthetic_adapter_promotes_through_gates(tmp_path):
    adapter = SyntheticLinearAdapter()
    kernel = gated_kernel(tmp_path, adapter.manifest.domain)
    candidate = adapter.propose(seed=5, limit=1)[0]
    kernel.register(candidate)
    assert kernel.validate_next(adapter, candidate, seed=40, context=ctx()) == EvidenceLevel.L1
    assert kernel.validate_next(adapter, candidate, seed=41, context=ctx()) == EvidenceLevel.L2
    assert all(verdict.passed for verdict in kernel.gate_log)


class LeakyReplicationAdapter:
    """Replication 'evidence' produced on the training dataset itself."""

    manifest = AdapterManifest("leaky", "1", "leaky-domain", ("x",))

    def propose(self, *, seed: int, limit: int):
        return (Candidate("cand-leaky", "leaky-domain", "leaks holdout"),)

    def validate(self, candidate, *, stage: str, seed: int, context):
        context.checkpoint()
        dataset = "synthetic-train"  # same dataset for every stage: leakage
        return (
            Evidence(
                f"ev-{stage}", candidate.candidate_id, stage, True, "leaky-v1", dataset, seed, 0.9
            ),
        )

    def import_structure(self, structure, *, candidate_id: str):
        return Candidate(candidate_id, "leaky-domain", "claim")


def test_kernel_blocks_l2_on_dataset_leakage(tmp_path):
    adapter = LeakyReplicationAdapter()
    kernel = gated_kernel(tmp_path, "leaky-domain")
    candidate = adapter.propose(seed=1, limit=1)[0]
    kernel.register(candidate)
    assert kernel.validate_next(adapter, candidate, seed=40, context=ctx()) == EvidenceLevel.L1
    assert kernel.validate_next(adapter, candidate, seed=41, context=ctx()) == EvidenceLevel.L1
    assert kernel.ledger.state("cand-leaky").level == EvidenceLevel.L1
    failing = [v for v in kernel.gate_log if not v.passed]
    assert failing and any("leakage" in r for r in failing[-1].reasons)


class NonDeterministicAdapter:
    """Same seed, different outcomes across calls: fails the determinism check."""

    manifest = AdapterManifest("flaky", "1", "flaky-domain", ("x",))

    def __init__(self):
        self.calls = 0

    def propose(self, *, seed: int, limit: int):
        return (Candidate("cand-flaky", "flaky-domain", "unstable signal"),)

    def validate(self, candidate, *, stage: str, seed: int, context):
        context.checkpoint()
        self.calls += 1
        score = 0.1 if self.calls == 1 else 0.9  # first attempt fails, then "recovers"
        return (
            Evidence(
                f"ev-{self.calls}",
                candidate.candidate_id,
                stage,
                score > 0.5,
                "flaky-v1",
                "synthetic-train",
                seed,
                score,
            ),
        )

    def import_structure(self, structure, *, candidate_id: str):
        return Candidate(candidate_id, "flaky-domain", "claim")


def test_kernel_blocks_l1_on_nondeterminism(tmp_path):
    adapter = NonDeterministicAdapter()
    kernel = gated_kernel(tmp_path, "flaky-domain")
    candidate = adapter.propose(seed=1, limit=1)[0]
    kernel.register(candidate)
    # Attempt 1 records failing evidence → stays L0. Attempt 2 reruns the same
    # (protocol, dataset, seed) but reports a contradictory passing outcome, so
    # the determinism check must block promotion even though evidence passed.
    assert kernel.validate_next(adapter, candidate, seed=42, context=ctx()) == EvidenceLevel.L0
    assert kernel.validate_next(adapter, candidate, seed=42, context=ctx()) == EvidenceLevel.L0
    assert kernel.ledger.state("cand-flaky").level == EvidenceLevel.L0
    failing = [v for v in kernel.gate_log if not v.passed]
    assert failing
    assert any("non-deterministic" in reason for reason in failing[-1].reasons)


def test_kernel_refuses_l2_without_declared_protocol(tmp_path):
    adapter = SyntheticLinearAdapter()
    gates = ValidationGates({})  # configured but declares nothing
    kernel = DiscoveryKernel(
        EvidenceLedger(tmp_path / "events.jsonl"), validation=gates
    )
    candidate = adapter.propose(seed=5, limit=1)[0]
    kernel.register(candidate)
    assert kernel.validate_next(adapter, candidate, seed=40, context=ctx()) == EvidenceLevel.L1
    with pytest.raises(ValueError, match="no holdout protocol"):
        kernel.validate_next(adapter, candidate, seed=41, context=ctx())


def test_kernel_without_gates_keeps_phase1_behaviour(tmp_path):
    adapter = LeakyReplicationAdapter()  # would fail gates; no gates configured
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"))
    candidate = adapter.propose(seed=1, limit=1)[0]
    kernel.register(candidate)
    assert kernel.validate_next(adapter, candidate, seed=40, context=ctx()) == EvidenceLevel.L1
    assert kernel.validate_next(adapter, candidate, seed=41, context=ctx()) == EvidenceLevel.L2
    assert kernel.gate_log == []

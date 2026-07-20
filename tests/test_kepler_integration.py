"""Phase-4 integration: registry tier, full kernel climb, bridge L0 reset."""

import pytest

from sapiens.adapters import (
    KeplerPhotometryAdapter,
    SyntheticThresholdAdapter,
    kepler_holdout_protocol,
)
from sapiens.bridge import transfer
from sapiens.budget import ExecutionContext
from sapiens.kernel import DiscoveryKernel
from sapiens.ledger import EvidenceLedger
from sapiens.models import EvidenceLevel
from sapiens.registry import AdapterRegistry, TrustTier
from sapiens.reviewers import reference_panel
from sapiens.validation import ValidationGates


@pytest.fixture(scope="module")
def adapter():
    return KeplerPhotometryAdapter()


@pytest.fixture(scope="module")
def candidate(adapter):
    return adapter.propose(seed=0, limit=1)[0]


def ctx():
    return ExecutionContext(max_steps=30, max_seconds=90.0)


class TestRegistryTier:
    def test_auto_tiers_core_from_manifest_facts(self, adapter):
        registry = AdapterRegistry()
        assert registry.validate_adapter(adapter) == TrustTier.CORE
        assert not registry.requires_isolation(adapter)

    def test_explicit_core_registration(self, adapter):
        registry = AdapterRegistry()
        registry.register(adapter, TrustTier.CORE)
        assert registry.tier_of(adapter) == TrustTier.CORE

    def test_synthetic_registration_rejected_for_real_data(self, adapter):
        registry = AdapterRegistry()
        with pytest.raises(ValueError, match="real data sources"):
            registry.register(adapter, TrustTier.SYNTHETIC)


def test_full_climb_to_l3_with_gates_and_panel(tmp_path, adapter, candidate):
    """The capstone: real public data through every shipped gate."""
    gates = ValidationGates({adapter.manifest.domain: kepler_holdout_protocol()})
    panel = reference_panel(adapter.manifest.vocabulary, kepler_holdout_protocol())
    kernel = DiscoveryKernel(
        EvidenceLedger(tmp_path / "events.jsonl"), validation=gates, panel=panel
    )
    kernel.register(candidate)
    assert kernel.validate_next(adapter, candidate, seed=40, context=ctx()) == EvidenceLevel.L1
    assert kernel.validate_next(adapter, candidate, seed=41, context=ctx()) == EvidenceLevel.L2
    assert kernel.validate_next(adapter, candidate, seed=42, context=ctx()) == EvidenceLevel.L3
    # L4 stays human-gated: the automated kernel refuses to go further.
    with pytest.raises(ValueError, match="human-gated"):
        kernel.validate_next(adapter, candidate, seed=43, context=ctx())
    assert all(verdict.passed for verdict in kernel.gate_log)
    assert kernel.panel_log[-1].outcome.value == "approved"
    assert kernel.ledger.verify()


def test_climb_without_gates_or_panel_also_promotes(tmp_path, adapter, candidate):
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"))
    kernel.register(candidate)
    for seed in (40, 41, 42):
        reached = kernel.validate_next(adapter, candidate, seed=seed, context=ctx())
    assert reached == EvidenceLevel.L3


def test_transfer_into_synthetic_domain_resets_to_l0(adapter, candidate):
    target = SyntheticThresholdAdapter()
    imported, level, envelope = transfer(
        candidate, EvidenceLevel.L3, target, candidate_id="kepler-transfer-1"
    )
    assert level == EvidenceLevel.L0  # the iron rule, re-verified on real data
    assert imported.domain == target.manifest.domain
    assert imported.parent_id == candidate.candidate_id
    assert envelope.source_level_discarded == EvidenceLevel.L3

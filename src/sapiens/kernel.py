"""Minimal domain-neutral orchestration boundary."""

from __future__ import annotations

from .adapter import DomainAdapter
from .budget import ExecutionContext
from .isolation import run_validate_isolated
from .ledger import EvidenceLedger
from .models import Candidate, EvidenceLevel
from .registry import AdapterRegistry, TrustTier

_STAGE_BY_LEVEL = {
    EvidenceLevel.L1: "internal",
    EvidenceLevel.L2: "replication",
    EvidenceLevel.L3: "review",
}


class DiscoveryKernel:
    def __init__(self, ledger: EvidenceLedger, registry: AdapterRegistry | None = None) -> None:
        self.ledger = ledger
        self.registry = registry if registry is not None else AdapterRegistry()

    def register(self, candidate: Candidate, *, transferred_from: str | None = None) -> None:
        self.ledger.record_candidate(candidate.candidate_id, transferred_from=transferred_from)

    def validate_next(
        self,
        adapter: DomainAdapter,
        candidate: Candidate,
        *,
        seed: int,
        context: ExecutionContext,
    ) -> EvidenceLevel:
        tier = self.registry.validate_adapter(adapter)
        if candidate.domain != adapter.manifest.domain:
            raise ValueError("candidate domain does not match adapter")
        current = self.ledger.state(candidate.candidate_id).level
        if current >= EvidenceLevel.L3:
            raise ValueError("automated kernel cannot promote beyond L3; L4 stays human-gated")
        target = EvidenceLevel(current + 1)
        stage = _STAGE_BY_LEVEL[target]
        if tier == TrustTier.UNTRUSTED:
            # Third-party code never runs in this process. A contained
            # isolation failure yields no evidence and no promotion.
            evidence = run_validate_isolated(
                adapter, candidate, stage=stage, seed=seed, context=context
            )
        else:
            evidence = adapter.validate(candidate, stage=stage, seed=seed, context=context)
        refs: list[str] = []
        for item in evidence:
            if item.candidate_id != candidate.candidate_id or item.kind != stage:
                raise ValueError("adapter returned mis-scoped evidence")
            self.ledger.record_evidence(item)
            if item.passed:
                refs.append(item.evidence_id)
        if not refs:
            return current
        self.ledger.promote(candidate.candidate_id, target, tuple(refs))
        return target

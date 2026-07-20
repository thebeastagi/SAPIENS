"""Validation framework v1 (Phase 2): automated L0→L2 gates.

Two gate families, both pure functions over recorded evidence:

- **Internal consistency (L1)**: statistical sanity checks — scores present
  and in range, determinism (identical protocol/dataset/seed reruns must
  agree), degenerate-distribution rejection (constant scores across
  independent seeds carry no information).
- **Replication (L2)**: a declared :class:`HoldoutProtocol` per domain plus
  explicit leakage controls — replication evidence must come from declared
  holdout datasets, and any dataset collision or (dataset, seed) pair reuse
  across the train/holdout boundary rejects the gate.

Gates return :class:`GateVerdict` with explicit reasons; they never fabricate
or mutate evidence. Wiring them into promotion is the kernel's job
(``DiscoveryKernel(validation=...)``); here they stay inspectable and testable
in isolation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .models import Evidence

INTERNAL_KIND = "internal"
REPLICATION_KIND = "replication"


@dataclass(frozen=True)
class GateVerdict:
    gate: str
    passed: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.passed and self.reasons:
            raise ValueError("a passing verdict carries no failure reasons")
        if not self.passed and not self.reasons:
            raise ValueError("a failing verdict must say why")


@dataclass(frozen=True)
class HoldoutProtocol:
    """Declared train/holdout split for a domain. Leakage controls key off this."""

    name: str
    train_datasets: tuple[str, ...]
    holdout_datasets: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.train_datasets or not self.holdout_datasets:
            raise ValueError("holdout protocol requires a name and both dataset splits")
        collision = set(self.train_datasets) & set(self.holdout_datasets)
        if collision:
            raise ValueError(f"holdout protocol is self-leaking: {sorted(collision)}")


def _scores(items: list[Evidence]) -> list[float]:
    return [item.score for item in items if item.score is not None]  # type: ignore[misc]


def check_internal_consistency(evidence: tuple[Evidence, ...]) -> GateVerdict:
    """L1 gate: statistical sanity over internal evidence for one candidate."""
    gate = "L1-internal-consistency"
    reasons: list[str] = []
    items = [item for item in evidence if item.kind == INTERNAL_KIND]
    if not items:
        return GateVerdict(gate, False, ("no internal evidence to validate",))
    for item in items:
        if item.score is None:
            reasons.append(f"evidence {item.evidence_id} carries no score")
        elif not 0.0 <= item.score <= 1.0:
            reasons.append(f"evidence {item.evidence_id} score out of range")
    # Determinism: reruns of the identical protocol/dataset/seed must agree.
    by_run: dict[tuple[str, str, int], set[tuple[float | None, bool]]] = {}
    for item in items:
        key = (item.protocol, item.dataset, item.seed)
        by_run.setdefault(key, set()).add((item.score, item.passed))
    for (protocol, dataset, seed), outcomes in by_run.items():
        if len(outcomes) > 1:
            reasons.append(
                f"non-deterministic rerun: {protocol}/{dataset}/seed={seed} "
                f"yielded {len(outcomes)} distinct outcomes"
            )
    # Degenerate distribution: identical scores across >=3 independent seeds
    # carry no information about the candidate.
    seeds = {item.seed for item in items}
    scores = _scores(items)
    if len(seeds) >= 3 and len(scores) >= 3 and len(set(scores)) == 1:
        reasons.append(
            f"degenerate evidence: constant score {scores[0]} across {len(seeds)} seeds"
        )
    if reasons:
        return GateVerdict(gate, False, tuple(reasons))
    return GateVerdict(gate, True)


def check_replication(
    internal: tuple[Evidence, ...],
    replication: tuple[Evidence, ...],
    protocol: HoldoutProtocol,
    *,
    min_pass_fraction: float = 1.0,
) -> GateVerdict:
    """L2 gate: holdout discipline + leakage controls over replication evidence."""
    gate = "L2-holdout-replication"
    if not 0.0 < min_pass_fraction <= 1.0:
        raise ValueError("min_pass_fraction must be in (0, 1]")
    reasons: list[str] = []
    train = [item for item in internal if item.kind == INTERNAL_KIND]
    holdout = [item for item in replication if item.kind == REPLICATION_KIND]
    if not holdout:
        return GateVerdict(gate, False, ("no replication evidence to validate",))
    for item in train:
        if item.dataset not in protocol.train_datasets:
            reasons.append(
                f"internal evidence {item.evidence_id} uses undeclared dataset "
                f"{item.dataset!r} (protocol {protocol.name!r})"
            )
    for item in holdout:
        if item.dataset not in protocol.holdout_datasets:
            reasons.append(
                f"replication evidence {item.evidence_id} uses non-holdout dataset "
                f"{item.dataset!r} (protocol {protocol.name!r})"
            )
    # Leakage control 1: dataset identifiers must not cross the boundary.
    train_ids = {item.dataset for item in train}
    holdout_ids = {item.dataset for item in holdout}
    collision = train_ids & holdout_ids
    if collision:
        reasons.append(f"dataset leakage across train/holdout boundary: {sorted(collision)}")
    # Leakage control 2: an identical (dataset, seed) pair on both sides means
    # the "independent" run literally reproduced the training draw.
    train_draws = {(item.dataset, item.seed) for item in train}
    holdout_draws = {(item.dataset, item.seed) for item in holdout}
    reused = train_draws & holdout_draws
    if reused:
        reasons.append(f"(dataset, seed) reuse across boundary: {sorted(reused)}")
    if holdout:
        pass_fraction = sum(1 for item in holdout if item.passed) / len(holdout)
        if pass_fraction < min_pass_fraction:
            reasons.append(
                f"replication pass fraction {pass_fraction:.3f} below "
                f"required {min_pass_fraction:.3f}"
            )
    if reasons:
        return GateVerdict(gate, False, tuple(reasons))
    return GateVerdict(gate, True)


@dataclass(frozen=True)
class ValidationGates:
    """Opt-in kernel wiring: per-domain holdout protocols + replication threshold."""

    protocols: Mapping[str, HoldoutProtocol] = field(
        default_factory=lambda: MappingProxyType({})
    )
    min_replication_pass_fraction: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "protocols", MappingProxyType(dict(self.protocols)))

    def protocol_for(self, domain: str) -> HoldoutProtocol | None:
        return self.protocols.get(domain)


def synthetic_holdout_protocol() -> HoldoutProtocol:
    """The split every shipped synthetic adapter already honours."""
    return HoldoutProtocol(
        "synthetic-v1",
        train_datasets=("synthetic-train",),
        holdout_datasets=("synthetic-holdout",),
    )

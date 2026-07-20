"""Domain-neutral immutable data models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType
from typing import Any


class EvidenceLevel(IntEnum):
    """Evidence gates; levels are not interchangeable confidence scores."""

    L0 = 0  # traceable candidate; not believed
    L1 = 1  # internally consistent on declared data
    L2 = 2  # reproduced on independent/held-out evidence
    L3 = 3  # bounded structured peer-review evidence
    L4 = 4  # externally review-ready, requiring a human gate


def frozen_mapping(values: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return MappingProxyType(dict(values or {}))


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    domain: str
    claim: str
    parameters: Mapping[str, Any] = field(default_factory=frozen_mapping)
    parent_id: str | None = None
    source_adapter: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.domain or not self.claim:
            raise ValueError("candidate_id, domain, and claim must be non-empty")
        object.__setattr__(self, "parameters", frozen_mapping(self.parameters))


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    candidate_id: str
    kind: str
    passed: bool
    protocol: str
    dataset: str
    seed: int
    score: float | None = None
    details: Mapping[str, Any] = field(default_factory=frozen_mapping)

    def __post_init__(self) -> None:
        if not all((self.evidence_id, self.candidate_id, self.kind, self.protocol, self.dataset)):
            raise ValueError("evidence identifiers and provenance fields must be non-empty")
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be within [0, 1]")
        object.__setattr__(self, "details", frozen_mapping(self.details))


CODE_ORIGINS = ("first-party-clean-room", "third-party")


@dataclass(frozen=True)
class AdapterManifest:
    """What an adapter is made of. Trust *decisions* live in the registry (Phase 1).

    ``synthetic_only`` describes the data: True means the adapter touches only
    deterministic synthetic data. ``code_origin`` describes the code:
    first-party-clean-room or third-party. Third-party code additionally
    requires ``third_party_source`` so the permission manifest can be checked.
    """

    name: str
    version: str
    domain: str
    vocabulary: tuple[str, ...]
    synthetic_only: bool = True
    code_origin: str = "first-party-clean-room"
    data_sources: tuple[str, ...] = ()
    third_party_source: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.version or not self.domain:
            raise ValueError("adapter manifest fields must be non-empty")
        if self.code_origin not in CODE_ORIGINS:
            raise ValueError(f"code_origin must be one of {CODE_ORIGINS}")
        if self.synthetic_only and self.data_sources:
            raise ValueError("synthetic-only adapters must not declare real data sources")
        if self.code_origin == "third-party" and not self.third_party_source:
            raise ValueError("third-party adapters must declare third_party_source")
        if self.code_origin == "first-party-clean-room" and self.third_party_source:
            raise ValueError("clean-room adapters must not declare a third_party_source")


@dataclass(frozen=True)
class WorkResult:
    candidate: Candidate
    evidence: tuple[Evidence, ...]

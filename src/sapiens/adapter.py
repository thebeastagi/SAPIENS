"""The clean boundary between the shared kernel and scientific domains."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .budget import ExecutionContext
from .models import AdapterManifest, Candidate, Evidence


@runtime_checkable
class DomainAdapter(Protocol):
    """A domain supplies data/generation/checks, never evidence-level decisions."""

    @property
    def manifest(self) -> AdapterManifest: ...

    def propose(self, *, seed: int, limit: int) -> tuple[Candidate, ...]: ...

    def validate(
        self, candidate: Candidate, *, stage: str, seed: int, context: ExecutionContext
    ) -> tuple[Evidence, ...]: ...

    def import_structure(self, structure: dict[str, object], *, candidate_id: str) -> Candidate: ...


def validate_adapter(adapter: DomainAdapter) -> None:
    """Phase-1 gate: auto-tiered registry validation.

    Kept for backward compatibility with Phase-0 callers. Synthetic adapters
    pass exactly as before; first-party clean-room real-data adapters pass at
    CORE tier; third-party adapters require a recorded permission and raise
    ``MissingPermissionError`` without one. Callers that need the tier (e.g.
    the kernel, to decide on isolation) should use ``AdapterRegistry``
    directly.
    """
    from .registry import AdapterRegistry

    AdapterRegistry().validate_adapter(adapter)

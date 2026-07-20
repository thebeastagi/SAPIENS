"""Trust-tiered adapter registry (Phase 1).

Replaces the Phase-0 synthetic-only gate. Three tiers:

- ``SYNTHETIC``: deterministic synthetic data only. Runs in-process.
- ``CORE``: first-party clean-room code; real data allowed. Runs in-process.
- ``UNTRUSTED``: third-party code. Requires a recorded owner permission
  (``PermissionManifest``) *and* subprocess isolation for every execution.

An adapter's tier derives from its manifest, never from adapter-supplied
claims at call time: synthetic data + any first-party code ⇒ SYNTHETIC;
real data + first-party clean-room code ⇒ CORE; third-party code ⇒ UNTRUSTED.
Explicit registration pins the tier so a manifest edit cannot silently
downgrade a check that already happened.
"""

from __future__ import annotations

from datetime import date
from enum import IntEnum

from .adapter import DomainAdapter
from .permissions import PermissionManifest


class TrustTier(IntEnum):
    SYNTHETIC = 0
    CORE = 1
    UNTRUSTED = 2


def derive_tier(adapter: DomainAdapter) -> TrustTier:
    """Tier from manifest facts alone."""
    manifest = adapter.manifest
    if manifest.code_origin == "third-party":
        return TrustTier.UNTRUSTED
    return TrustTier.SYNTHETIC if manifest.synthetic_only else TrustTier.CORE


class AdapterRegistry:
    """Validates adapters against trust tiers and recorded permissions."""

    def __init__(
        self,
        permissions: PermissionManifest | None = None,
        *,
        today: date | None = None,
    ) -> None:
        self._permissions = permissions if permissions is not None else PermissionManifest.empty()
        self._today = today if today is not None else date.today()
        self._tiers: dict[str, TrustTier] = {}

    @property
    def permissions(self) -> PermissionManifest:
        return self._permissions

    def _check(self, adapter: DomainAdapter, tier: TrustTier) -> None:
        manifest = adapter.manifest
        if tier == TrustTier.SYNTHETIC and not manifest.synthetic_only:
            raise ValueError(
                f"adapter {manifest.name!r} registered SYNTHETIC but declares real data sources"
            )
        if tier == TrustTier.CORE and manifest.code_origin != "first-party-clean-room":
            raise ValueError(
                f"adapter {manifest.name!r} registered CORE but is not first-party clean-room code"
            )
        if tier == TrustTier.UNTRUSTED:
            self._permissions.require(
                source=manifest.third_party_source or "",
                scope=f"adapter:{manifest.name}",
                on=self._today,
            )

    def register(self, adapter: DomainAdapter, tier: TrustTier) -> None:
        """Pin an adapter to an explicit tier after validating manifest coherence."""
        if not isinstance(adapter, DomainAdapter):
            raise TypeError("adapter does not implement DomainAdapter")
        self._check(adapter, tier)
        name = adapter.manifest.name
        existing = self._tiers.get(name)
        if existing is not None and existing != tier:
            raise ValueError(f"adapter {name!r} already registered at tier {existing.name}")
        self._tiers[name] = tier

    def tier_of(self, adapter: DomainAdapter) -> TrustTier:
        registered = self._tiers.get(adapter.manifest.name)
        return registered if registered is not None else derive_tier(adapter)

    def validate_adapter(self, adapter: DomainAdapter) -> TrustTier:
        """Phase-1 gate: structural check + tier rules + permission enforcement."""
        if not isinstance(adapter, DomainAdapter):
            raise TypeError("adapter does not implement DomainAdapter")
        tier = self.tier_of(adapter)
        self._check(adapter, tier)
        return tier

    def requires_isolation(self, adapter: DomainAdapter) -> bool:
        return self.validate_adapter(adapter) == TrustTier.UNTRUSTED

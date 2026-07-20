import json
from datetime import date

import pytest

from sapiens.models import AdapterManifest, Candidate
from sapiens.permissions import MissingPermissionError, PermissionManifest
from sapiens.registry import AdapterRegistry, TrustTier, derive_tier


class SyntheticDouble:
    manifest = AdapterManifest("synth", "1", "synth-domain", ("x",))

    def propose(self, *, seed: int, limit: int):
        return ()

    def validate(self, candidate, *, stage: str, seed: int, context):
        return ()

    def import_structure(self, structure, *, candidate_id: str):
        return Candidate(candidate_id, "synth-domain", "claim")


class CoreDouble(SyntheticDouble):
    manifest = AdapterManifest(
        "core-real",
        "1",
        "core-domain",
        ("x",),
        synthetic_only=False,
        data_sources=("https://example.org/public",),
    )


class ThirdPartyDouble(SyntheticDouble):
    manifest = AdapterManifest(
        "tp",
        "1",
        "tp-domain",
        ("x",),
        synthetic_only=False,
        code_origin="third-party",
        third_party_source="ASTRA-dev",
        data_sources=("https://example.org/public",),
    )


PERMISSION = {
    "source": "ASTRA-dev",
    "scope": "adapter:tp",
    "licence": "MIT",
    "granted_by": "owner@example.org",
    "reference": "https://example.org/permission/1",
    "granted_on": "2026-07-01",
    "expires_on": None,
}


def manifest_with(entries, tmp_path):
    path = tmp_path / "permissions.json"
    path.write_text(json.dumps({"version": 1, "entries": entries}))
    return PermissionManifest.load(path)


def test_derive_tier_from_manifest_facts():
    assert derive_tier(SyntheticDouble()) == TrustTier.SYNTHETIC
    assert derive_tier(CoreDouble()) == TrustTier.CORE
    assert derive_tier(ThirdPartyDouble()) == TrustTier.UNTRUSTED


def test_unregistered_adapters_auto_tier_on_validate():
    registry = AdapterRegistry(today=date(2026, 7, 20))
    assert registry.validate_adapter(SyntheticDouble()) == TrustTier.SYNTHETIC
    assert registry.validate_adapter(CoreDouble()) == TrustTier.CORE


def test_third_party_requires_permission_entry(tmp_path):
    registry = AdapterRegistry(today=date(2026, 7, 20))
    with pytest.raises(MissingPermissionError):
        registry.validate_adapter(ThirdPartyDouble())
    permitted = AdapterRegistry(
        manifest_with([PERMISSION], tmp_path), today=date(2026, 7, 20)
    )
    assert permitted.validate_adapter(ThirdPartyDouble()) == TrustTier.UNTRUSTED
    assert permitted.requires_isolation(ThirdPartyDouble())


def test_expired_permission_blocks_validation(tmp_path):
    expired = {**PERMISSION, "expires_on": "2026-07-19"}
    registry = AdapterRegistry(manifest_with([expired], tmp_path), today=date(2026, 7, 20))
    with pytest.raises(MissingPermissionError):
        registry.validate_adapter(ThirdPartyDouble())


def test_registration_pins_tier_and_rejects_incoherent(tmp_path):
    registry = AdapterRegistry(today=date(2026, 7, 20))
    registry.register(SyntheticDouble(), TrustTier.SYNTHETIC)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(SyntheticDouble(), TrustTier.CORE)
    with pytest.raises(ValueError, match="real data sources"):
        registry.register(CoreDouble(), TrustTier.SYNTHETIC)
    with pytest.raises(ValueError, match="clean-room"):
        registry.register(ThirdPartyDouble(), TrustTier.CORE)


def test_register_third_party_untrusted_with_permission(tmp_path):
    registry = AdapterRegistry(manifest_with([PERMISSION], tmp_path), today=date(2026, 7, 20))
    registry.register(ThirdPartyDouble(), TrustTier.UNTRUSTED)
    assert registry.tier_of(ThirdPartyDouble()) == TrustTier.UNTRUSTED


def test_non_adapter_rejected():
    registry = AdapterRegistry()
    with pytest.raises(TypeError):
        registry.validate_adapter(object())

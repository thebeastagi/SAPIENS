import ast
from pathlib import Path

import pytest

from sapiens.adapter import validate_adapter
from sapiens.models import AdapterManifest, Candidate, Evidence
from sapiens.permissions import MissingPermissionError
from sapiens.registry import TrustTier

ROOT = Path(__file__).resolve().parents[1]


def test_core_does_not_import_adapters():
    for path in (ROOT / "src" / "sapiens").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("sapiens.adapters"), path
            elif isinstance(node, ast.Import):
                assert all(not alias.name.startswith("sapiens.adapters") for alias in node.names), (
                    path
                )


class _RealDataAdapter:
    @property
    def manifest(self):  # type: ignore[override]
        return AdapterManifest(
            "real",
            "0",
            "unsafe",
            ("x",),
            synthetic_only=False,
            data_sources=("https://example.org/public-data",),
        )

    def propose(self, *, seed: int, limit: int):
        return ()

    def validate(self, candidate, *, stage: str, seed: int, context):
        return ()

    def import_structure(self, structure, *, candidate_id: str):
        return Candidate(candidate_id, "unsafe", "claim")


class _ThirdPartyAdapter(_RealDataAdapter):
    @property
    def manifest(self):  # type: ignore[override]
        return AdapterManifest(
            "third-party-real",
            "0",
            "unsafe",
            ("x",),
            synthetic_only=False,
            code_origin="third-party",
            third_party_source="ASTRA-dev",
            data_sources=("https://example.org/public-data",),
        )


def test_phase1_accepts_first_party_real_data_adapter_at_core_tier():
    # Phase 1 replaced the synthetic-only gate with trust tiers: first-party
    # clean-room code on real data is CORE and runs in-process.
    validate_adapter(_RealDataAdapter())


def test_phase1_rejects_third_party_adapter_without_permission():
    with pytest.raises(MissingPermissionError):
        validate_adapter(_ThirdPartyAdapter())


def test_phase1_registry_reports_untrusted_tier_for_third_party():
    from sapiens.registry import AdapterRegistry

    registry = AdapterRegistry()
    assert registry.tier_of(_ThirdPartyAdapter()) == TrustTier.UNTRUSTED
    assert registry.tier_of(_RealDataAdapter()) == TrustTier.CORE


def test_manifest_rejects_incoherent_provenance():
    with pytest.raises(ValueError):
        AdapterManifest("m", "1", "d", ("x",), code_origin="third-party")  # no source
    with pytest.raises(ValueError):
        AdapterManifest("m", "1", "d", ("x",), code_origin="not-a-real-origin")
    with pytest.raises(ValueError):
        AdapterManifest("m", "1", "d", ("x",), data_sources=("real-data",))  # synthetic lie


def test_evidence_rejects_invalid_confidence_score():
    with pytest.raises(ValueError):
        Evidence("e", "c", "internal", True, "p", "d", 1, 1.2)

import json
from datetime import date

import pytest

from sapiens.permissions import (
    ManifestFormatError,
    MissingPermissionError,
    PermissionEntry,
    PermissionManifest,
)

TODAY = date(2026, 7, 20)

ENTRY = {
    "source": "ASTRA-dev",
    "scope": "adapter:astra-photometry",
    "licence": "MIT",
    "granted_by": "owner@example.org",
    "reference": "https://example.org/permission/1",
    "granted_on": "2026-07-01",
    "expires_on": "2026-12-31",
}


def make_manifest(tmp_path, entries):
    path = tmp_path / "permissions.json"
    path.write_text(json.dumps({"version": 1, "entries": entries}))
    return PermissionManifest.load(path)


def test_repo_manifest_is_empty_and_valid():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = PermissionManifest.load(root / "permissions.json")
    assert manifest.entries == ()
    # The clean-room invariant: zero ASTRA-family permissions recorded.
    assert not any("ASTRA" in e.source or "astra" in e.source for e in manifest.entries)


def test_empty_manifest_refuses_everything():
    manifest = PermissionManifest.empty()
    assert not manifest.permits(source="ASTRA-dev", scope="adapter:x", on=TODAY)
    with pytest.raises(MissingPermissionError):
        manifest.require(source="ASTRA-dev", scope="adapter:x", on=TODAY)


def test_load_roundtrip_and_permit(tmp_path):
    manifest = make_manifest(tmp_path, [ENTRY])
    assert manifest.permits(
        source="ASTRA-dev", scope="adapter:astra-photometry", on=date(2026, 8, 1)
    )
    entry = manifest.require(
        source="ASTRA-dev", scope="adapter:astra-photometry", on=date(2026, 8, 1)
    )
    assert entry.licence == "MIT"


def test_expired_permission_refused(tmp_path):
    manifest = make_manifest(tmp_path, [ENTRY])
    assert not manifest.permits(
        source="ASTRA-dev", scope="adapter:astra-photometry", on=date(2027, 1, 1)
    )
    with pytest.raises(MissingPermissionError, match="not active"):
        manifest.require(
            source="ASTRA-dev", scope="adapter:astra-photometry", on=date(2027, 1, 1)
        )


def test_not_yet_granted_permission_refused(tmp_path):
    manifest = make_manifest(tmp_path, [ENTRY])
    assert not manifest.permits(
        source="ASTRA-dev", scope="adapter:astra-photometry", on=date(2026, 6, 1)
    )


def test_scope_wildcard(tmp_path):
    wildcard = {**ENTRY, "scope": "module:swarm/*"}
    manifest = make_manifest(tmp_path, [wildcard])
    assert manifest.permits(
        source="ASTRA-dev", scope="module:swarm/pheromone_dynamics", on=date(2026, 8, 1)
    )
    assert not manifest.permits(source="ASTRA-dev", scope="module:other/x", on=date(2026, 8, 1))


def test_wrong_source_refused(tmp_path):
    manifest = make_manifest(tmp_path, [ENTRY])
    assert not manifest.permits(
        source="SLATE", scope="adapter:astra-photometry", on=date(2026, 8, 1)
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"version": 2, "entries": []},  # unsupported version
        {"version": 1},  # missing entries list
        {"version": 1, "entries": [{"source": "x"}]},  # incomplete entry
        {"version": 1, "entries": [{**ENTRY, "granted_on": "not-a-date"}]},
        {"version": 1, "entries": [{**ENTRY, "expires_on": "2026-01-01"}]},  # before grant
        {"version": 1, "entries": [{**ENTRY, "surprise_field": 1}]},  # unknown field
        {"version": 1, "entries": [ENTRY, ENTRY]},  # duplicates
    ],
)
def test_malformed_manifests_fail_loudly(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ManifestFormatError):
        PermissionManifest.load(path)


def test_entry_requires_nonempty_fields():
    with pytest.raises(ManifestFormatError):
        PermissionEntry.from_dict({**ENTRY, "licence": ""})

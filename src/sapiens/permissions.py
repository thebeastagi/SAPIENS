"""Owner-permission/licence manifest for third-party code reuse (Phase 1).

No third-party code may power an adapter without a recorded permission entry.
The repository ships with an **empty** manifest: zero ASTRA-family permissions
exist, and the clean-room invariant holds until an owner records otherwise.

The manifest is data, not code: a JSON document listing each grant with its
source, scope, licence, grantor, evidence reference, and validity window.
Entries are immutable once loaded; expiry is checked against an explicit date
(injected, never a hidden clock) so verification is deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class MissingPermissionError(PermissionError):
    """Raised when third-party code is used without a recorded permission."""


class ManifestFormatError(ValueError):
    """Raised when a permission manifest is malformed. Fail loudly, never guess."""


def _parse_date(value: Any, *, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestFormatError(f"{field} must be an ISO date string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ManifestFormatError(f"{field} is not a valid ISO date: {value!r}") from exc


@dataclass(frozen=True)
class PermissionEntry:
    """One recorded owner grant for third-party material."""

    source: str  # upstream project, e.g. "ASTRA-dev"
    scope: str  # what the grant covers, e.g. "adapter:astra-photometry" or "module:swarm/*"
    licence: str  # licence or permission basis, e.g. "MIT" or "written-permission"
    granted_by: str  # identity of the owner who granted it
    reference: str  # evidence: URL, document id, or message reference
    granted_on: date
    expires_on: date | None = None

    def __post_init__(self) -> None:
        for name in ("source", "scope", "licence", "granted_by", "reference"):
            if not getattr(self, name):
                raise ManifestFormatError(f"permission entry field {name} must be non-empty")
        if self.expires_on is not None and self.expires_on < self.granted_on:
            raise ManifestFormatError("permission expires before it was granted")

    @classmethod
    def from_dict(cls, raw: Any) -> PermissionEntry:
        if not isinstance(raw, dict):
            raise ManifestFormatError("permission entries must be objects")
        known = {
            "source", "scope", "licence", "granted_by", "reference", "granted_on", "expires_on",
        }
        unknown = set(raw) - known
        if unknown:
            raise ManifestFormatError(f"unknown permission entry fields: {sorted(unknown)}")
        granted_on = _parse_date(raw.get("granted_on"), field="granted_on")
        if granted_on is None:
            raise ManifestFormatError("granted_on is required")
        return cls(
            source=str(raw.get("source", "")),
            scope=str(raw.get("scope", "")),
            licence=str(raw.get("licence", "")),
            granted_by=str(raw.get("granted_by", "")),
            reference=str(raw.get("reference", "")),
            granted_on=granted_on,
            expires_on=_parse_date(raw.get("expires_on"), field="expires_on"),
        )

    def active(self, *, on: date) -> bool:
        return self.granted_on <= on and (self.expires_on is None or on <= self.expires_on)

    def covers(self, *, source: str, scope: str) -> bool:
        if self.source != source:
            return False
        if self.scope == scope:
            return True
        # Prefix wildcard: "module:swarm/*" covers "module:swarm/pheromone_dynamics".
        return self.scope.endswith("/*") and scope.startswith(self.scope[:-1])


@dataclass(frozen=True)
class PermissionManifest:
    """Immutable set of recorded owner permissions."""

    entries: tuple[PermissionEntry, ...] = ()

    @classmethod
    def empty(cls) -> PermissionManifest:
        return cls(())

    @classmethod
    def load(cls, path: str | Path) -> PermissionManifest:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestFormatError(f"permission manifest is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ManifestFormatError("permission manifest must be a JSON object")
        version = raw.get("version")
        if version != SCHEMA_VERSION:
            raise ManifestFormatError(f"unsupported manifest version: {version!r}")
        entries_raw = raw.get("entries")
        if not isinstance(entries_raw, list):
            raise ManifestFormatError("manifest entries must be a list")
        entries = tuple(PermissionEntry.from_dict(item) for item in entries_raw)
        sources = [(e.source, e.scope) for e in entries]
        if len(set(sources)) != len(sources):
            raise ManifestFormatError("duplicate (source, scope) permission entries")
        return cls(entries)

    def permits(self, *, source: str, scope: str, on: date) -> bool:
        return any(
            entry.covers(source=source, scope=scope) and entry.active(on=on)
            for entry in self.entries
        )

    def require(self, *, source: str, scope: str, on: date) -> PermissionEntry:
        for entry in self.entries:
            if entry.covers(source=source, scope=scope):
                if entry.active(on=on):
                    return entry
                raise MissingPermissionError(
                    f"permission for {source!r} scope {scope!r} is not active on {on}"
                )
        raise MissingPermissionError(
            f"no recorded owner permission for {source!r} scope {scope!r}; "
            "third-party code requires an explicit permission entry"
        )

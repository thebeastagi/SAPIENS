"""Signed ledger checkpoints and external anchor export (Phase 1).

A checkpoint is a ledger event that summarises the chain so far: the event
count and the current head hash. With an HMAC key (environment-only, never
stored) the checkpoint is *signed*; without one it is still a structural
marker the verifier checks for continuity.

Honest scope, matching the ledger's own warnings:

- HMAC is symmetric. A signed checkpoint proves the writer held the local
  key; it is **not** a public signature and proves nothing to a third party
  who does not hold the key.
- ``export_anchor`` writes the head hash to a separate file so it can be
  published or archived elsewhere. Comparing an anchor against a ledger
  detects whole-file rewrites by anyone who could not also update the
  anchor. Anchoring to a truly external system (timestamping service,
  public chain) is a Phase-5 workflow; this module provides the hook.

The key is read from the environment (``SAPIENS_CHECKPOINT_KEY``) at call
time and is never written to the ledger, the anchor file, logs, or any
artifact.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ledger import GENESIS, EvidenceLedger, LedgerEvent

CHECKPOINT_KEY_ENV = "SAPIENS_CHECKPOINT_KEY"
SIGNATURE_SCHEME = "hmac-sha256"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False
    ).encode("utf-8")


def key_from_env(env: Mapping[str, str] | None = None) -> bytes | None:
    """Read the HMAC key from the environment. Never log or persist the result."""
    source = env if env is not None else os.environ
    raw = source.get(CHECKPOINT_KEY_ENV)
    if not raw:
        return None
    return raw.encode("utf-8")


def signature_payload(*, event_count: int, head_hash: str) -> bytes:
    return _canonical({"event_count": event_count, "head_hash": head_hash})


def sign(*, event_count: int, head_hash: str, key: bytes) -> str:
    if not key:
        raise ValueError("signing key must be non-empty")
    return hmac.new(
        key, signature_payload(event_count=event_count, head_hash=head_hash), hashlib.sha256
    ).hexdigest()


@dataclass(frozen=True)
class CheckpointVerification:
    """Outcome of checkpoint signature verification. Data, not vibes."""

    checkpoints: int
    signed: int
    signatures_verified: int
    signatures_unverifiable: tuple[int, ...]  # seq numbers: signed, but no key available
    signature_failures: tuple[int, ...]  # seq numbers: signature does not match


def verify_checkpoints(
    events: tuple[LedgerEvent, ...], *, key: bytes | None
) -> CheckpointVerification:
    """Check every checkpoint event's signature (when verifiable).

    Structural continuity (event count + head hash) is already enforced by
    ``EvidenceLedger.verify``; this layer handles only signatures.
    """
    checkpoints = signed = verified = 0
    unverifiable: list[int] = []
    failures: list[int] = []
    for event in events:
        if event.kind != "checkpoint":
            continue
        checkpoints += 1
        signature = event.payload.get("signature")
        if not signature:
            continue
        signed += 1
        if key is None:
            unverifiable.append(event.seq)
            continue
        expected = sign(
            event_count=int(event.payload["event_count"]),
            head_hash=str(event.payload["head_hash"]),
            key=key,
        )
        if hmac.compare_digest(expected, str(signature)):
            verified += 1
        else:
            failures.append(event.seq)
    return CheckpointVerification(
        checkpoints=checkpoints,
        signed=signed,
        signatures_verified=verified,
        signatures_unverifiable=tuple(unverifiable),
        signature_failures=tuple(failures),
    )


def record_checkpoint(ledger: EvidenceLedger, *, key: bytes | None = None) -> LedgerEvent:
    """Append a checkpoint over the current chain. Key from env when omitted."""
    if key is None:
        key = key_from_env()
    events = ledger.events()
    head = events[-1].event_hash if events else GENESIS
    payload: dict[str, Any] = {
        "event_count": len(events),
        "head_hash": head,
        "signed": key is not None,
        "signature": None,
        "scheme": SIGNATURE_SCHEME if key is not None else None,
    }
    if key is not None:
        payload["signature"] = sign(event_count=len(events), head_hash=head, key=key)
    return ledger.append("checkpoint", "__ledger__", payload)


def export_anchor(ledger: EvidenceLedger, path: str | Path) -> dict[str, Any]:
    """Write the current head hash to a separate anchor file (JSON)."""
    events = ledger.events()
    head = events[-1].event_hash if events else GENESIS
    anchor = {
        "kind": "sapiens-ledger-anchor",
        "version": 1,
        "event_count": len(events),
        "head_hash": head,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(anchor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return anchor


def verify_anchor(ledger: EvidenceLedger, path: str | Path) -> bool:
    """True iff the anchor file matches the ledger's current head."""
    try:
        anchor = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable anchor file: {exc}") from exc
    if anchor.get("kind") != "sapiens-ledger-anchor" or anchor.get("version") != 1:
        raise ValueError("not a sapiens ledger anchor file")
    events = ledger.events()
    head = events[-1].event_hash if events else GENESIS
    return anchor.get("head_hash") == head and anchor.get("event_count") == len(events)

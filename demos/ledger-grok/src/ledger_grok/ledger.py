"""Append-only JSONL evidence ledger with a SHA-256 hash chain.

Follows the same canonical-JSON chaining convention as ``sapiens.ledger``
(the SAPIENS Phase-0 evidence ledger), specialised for this demo's event
kinds. The chain detects after-the-fact tampering; it does not by itself
prove identity, authorship, or scientific validity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
EVENT_KINDS = (
    "data_ingested",
    "hypothesis",
    "analysis",
    "adversarial_challenge",
    "challenge_response",
    "verdict",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False
    ).encode("utf-8")


def compute_hash(
    seq: int, ts: str, actor: str, kind: str, payload: dict[str, Any], previous_hash: str
) -> str:
    unsigned = {
        "actor": actor,
        "kind": kind,
        "payload": payload,
        "previous_hash": previous_hash,
        "seq": seq,
        "ts": ts,
    }
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


@dataclass(frozen=True)
class Entry:
    seq: int
    ts: str
    actor: str
    kind: str
    payload: dict[str, Any]
    previous_hash: str
    entry_hash: str


class LedgerIntegrityError(ValueError):
    """Raised when a chain fails verification (gap, bad link, bad hash)."""


class Ledger:
    """Creates a fresh ledger file; refuses to clobber an existing non-empty one."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > 0:
            raise FileExistsError(f"ledger already exists and is non-empty: {self.path}")
        self._prev = GENESIS
        self._seq = 0

    def append(self, actor: str, kind: str, payload: dict[str, Any]) -> Entry:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind: {kind}")
        self._seq += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        eh = compute_hash(self._seq, ts, actor, kind, payload, self._prev)
        entry = Entry(self._seq, ts, actor, kind, payload, self._prev, eh)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(asdict(entry)).decode("utf-8") + "\n")
        self._prev = eh
        return entry


def load_entries(path: str | Path) -> list[Entry]:
    entries: list[Entry] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(Entry(**json.loads(line)))
            except (json.JSONDecodeError, TypeError) as exc:
                raise LedgerIntegrityError(f"invalid record at line {lineno}") from exc
    return entries


def verify_entries(entries: list[Entry]) -> bool:
    previous = GENESIS
    for expected, entry in enumerate(entries, 1):
        if entry.seq != expected:
            raise LedgerIntegrityError(f"sequence gap at position {expected}: seq={entry.seq}")
        if entry.previous_hash != previous:
            raise LedgerIntegrityError(f"broken chain link at entry {expected}")
        if entry.kind not in EVENT_KINDS:
            raise LedgerIntegrityError(f"unknown event kind at entry {expected}: {entry.kind}")
        digest = compute_hash(
            entry.seq, entry.ts, entry.actor, entry.kind, entry.payload, entry.previous_hash
        )
        if digest != entry.entry_hash:
            raise LedgerIntegrityError(
                f"hash mismatch at entry {expected} — payload or metadata was modified"
            )
        previous = entry.entry_hash
    return True

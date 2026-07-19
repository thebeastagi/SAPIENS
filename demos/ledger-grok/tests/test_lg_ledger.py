"""Ledger hash-chain integrity tests: build, verify, and tamper detection."""

import json

import pytest

from ledger_grok.ledger import (
    GENESIS,
    Ledger,
    LedgerIntegrityError,
    load_entries,
    verify_entries,
)


def _build(path):
    ledger = Ledger(path)
    ledger.append("pipeline", "data_ingested", {"sha256": "abc", "rows": 3})
    ledger.append("grok-mock", "hypothesis", {"text": "box-like dimming"})
    ledger.append("pipeline", "verdict", {"match": True})
    return path


def test_fresh_chain_verifies(tmp_path):
    path = _build(tmp_path / "ledger.jsonl")
    entries = load_entries(path)
    assert [e.seq for e in entries] == [1, 2, 3]
    assert entries[0].previous_hash == GENESIS
    assert verify_entries(entries) is True


def test_refuses_to_clobber_existing(tmp_path):
    path = _build(tmp_path / "ledger.jsonl")
    with pytest.raises(FileExistsError):
        Ledger(path)


def test_unknown_kind_rejected(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError):
        ledger.append("pipeline", "made_up_kind", {})


def _rewrite(path, mutate):
    lines = path.read_text().splitlines()
    entries = [json.loads(line) for line in lines]
    mutate(entries)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_payload_tamper_detected(tmp_path):
    path = _build(tmp_path / "ledger.jsonl")
    _rewrite(path, lambda e: e[1]["payload"].update({"text": "forged"}))
    with pytest.raises(LedgerIntegrityError, match="hash mismatch"):
        verify_entries(load_entries(path))


def test_reordered_entries_detected(tmp_path):
    path = _build(tmp_path / "ledger.jsonl")
    _rewrite(path, lambda e: e.__setitem__(slice(1, 3), [e[2], e[1]]))
    with pytest.raises(LedgerIntegrityError):
        verify_entries(load_entries(path))


def test_truncation_detected(tmp_path):
    path = _build(tmp_path / "ledger.jsonl")
    _rewrite(path, lambda e: e.pop())
    # truncation alone leaves a valid prefix chain; dropping from the middle must not
    middle = _build(tmp_path / "ledger2.jsonl")
    _rewrite(middle, lambda e: e.pop(1))
    with pytest.raises(LedgerIntegrityError):
        verify_entries(load_entries(middle))


def test_genesis_link_required(tmp_path):
    path = _build(tmp_path / "ledger.jsonl")
    _rewrite(path, lambda e: e[0].update({"previous_hash": "f" * 64}))
    with pytest.raises(LedgerIntegrityError):
        verify_entries(load_entries(path))

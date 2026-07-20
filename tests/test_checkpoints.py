import json

import pytest

from sapiens.checkpoints import (
    export_anchor,
    key_from_env,
    record_checkpoint,
    sign,
    verify_anchor,
    verify_checkpoints,
)
from sapiens.ledger import EvidenceLedger, LedgerIntegrityError
from sapiens.models import Evidence

KEY = b"test-key-not-a-secret"
OTHER_KEY = b"different-key"


def filled_ledger(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ledger.record_candidate("cand-1")
    ledger.record_evidence(
        Evidence("ev-1", "cand-1", "internal", True, "proto", "data", 7, 0.9)
    )
    ledger.promote("cand-1", 1, ("ev-1",))
    return ledger


def test_unsigned_checkpoint_roundtrip(tmp_path):
    ledger = filled_ledger(tmp_path)
    event = record_checkpoint(ledger, key=None)
    assert event.kind == "checkpoint"
    assert event.payload["event_count"] == 3
    assert event.payload["signed"] is False
    assert event.payload["signature"] is None
    assert ledger.verify()
    report = verify_checkpoints(ledger.events(), key=None)
    assert report.checkpoints == 1 and report.signed == 0
    # More events may follow a checkpoint; the chain stays valid.
    ledger.record_candidate("cand-2")
    assert ledger.verify()


def test_signed_checkpoint_verifies_with_key(tmp_path):
    ledger = filled_ledger(tmp_path)
    record_checkpoint(ledger, key=KEY)
    assert ledger.verify()
    events = ledger.events()
    report = verify_checkpoints(events, key=KEY)
    assert report.signed == 1 and report.signatures_verified == 1
    assert not report.signature_failures


def test_signed_checkpoint_reports_unverifiable_without_key(tmp_path):
    ledger = filled_ledger(tmp_path)
    record_checkpoint(ledger, key=KEY)
    report = verify_checkpoints(ledger.events(), key=None)
    assert report.signed == 1
    assert report.signatures_verified == 0
    assert report.signatures_unverifiable == (4,)


def test_wrong_key_detected(tmp_path):
    ledger = filled_ledger(tmp_path)
    record_checkpoint(ledger, key=KEY)
    report = verify_checkpoints(ledger.events(), key=OTHER_KEY)
    assert report.signature_failures == (4,)


def test_tampered_history_breaks_checkpoint_continuity(tmp_path):
    ledger = filled_ledger(tmp_path)
    record_checkpoint(ledger, key=KEY)
    path = tmp_path / "evidence.jsonl"
    lines = path.read_text().splitlines()
    # Rewrite a historical payload without fixing the chain.
    first = json.loads(lines[0])
    first["payload"]["level"] = 99
    lines[0] = json.dumps(first)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerIntegrityError):
        ledger.verify()


def test_forged_checkpoint_event_rejected(tmp_path):
    ledger = filled_ledger(tmp_path)
    with pytest.raises(LedgerIntegrityError):
        # Wrong head hash: verifier catches it at append time.
        ledger.append(
            "checkpoint",
            "__ledger__",
            {"event_count": 3, "head_hash": "0" * 64, "signed": False, "signature": None},
        )


def test_anchor_export_and_verify(tmp_path):
    ledger = filled_ledger(tmp_path)
    anchor_path = tmp_path / "anchor.json"
    anchor = export_anchor(ledger, anchor_path)
    assert anchor["event_count"] == 3
    assert verify_anchor(ledger, anchor_path)
    # Ledger moves on: the anchor no longer matches the head.
    ledger.record_candidate("cand-2")
    assert not verify_anchor(ledger, anchor_path)


def test_anchor_rejects_foreign_file(tmp_path):
    ledger = filled_ledger(tmp_path)
    bogus = tmp_path / "bogus.json"
    bogus.write_text(json.dumps({"kind": "something-else"}))
    with pytest.raises(ValueError):
        verify_anchor(ledger, bogus)


def test_key_from_env_never_returns_empty(monkeypatch):
    monkeypatch.delenv("SAPIENS_CHECKPOINT_KEY", raising=False)
    assert key_from_env() is None
    monkeypatch.setenv("SAPIENS_CHECKPOINT_KEY", "env-key")
    assert key_from_env() == b"env-key"
    monkeypatch.setenv("SAPIENS_CHECKPOINT_KEY", "")
    assert key_from_env() is None


def test_sign_is_deterministic_and_key_dependent():
    a = sign(event_count=3, head_hash="ab" * 32, key=KEY)
    assert a == sign(event_count=3, head_hash="ab" * 32, key=KEY)
    assert a != sign(event_count=3, head_hash="ab" * 32, key=OTHER_KEY)
    assert a != sign(event_count=4, head_hash="ab" * 32, key=KEY)

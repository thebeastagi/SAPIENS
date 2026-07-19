"""Grok adapter tests: mock determinism + real-adapter key handling."""

import json

import pytest

from ledger_grok.grok_adapter import MockGrokAdapter, RealGrokAdapter, get_adapter

CTX = {"target": "Kepler-10 (KIC 11904151)", "rows": 1432, "span_days": 33.47}
FINDINGS = {"period_days": 0.837, "depth_ppm": 158.0, "snr": 34.0}
DATA_SHA = "1d82ef8c" * 8


def test_mock_is_deterministic():
    a = MockGrokAdapter.from_data_hash(DATA_SHA)
    b = MockGrokAdapter.from_data_hash(DATA_SHA)
    h1, h2 = a.generate_hypothesis(CTX), b.generate_hypothesis(CTX)
    c1, c2 = a.adversarial_challenge(FINDINGS), b.adversarial_challenge(FINDINGS)
    assert json.dumps(h1, sort_keys=True) == json.dumps(h2, sort_keys=True)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)


def test_mock_schema_fields():
    a = MockGrokAdapter.from_data_hash(DATA_SHA)
    hyp = a.generate_hypothesis(CTX)
    for key in ("text", "predicted_period_range_days", "predicted_depth_ppm_range", "shape"):
        assert key in hyp
    ch = a.adversarial_challenge(FINDINGS)
    ids = {c["id"] for c in ch["challenges"]}
    assert {"harmonic_confusion", "odd_even_depth", "secondary_eclipse"} <= ids
    # mock output must always be labelled as mock
    assert hyp["adapter"] == "mock" and ch["adapter"] == "mock"


def test_factory():
    assert isinstance(get_adapter("mock", DATA_SHA), MockGrokAdapter)
    with pytest.raises(ValueError):
        get_adapter("bogus", DATA_SHA)


def test_real_adapter_requires_key(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROK_API_KEY"):
        RealGrokAdapter()

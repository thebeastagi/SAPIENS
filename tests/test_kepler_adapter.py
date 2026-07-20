"""Phase-4 Kepler adapter tests on the bundled public light curve.

Everything here validates a re-derivation of the published Kepler-10 b
signal. No discovery is claimed anywhere in this file.
"""

import math
import random

import pytest

from sapiens.adapters._transit import DataIntegrityError
from sapiens.adapters.kepler import (
    PUBLISHED_PERIOD_DAYS,
    KeplerPhotometryAdapter,
    verify_data_integrity,
)
from sapiens.budget import ExecutionContext
from sapiens.models import Candidate


@pytest.fixture(scope="module")
def adapter():
    return KeplerPhotometryAdapter()


@pytest.fixture(scope="module")
def candidate(adapter):
    proposed = adapter.propose(seed=0, limit=1)
    assert len(proposed) == 1
    return proposed[0]


def ctx():
    return ExecutionContext(max_steps=20, max_seconds=60.0)


def test_manifest_declares_core_tier_facts(adapter):
    manifest = adapter.manifest
    assert manifest.synthetic_only is False
    assert manifest.code_origin == "first-party-clean-room"
    assert manifest.third_party_source is None
    assert any("mast.stsci.edu" in source for source in manifest.data_sources)


def test_propose_rederives_published_period(candidate):
    period = float(candidate.parameters["period"])
    assert abs(period - PUBLISHED_PERIOD_DAYS) / PUBLISHED_PERIOD_DAYS < 0.01
    assert candidate.parameters["snr"] > 20
    # Honesty: the claim is a measurement statement, never a discovery claim.
    assert "not a discovery" in candidate.claim
    assert "transit-like dimming" in candidate.claim


def test_internal_stage_passes_on_real_data(adapter, candidate):
    evidence = adapter.validate(candidate, stage="internal", seed=40, context=ctx())
    assert len(evidence) == 1
    item = evidence[0]
    assert item.kind == "internal"
    assert item.dataset == "kepler-q1-full"
    assert item.passed is True
    assert 0.0 <= item.score <= 1.0
    assert item.details["snr"] > 20
    assert item.details["masked_rows"] > 0  # Kepler-10 C mask disclosed


def test_replication_stage_redetects_in_independent_halves(adapter, candidate):
    evidence = adapter.validate(candidate, stage="replication", seed=41, context=ctx())
    assert len(evidence) == 1
    item = evidence[0]
    assert item.dataset == "kepler-q1-holdout-halves"
    assert item.passed is True
    assert item.details["half-a"]["passed"] is True
    assert item.details["half-b"]["passed"] is True


def test_review_stage_adversarial_checks_pass(adapter, candidate):
    evidence = adapter.validate(candidate, stage="review", seed=42, context=ctx())
    item = evidence[0]
    assert item.dataset == "kepler-q1-review-adversarial"
    assert item.passed is True
    assert item.details["odd_even_ok"] is True
    assert item.details["secondary_ok"] is True
    assert item.details["harmonic_ok"] is True


def test_bundled_curve_checksum_is_pinned():
    from sapiens.adapters.kepler import DEFAULT_DATA

    verify_data_integrity(DEFAULT_DATA)  # must not raise


def test_tampered_curve_refused(tmp_path):
    from sapiens.adapters.kepler import DEFAULT_DATA

    blob = bytearray(DEFAULT_DATA.read_bytes())
    blob[-10] ^= 0xFF
    forged = tmp_path / "forged.csv"
    forged.write_bytes(bytes(blob))
    with pytest.raises(DataIntegrityError):
        verify_data_integrity(forged)


def _write_curve(path, times, fluxes):
    lines = ["time_bkjd,flux"] + [f"{t:.6f},{f:.8f}" for t, f in zip(times, fluxes, strict=True)]
    path.write_text("\n".join(lines) + "\n")


def test_flat_curve_proposes_nothing(tmp_path):
    rng = random.Random(7)
    times = [200.0 + i * 0.02 for i in range(1500)]
    fluxes = [1.0 + rng.gauss(0, 0.0002) for _ in times]
    curve = tmp_path / "flat.csv"
    _write_curve(curve, times, fluxes)
    adapter = KeplerPhotometryAdapter(curve)
    assert adapter.propose(seed=0, limit=1) == ()


def _shifted_curve(path):
    """Box dips at P=1.000 d in the first half, P=1.060 d in the second."""
    rng = random.Random(11)
    times: list[float] = []
    fluxes: list[float] = []
    for i in range(2000):
        t = 200.0 + i * 0.02
        period = 1.0 if t < 220.0 else 1.06
        in_dip = math.fmod(t, period) / period < 0.05
        flux = (0.99 if in_dip else 1.0) + rng.gauss(0, 0.0002)
        times.append(t)
        fluxes.append(flux)
    _write_curve(path, times, fluxes)


def test_shifted_period_curve_fails_replication_honestly(tmp_path):
    curve = tmp_path / "shifted.csv"
    _shifted_curve(curve)
    adapter = KeplerPhotometryAdapter(curve)
    candidate = Candidate(
        "cand-shifted",
        adapter.manifest.domain,
        "synthetic shifted-period control (not real data, not a discovery)",
        {
            "relation": "periodic-transit",
            "arity": 1,
            "period": 1.0,
            "q": 0.05,
            "phase_center": 0.025,
        },
        source_adapter="test",
    )
    evidence = adapter.validate(candidate, stage="replication", seed=41, context=ctx())
    item = evidence[0]
    assert item.passed is False
    per_half = {k: v["period_days"] for k, v in item.details.items() if k.startswith("half")}
    assert len(per_half) == 2
    # The halves genuinely disagree — the failure is in the data, not the gate.
    assert abs(per_half["half-a"] - per_half["half-b"]) / 1.0 > 0.02

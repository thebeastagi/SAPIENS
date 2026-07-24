"""Phase 0 core: G-03/G-05/G-06 seams + FP-06 guard on the promotion path."""

from sapiens.gates.nulls import InstrumentSystematic, NullKind, NullProvenance
from sapiens.gates.promotion import (
    CalibrationStatus,
    GateInputs,
    LedgerStatus,
    anomaly_priority,
    calibration_status,
    ledger_status,
    promotion_score,
    reserved_slot_eligible,
)
from sapiens.gates.surprise import LiteratureExpectation
from sapiens.gates.thresholds import ThresholdPolicy

POLICY = ThresholdPolicy()


def _null(sigma, **kw):
    return NullProvenance(
        kind=kw.get("kind", NullKind.CORRECT),
        description=kw.get("description", "null"),
        external_data_required=kw.get("req", False),
        external_data_fetched=kw.get("fetched", True),
        sigma_under_null=sigma,
        instrument_systematic=kw.get("inst", InstrumentSystematic.NOT_APPLICABLE),
    )


def _inputs(**kw):
    base = dict(
        candidate_id="c",
        domain="physics",
        provenance_ok=True,
        method_integrity=0.8,
        null=_null(5.0),
        has_mechanism=False,
        has_replication=True,
        orthogonal_confirmation=False,
        holdout_passed=None,
        observed_value=5.0,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "lit"),
    )
    base.update(kw)
    return GateInputs(**base)


def test_ledger_four_way():
    assert ledger_status(_inputs(has_mechanism=True, has_replication=True)) == (
        LedgerStatus.EXPLAINED_CONFIRMED
    )
    assert ledger_status(_inputs(has_mechanism=False, has_replication=True)) == (
        LedgerStatus.UNEXPLAINED_CONFIRMED
    )
    assert ledger_status(_inputs(has_mechanism=False, has_replication=False)) == (
        LedgerStatus.UNEXPLAINED_UNCONFIRMED
    )


def test_g03_anomaly_boost_requires_surprise():
    # Unexplained but matches expectation (surprise 0) -> no boost.
    unsurprising = _inputs(
        has_mechanism=False, observed_value=0.0,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "lit"),
    )
    assert anomaly_priority(unsurprising, policy=POLICY) == 0.0
    # Unexplained AND measurably surprising -> boost.
    surprising = _inputs(
        has_mechanism=False, observed_value=8.0,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "lit"),
    )
    assert anomaly_priority(surprising, policy=POLICY) > 0.0


def test_fp06_conservation_violation_denies_boost():
    breaker = _inputs(
        has_mechanism=False, observed_value=42.0, violates_conservation_law=True,
        has_replication=False, orthogonal_confirmation=False,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "conservation"),
    )
    assert anomaly_priority(breaker, policy=POLICY) == 0.0
    # Only orthogonal confirmation + replication unlocks any consideration.
    confirmed = _inputs(
        has_mechanism=False, observed_value=42.0, violates_conservation_law=True,
        has_replication=True, orthogonal_confirmation=True,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "conservation"),
    )
    assert anomaly_priority(confirmed, policy=POLICY) >= 0.0  # no crash; boost allowed


def test_g06_calibrated_requires_holdout():
    # Calibratable null but L2 holdout explicitly failed -> UNCALIBRATED.
    assert calibration_status(_inputs(holdout_passed=False)) == (
        CalibrationStatus.UNCALIBRATED
    )
    # holdout passed -> CALIBRATED.
    assert calibration_status(_inputs(holdout_passed=True)) == (
        CalibrationStatus.CALIBRATED
    )
    # None = deductive/single-obs carve-out -> CALIBRATED if null is calibratable.
    assert calibration_status(_inputs(holdout_passed=None)) == (
        CalibrationStatus.CALIBRATED
    )
    # No calibratable null -> UNCALIBRATED regardless of holdout.
    assert calibration_status(
        _inputs(null=_null(5.0, req=True, fetched=False))
    ) == CalibrationStatus.UNCALIBRATED


def test_g05_reserved_slot_requires_score_and_surprise():
    # Barely-L1 squatter: weak provenance/method -> low promotion score.
    squatter = _inputs(
        provenance_ok=False, method_integrity=0.05, null=_null(0.5),
        has_mechanism=False, has_replication=True, observed_value=100.0,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "lit"),
    )
    assert promotion_score(squatter) < POLICY.reserved_slot_min_promotion
    assert not reserved_slot_eligible(squatter, policy=POLICY)
    # Genuine paradigm-breaker: strong score + surprise + UNEXPLAINED_CONFIRMED.
    real = _inputs(
        provenance_ok=True, method_integrity=0.9, null=_null(8.0),
        has_mechanism=False, has_replication=True, observed_value=8.0,
        literature_expectation=LiteratureExpectation(0.0, 1.0, "lit"),
    )
    assert promotion_score(real) >= POLICY.reserved_slot_min_promotion
    assert reserved_slot_eligible(real, policy=POLICY)


def test_promotion_score_never_penalises_mechanism_absence():
    with_mech = _inputs(has_mechanism=True)
    without = _inputs(has_mechanism=False)
    # Mechanism presence is not a promotion-score term (it lives in anomaly track).
    assert promotion_score(with_mech) == promotion_score(without)

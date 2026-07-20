import json

import pytest

from sapiens.calibration import CalibrationReport, run_calibration
from sapiens.confidence import UncalibratedError, aggregate_confidence
from sapiens.fixtures import FixtureKind, fixture_suite
from sapiens.models import Evidence


def test_fixture_suite_labels_match_gate_behaviour():
    # run_calibration raises if any fixture's label disagrees with the gates.
    report = run_calibration(fixture_suite())
    assert len(report.outcomes) == 4


def test_calibration_report_rates_match_ground_truth():
    report = run_calibration(fixture_suite())
    assert report.known_good_total == 1
    assert report.known_good_accepted == 1
    assert report.known_bad_total == 3
    assert report.known_bad_caught == 3
    assert report.catch_rate == 1.0
    assert report.false_reject_rate == 0.0


def test_fixture_kinds_cover_documented_failure_modes():
    kinds = {fixture.kind for fixture in fixture_suite()}
    assert FixtureKind.KNOWN_GOOD in kinds
    assert FixtureKind.OVERFIT in kinds
    assert FixtureKind.LEAKAGE in kinds
    assert FixtureKind.DEGENERATE in kinds
    for fixture in fixture_suite():
        assert fixture.rationale  # every fixture explains itself


def test_report_is_json_serialisable_and_identified():
    report = run_calibration(fixture_suite())
    blob = json.dumps(report.to_dict())
    assert report.report_id in blob
    # Same fixtures ⇒ same report id (deterministic).
    assert run_calibration(fixture_suite()).report_id == report.report_id


def test_empty_suite_report_is_honest_about_thinness():
    report = run_calibration(())
    assert report.known_bad_total == 0
    assert report.catch_rate == 0.0
    assert report.false_reject_rate == 1.0  # no evidence: assume the worst
    assert not report.meets_minimum(min_known_bad=2, min_known_good=1)


def ev(eid, passed):
    return Evidence(eid, "cand-x", "internal", passed, "p", "synthetic-train", 1, 0.9)


def test_confidence_refused_without_calibration():
    with pytest.raises(UncalibratedError, match="no calibration"):
        aggregate_confidence((ev("a", True),), None)


def test_confidence_refused_with_thin_calibration():
    good_only = tuple(f for f in fixture_suite() if f.kind == FixtureKind.KNOWN_GOOD)
    thin = run_calibration(good_only)
    with pytest.raises(UncalibratedError, match="too thin"):
        aggregate_confidence((ev("a", True),), thin)


def test_confidence_refused_without_evidence():
    report = run_calibration(fixture_suite())
    with pytest.raises(UncalibratedError, match="no evidence"):
        aggregate_confidence((), report)


def test_calibrated_confidence_value_and_provenance():
    report = run_calibration(fixture_suite())
    result = aggregate_confidence((ev("a", True), ev("b", False)), report)
    assert result.raw_pass_fraction == 0.5
    assert result.catch_rate == 1.0
    assert result.value == 0.5  # raw * catch_rate
    assert result.calibration_report_id == report.report_id
    assert "not a probability" in result.caveat


def test_confidence_discounted_by_weak_calibration():
    weak = CalibrationReport(
        "weak-report",
        (),
        known_good_total=2,
        known_good_accepted=2,
        known_bad_total=4,
        known_bad_caught=2,
    )
    result = aggregate_confidence((ev("a", True),), weak)
    assert result.catch_rate == 0.5
    assert result.value == 0.5  # perfect evidence, halved by demonstrated weakness

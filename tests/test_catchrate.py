"""Catch-rate scoring harness (Phase 3) with regression thresholds."""

import json

from sapiens.catchrate import score_panel
from sapiens.fixtures import fixture_suite
from sapiens.reviewers import reference_panel
from sapiens.validation import synthetic_holdout_protocol

VOCAB = ("signal", "score", "data", "training", "replication", "holdout")


def make_report():
    panel = reference_panel(VOCAB, synthetic_holdout_protocol())
    return score_panel(panel, fixture_suite(), seed=0)


def test_panel_catches_every_seeded_bad_fixture():
    # Regression threshold on this suite: exact, not estimated (see caveat).
    report = make_report()
    assert report.known_bad_total == 3
    assert report.panel_catches == 3
    assert report.panel_catch_rate == 1.0


def test_panel_does_not_false_reject_known_good():
    report = make_report()
    assert report.known_good_total == 1
    assert report.known_good_approved == 1
    assert report.false_reject_rate == 0.0


def test_per_role_attribution_is_honest():
    report = make_report()
    stats = {entry.role: entry for entry in report.per_role}
    assert set(stats) == {
        "statistician",
        "domain-theorist",
        "methodologist",
        "devils-advocate",
    }
    # The theorist's job is coherence, not bias: zero catches is the honest
    # result, and the report must show it rather than inflate roles.
    assert stats["domain-theorist"].bad_fixtures_objected == 0
    assert stats["statistician"].bad_fixtures_objected == 3
    assert stats["devils-advocate"].bad_fixtures_objected >= 2


def test_report_serialisable_with_caveat():
    report = make_report()
    blob = json.dumps(report.to_dict())
    assert "do not estimate" in report.caveat
    assert "statistician" in blob

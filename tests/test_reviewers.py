"""Reference reviewers against the seeded fixture suite."""

from sapiens.fixtures import FixtureKind, fixture_suite
from sapiens.models import Candidate, Evidence
from sapiens.review import Severity, VerdictKind
from sapiens.reviewers import (
    DevilsAdvocateReviewer,
    DomainTheoristReviewer,
    MethodologistReviewer,
    StatisticianReviewer,
    reference_panel,
)
from sapiens.validation import synthetic_holdout_protocol

FIXTURES = {f.kind: f for f in fixture_suite()}
PROTOCOL = synthetic_holdout_protocol()
VOCAB = ("signal", "score", "data", "training", "replication", "holdout")


def review(reviewer, fixture, round_number=1):
    return reviewer.review(
        fixture.candidate,
        fixture.internal + fixture.replication,
        round_number=round_number,
        prior_objections=(),
        seed=0,
    )


class TestStatistician:
    reviewer = StatisticianReviewer(PROTOCOL)

    def test_approves_known_good(self):
        assert review(self.reviewer, FIXTURES[FixtureKind.KNOWN_GOOD]).verdict == (
            VerdictKind.APPROVE
        )

    def test_catches_overfit_at_l2(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.OVERFIT])
        assert verdict.verdict == VerdictKind.OBJECT
        assert any(
            o.severity == Severity.BLOCKING and "L2 gate" in o.text for o in verdict.objections
        )

    def test_catches_leakage_at_l2(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.LEAKAGE])
        assert verdict.verdict == VerdictKind.OBJECT
        assert any("leakage" in o.text for o in verdict.objections)

    def test_catches_degenerate_at_l1(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.DEGENERATE])
        assert verdict.verdict == VerdictKind.OBJECT
        assert any("L1 gate" in o.text for o in verdict.objections)


class TestMethodologist:
    reviewer = MethodologistReviewer()

    def test_approves_known_good(self):
        assert review(self.reviewer, FIXTURES[FixtureKind.KNOWN_GOOD]).verdict == (
            VerdictKind.APPROVE
        )

    def test_catches_cross_stage_dataset_reuse(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.LEAKAGE])
        assert verdict.verdict == VerdictKind.OBJECT
        assert any(
            o.severity == Severity.BLOCKING and "leakage signal" in o.text
            for o in verdict.objections
        )

    def test_blocks_on_empty_evidence(self):
        verdict = self.reviewer.review(
            Candidate("c", "d", "claim about signal"),
            (),
            round_number=1,
            prior_objections=(),
            seed=0,
        )
        assert verdict.verdict == VerdictKind.OBJECT
        assert verdict.objections[0].severity == Severity.BLOCKING


class TestDomainTheorist:
    reviewer = DomainTheoristReviewer(VOCAB)

    def test_approves_all_fixture_claims(self):
        # Fixture claims are deliberately vocabulary-coherent so per-role
        # attribution stays clean: the theorist's job is coherence, not bias.
        for fixture in FIXTURES.values():
            assert review(self.reviewer, fixture).verdict == VerdictKind.APPROVE

    def test_incoherent_claim_escalates_across_rounds(self):
        candidate = Candidate("c", "d", "zzz qqq nothing coherent")
        evidence = (Evidence("e", "c", "internal", True, "p", "d", 1, 0.9),)
        first = self.reviewer.review(
            candidate, evidence, round_number=1, prior_objections=(), seed=0
        )
        second = self.reviewer.review(
            candidate, evidence, round_number=2, prior_objections=(), seed=0
        )
        assert first.objections[0].severity == Severity.MAJOR
        assert second.objections[0].severity == Severity.BLOCKING


class TestDevilsAdvocate:
    reviewer = DevilsAdvocateReviewer()

    def test_approves_known_good(self):
        assert review(self.reviewer, FIXTURES[FixtureKind.KNOWN_GOOD]).verdict == (
            VerdictKind.APPROVE
        )

    def test_catches_degenerate_signature(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.DEGENERATE])
        assert any(
            o.severity == Severity.BLOCKING and "degenerate" in o.text
            for o in verdict.objections
        )

    def test_catches_leakage_signature(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.LEAKAGE])
        assert any(
            o.severity == Severity.BLOCKING and "leakage" in o.text
            for o in verdict.objections
        )

    def test_overfit_alone_not_advocate_territory(self):
        # Overfit passes the advocate's signature checks; the statistician
        # owns that catch. Attribution honesty matters for per-role rates.
        verdict = review(self.reviewer, FIXTURES[FixtureKind.OVERFIT])
        assert all(
            o.severity != Severity.BLOCKING or "single run" in o.text
            for o in verdict.objections
        )

    def test_perfect_scores_escalate(self):
        candidate = Candidate("c", "d", "signal claim")
        evidence = (
            Evidence("e1", "c", "internal", True, "p", "train", 1, 1.0),
            Evidence("e2", "c", "replication", True, "p", "holdout", 2, 1.0),
        )
        first = self.reviewer.review(
            candidate, evidence, round_number=1, prior_objections=(), seed=0
        )
        second = self.reviewer.review(
            candidate, evidence, round_number=2, prior_objections=(), seed=0
        )
        assert any(o.severity == Severity.MAJOR for o in first.objections)
        assert any(o.severity == Severity.BLOCKING for o in second.objections)

    def test_thin_stage_is_minor_caveat(self):
        verdict = review(self.reviewer, FIXTURES[FixtureKind.LEAKAGE])
        # leakage fixture has one run per stage: minor caveat rides alongside
        assert any(o.severity == Severity.MINOR for o in verdict.objections)


def test_reference_panel_has_four_unique_roles():
    panel = reference_panel(VOCAB, PROTOCOL)
    assert len(panel.reviewers) == 4
    assert len({reviewer.role for reviewer in panel.reviewers}) == 4

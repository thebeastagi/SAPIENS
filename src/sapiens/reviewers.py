"""Deterministic reference reviewers for the L3 panel (Phase 3).

Four role-specialized reviewers, each a pure function of (candidate,
evidence, round, prior objections, seed). They overlap the Phase-2 gates
deliberately: the statistician re-runs them as an independent check, and
the devil's advocate hunts planted-bias signatures directly. Redundancy is
the point of a panel.

Escalation policy (uniform): findings are recomputed every round; a MAJOR
finding re-affirmed in round 2 or later escalates to BLOCKING. MINOR stays
MINOR. The seed is accepted for interface uniformity; every check here is
deterministic without it.
"""

from __future__ import annotations

from .calibration import CalibrationReport
from .models import Candidate, Evidence
from .review import (
    Objection,
    ReviewerRole,
    ReviewerVerdict,
    ReviewPanel,
    Severity,
    VerdictKind,
)
from .validation import (
    HoldoutProtocol,
    check_internal_consistency,
    check_replication,
)


def _objection(
    role: ReviewerRole, severity: Severity, text: str, round_number: int, index: int
) -> Objection:
    return Objection(
        f"{role.value}-r{round_number}-{index}",
        role,
        severity,
        text,
        round_number,
    )


def _escalate(severity: Severity, round_number: int) -> Severity:
    if severity == Severity.MAJOR and round_number >= 2:
        return Severity.BLOCKING
    return severity


class StatisticianReviewer:
    """Re-runs the Phase-2 gates as an independent statistical check."""

    role = ReviewerRole.STATISTICIAN

    def __init__(
        self,
        protocol: HoldoutProtocol | None = None,
        calibration: CalibrationReport | None = None,
    ) -> None:
        self._protocol = protocol
        self._calibration = calibration

    def review(
        self,
        candidate: Candidate,
        evidence: tuple[Evidence, ...],
        *,
        round_number: int,
        prior_objections: tuple[Objection, ...],
        seed: int,
    ) -> ReviewerVerdict:
        objections: list[Objection] = []
        internal = tuple(item for item in evidence if item.kind == "internal")
        replication = tuple(item for item in evidence if item.kind == "replication")
        l1 = check_internal_consistency(evidence)
        if not l1.passed:
            for reason in l1.reasons:
                objections.append(
                    _objection(
                        self.role, Severity.BLOCKING, f"L1 gate: {reason}", round_number, 0
                    )
                )
        if self._protocol is not None:
            l2 = check_replication(internal, replication, self._protocol)
            if not l2.passed:
                for reason in l2.reasons:
                    objections.append(
                        _objection(
                            self.role, Severity.BLOCKING, f"L2 gate: {reason}", round_number, 1
                        )
                    )
        if (
            self._calibration is not None
            and self._calibration.known_bad_total > 0
            and self._calibration.catch_rate < 1.0
        ):
            objections.append(
                _objection(
                    self.role,
                    Severity.MINOR,
                    f"calibration report {self._calibration.report_id} shows gates catch "
                    f"only {self._calibration.catch_rate:.2f} of known-bad fixtures",
                    round_number,
                    2,
                )
            )
        if objections:
            return ReviewerVerdict(
                self.role,
                VerdictKind.OBJECT,
                f"statistical checks found {len(objections)} issue(s)",
                tuple(objections),
            )
        return ReviewerVerdict(
            self.role, VerdictKind.APPROVE, "statistical gates satisfied"
        )


class MethodologistReviewer:
    """Protocol and dataset hygiene: consistency within stages, no cross-stage reuse."""

    role = ReviewerRole.METHODOLOGIST

    def review(
        self,
        candidate: Candidate,
        evidence: tuple[Evidence, ...],
        *,
        round_number: int,
        prior_objections: tuple[Objection, ...],
        seed: int,
    ) -> ReviewerVerdict:
        objections: list[Objection] = []
        if not evidence:
            objections.append(
                _objection(
                    self.role, Severity.BLOCKING, "no evidence to review", round_number, 0
                )
            )
        by_stage: dict[str, list[Evidence]] = {}
        for item in evidence:
            by_stage.setdefault(item.kind, []).append(item)
        index = 1
        for stage, items in sorted(by_stage.items()):
            protocols = {item.protocol for item in items}
            if len(protocols) > 1:
                objections.append(
                    _objection(
                        self.role,
                        Severity.BLOCKING,
                        f"stage {stage!r} mixes protocols {sorted(protocols)}",
                        round_number,
                        index,
                    )
                )
                index += 1
        # Leakage signal: an internal-stage (train) dataset reappearing in a
        # later stage. Holdout reuse across replication/review is legitimate.
        internal_datasets = {item.dataset for item in by_stage.get("internal", [])}
        later_datasets = {
            item.dataset
            for stage, items in by_stage.items()
            if stage != "internal"
            for item in items
        }
        reused = internal_datasets & later_datasets
        if reused:
            objections.append(
                _objection(
                    self.role,
                    Severity.BLOCKING,
                    f"train dataset(s) {sorted(reused)} reappear beyond the internal "
                    "stage — leakage signal",
                    round_number,
                    index,
                )
            )
        if objections:
            return ReviewerVerdict(
                self.role,
                VerdictKind.OBJECT,
                f"methodology checks found {len(objections)} issue(s)",
                tuple(objections),
            )
        return ReviewerVerdict(
            self.role, VerdictKind.APPROVE, "protocol and dataset hygiene satisfied"
        )


class DomainTheoristReviewer:
    """Claim coherence: the claim must be expressible in the domain vocabulary."""

    role = ReviewerRole.DOMAIN_THEORIST

    def __init__(self, vocabulary: tuple[str, ...]) -> None:
        if not vocabulary:
            raise ValueError("domain theorist requires a vocabulary")
        self._vocabulary = vocabulary

    def review(
        self,
        candidate: Candidate,
        evidence: tuple[Evidence, ...],
        *,
        round_number: int,
        prior_objections: tuple[Objection, ...],
        seed: int,
    ) -> ReviewerVerdict:
        haystack = " ".join(
            [candidate.claim, *(str(key) for key in candidate.parameters)]
        ).lower()
        hits = [term for term in self._vocabulary if term.lower() in haystack]
        if not hits:
            severity = _escalate(Severity.MAJOR, round_number)
            return ReviewerVerdict(
                self.role,
                VerdictKind.OBJECT,
                "claim is not expressible in the declared domain vocabulary",
                (
                    _objection(
                        self.role,
                        severity,
                        f"claim references none of {self._vocabulary}",
                        round_number,
                        0,
                    ),
                ),
            )
        return ReviewerVerdict(
            self.role,
            VerdictKind.APPROVE,
            f"claim coheres with domain vocabulary ({', '.join(hits)})",
        )


class DevilsAdvocateReviewer:
    """Adversarial hunt for seeded-bias signatures. Never satisfied by default."""

    role = ReviewerRole.DEVILS_ADVOCATE

    def review(
        self,
        candidate: Candidate,
        evidence: tuple[Evidence, ...],
        *,
        round_number: int,
        prior_objections: tuple[Objection, ...],
        seed: int,
    ) -> ReviewerVerdict:
        objections: list[Objection] = []
        # Signature 1: constant scores across independent seeds (degenerate).
        by_stage: dict[str, list[Evidence]] = {}
        for item in evidence:
            by_stage.setdefault(item.kind, []).append(item)
        index = 0
        for stage, items in sorted(by_stage.items()):
            seeds = {item.seed for item in items}
            scores = [item.score for item in items if item.score is not None]
            if len(seeds) >= 3 and len(scores) >= 3 and len(set(scores)) == 1:
                objections.append(
                    _objection(
                        self.role,
                        Severity.BLOCKING,
                        f"constant score {scores[0]} across {len(seeds)} seeds in stage "
                        f"{stage!r} — degenerate signature",
                        round_number,
                        index,
                    )
                )
                index += 1
        # Signature 2: a train (internal-stage) dataset reappearing in a later
        # stage (leakage). Holdout reuse across replication/review is fine.
        internal_datasets = {item.dataset for item in by_stage.get("internal", [])}
        for stage, items in sorted(by_stage.items()):
            if stage == "internal":
                continue
            overlap = internal_datasets & {item.dataset for item in items}
            if overlap:
                objections.append(
                    _objection(
                        self.role,
                        Severity.BLOCKING,
                        f"train dataset(s) {sorted(overlap)} reappear in stage "
                        f"{stage!r} — leakage signature",
                        round_number,
                        index,
                    )
                )
                index += 1
        # Signature 3: everything perfect (all scores 1.0) — too clean to trust.
        all_scores = [item.score for item in evidence if item.score is not None]
        if all_scores and all(score == 1.0 for score in all_scores):
            objections.append(
                _objection(
                    self.role,
                    _escalate(Severity.MAJOR, round_number),
                    "every score is exactly 1.0 — implausibly perfect",
                    round_number,
                    index,
                )
            )
            index += 1
        # Signature 4: thin stages (a single run decides a stage). Caveat only.
        thin = [stage for stage, items in sorted(by_stage.items()) if len(items) == 1]
        if thin:
            objections.append(
                _objection(
                    self.role,
                    Severity.MINOR,
                    f"stage(s) {thin} rest on a single run",
                    round_number,
                    index,
                )
            )
        if objections:
            return ReviewerVerdict(
                self.role,
                VerdictKind.OBJECT,
                f"adversarial hunt found {len(objections)} signature(s)",
                tuple(objections),
            )
        return ReviewerVerdict(
            self.role,
            VerdictKind.APPROVE,
            "adversarial hunt found no seeded-bias signature",
        )


def reference_panel(
    vocabulary: tuple[str, ...],
    protocol: HoldoutProtocol | None = None,
    calibration: CalibrationReport | None = None,
    *,
    max_rounds: int = 3,
) -> ReviewPanel:
    """A panel of the four deterministic reference reviewers."""
    return ReviewPanel(
        (
            StatisticianReviewer(protocol, calibration),
            DomainTheoristReviewer(vocabulary),
            MethodologistReviewer(),
            DevilsAdvocateReviewer(),
        ),
        max_rounds=max_rounds,
    )

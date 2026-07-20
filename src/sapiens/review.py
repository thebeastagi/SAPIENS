"""Structured L3 review panels (Phase 3).

A panel is a bounded, deterministic, multi-round protocol over typed
reviewer verdicts. Four roles are defined — statistician, domain theorist,
methodologist, devil's advocate — each emitting approve / object / abstain
verdicts with severity-graded objections and rationales.

Protocol (deliberately strict, documented here and nowhere else):

1. **Round 1** — every reviewer verdicts independently over the candidate's
   recorded evidence.
2. **Objection lifecycle** — an objection is RAISED in its round; in each
   later round its raiser must re-affirm it (SUSTAINED) or drop it
   (WITHDRAWN). Objections cannot silently vanish: the transcript records
   every transition.
3. **Rebuttal rounds** — while any objection stands and the round budget
   lasts, the panel convenes another round. Reference reviewers escalate a
   re-affirmed MAJOR to BLOCKING; MINOR findings stay MINOR.
4. **Disagreement gate** — the panel approves only if no MAJOR or BLOCKING
   objection is sustained in the final round. MINOR objections are recorded
   as standing caveats in the transcript but do not block: the gate is
   strict on substance, tolerant of caveats. L3 is the last automated rung
   before the human L4 gate, so any substantive disagreement rejects.

Panels produce :class:`PanelReport` data — the kernel may record it as
review evidence, but the report itself is the verdict, never a promotion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .models import Candidate, Evidence


class ReviewerRole(Enum):
    STATISTICIAN = "statistician"
    DOMAIN_THEORIST = "domain-theorist"
    METHODOLOGIST = "methodologist"
    DEVILS_ADVOCATE = "devils-advocate"


class VerdictKind(Enum):
    APPROVE = "approve"
    OBJECT = "object"
    ABSTAIN = "abstain"


class Severity(Enum):
    MINOR = "minor"
    MAJOR = "major"
    BLOCKING = "blocking"


class ObjectionStatus(Enum):
    RAISED = "raised"
    SUSTAINED = "sustained"
    WITHDRAWN = "withdrawn"


class PanelOutcome(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Objection:
    objection_id: str
    role: ReviewerRole
    severity: Severity
    text: str
    raised_round: int

    def __post_init__(self) -> None:
        if not self.objection_id or not self.text:
            raise ValueError("objections require an id and text")
        if self.raised_round < 1:
            raise ValueError("rounds are 1-indexed")

    @property
    def key(self) -> str:
        """Identity across rounds: same reviewer, same concern."""
        return hashlib.sha256(f"{self.role.value}|{self.text}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ReviewerVerdict:
    role: ReviewerRole
    verdict: VerdictKind
    rationale: str
    objections: tuple[Objection, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict != VerdictKind.OBJECT and self.objections:
            raise ValueError("only an objecting verdict carries objections")
        if self.verdict == VerdictKind.OBJECT and not self.objections:
            raise ValueError("an objecting verdict must raise at least one objection")
        if not self.rationale:
            raise ValueError("every verdict requires a rationale")
        for objection in self.objections:
            if objection.role != self.role:
                raise ValueError("objections must belong to their verdict's role")


@dataclass(frozen=True)
class ReviewRound:
    round_number: int
    verdicts: tuple[ReviewerVerdict, ...]

    def objections(self) -> tuple[Objection, ...]:
        return tuple(obj for verdict in self.verdicts for obj in verdict.objections)


@runtime_checkable
class Reviewer(Protocol):
    """A role-specialized, deterministic reviewer. Pure function of its inputs."""

    @property
    def role(self) -> ReviewerRole: ...

    def review(
        self,
        candidate: Candidate,
        evidence: tuple[Evidence, ...],
        *,
        round_number: int,
        prior_objections: tuple[Objection, ...],
        seed: int,
    ) -> ReviewerVerdict: ...


@dataclass(frozen=True)
class PanelReport:
    candidate_id: str
    outcome: PanelOutcome
    rounds: tuple[ReviewRound, ...]
    sustained_blocking: tuple[Objection, ...]
    withdrawn: tuple[Objection, ...]
    lifecycle: tuple[tuple[str, ObjectionStatus], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "outcome": self.outcome.value,
            "rounds": [
                {
                    "round_number": r.round_number,
                    "verdicts": [
                        {
                            "role": v.role.value,
                            "verdict": v.verdict.value,
                            "rationale": v.rationale,
                            "objections": [
                                {
                                    "objection_id": o.objection_id,
                                    "severity": o.severity.value,
                                    "text": o.text,
                                    "raised_round": o.raised_round,
                                }
                                for o in v.objections
                            ],
                        }
                        for v in r.verdicts
                    ],
                }
                for r in self.rounds
            ],
            "sustained_blocking": [o.text for o in self.sustained_blocking],
            "withdrawn": [o.text for o in self.withdrawn],
            "lifecycle": {key: status.value for key, status in self.lifecycle},
        }

    @property
    def report_id(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ReviewPanel:
    """Convenes reviewers over bounded multi-round protocols. Deterministic."""

    def __init__(self, reviewers: tuple[Reviewer, ...], *, max_rounds: int = 3) -> None:
        if not reviewers:
            raise ValueError("a panel requires at least one reviewer")
        roles = [reviewer.role for reviewer in reviewers]
        if len(set(roles)) != len(roles):
            raise ValueError("reviewer roles must be unique on a panel")
        if max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        self._reviewers = reviewers
        self._max_rounds = max_rounds

    @property
    def reviewers(self) -> tuple[Reviewer, ...]:
        return self._reviewers

    def convene(
        self, candidate: Candidate, evidence: tuple[Evidence, ...], *, seed: int
    ) -> PanelReport:
        rounds: list[ReviewRound] = []
        active: dict[str, Objection] = {}  # key -> latest objection form
        withdrawn: list[Objection] = []
        for round_number in range(1, self._max_rounds + 1):
            prior = tuple(active.values())
            verdicts = tuple(
                reviewer.review(
                    candidate,
                    evidence,
                    round_number=round_number,
                    prior_objections=prior,
                    seed=seed,
                )
                for reviewer in self._reviewers
            )
            rounds.append(ReviewRound(round_number, verdicts))
            current: dict[str, Objection] = {}
            for verdict in verdicts:
                for objection in verdict.objections:
                    key = objection.key
                    if key in active:
                        current[key] = Objection(
                            objection.objection_id,
                            objection.role,
                            objection.severity,
                            objection.text,
                            active[key].raised_round,
                        )
                    else:
                        current[key] = objection
            for key, previous in active.items():
                if key not in current:
                    withdrawn.append(previous)
            active = current
            # Continue convening while any objection stands: rebuttal rounds
            # give raisers the chance to sustain, escalate, or withdraw.
            # Termination is bounded by the round budget.
            if not active:
                break  # clean consensus (or everything withdrawn)
        final = rounds[-1]
        sustained_blocking = tuple(
            obj for obj in active.values() if obj.severity == Severity.BLOCKING
        )
        sustained_substantive = tuple(
            obj
            for obj in active.values()
            if obj.severity in (Severity.MAJOR, Severity.BLOCKING)
        )
        approved = not sustained_substantive
        lifecycle: list[tuple[str, ObjectionStatus]] = []
        for key, obj in active.items():
            status = (
                ObjectionStatus.RAISED
                if obj.raised_round == final.round_number
                else ObjectionStatus.SUSTAINED
            )
            lifecycle.append((key, status))
        for obj in withdrawn:
            lifecycle.append((obj.key, ObjectionStatus.WITHDRAWN))
        return PanelReport(
            candidate.candidate_id,
            PanelOutcome.APPROVED if approved else PanelOutcome.REJECTED,
            tuple(rounds),
            sustained_blocking,
            tuple(withdrawn),
            tuple(lifecycle),
        )

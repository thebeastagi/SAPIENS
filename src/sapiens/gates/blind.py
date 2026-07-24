"""Phase 3 — genuine blind re-run harness.

The shipped benchmark set leaked ``ground_truth`` / ``expected_verdict`` /
``gates_probed`` / ``how_*`` **inline** — it was never sealed, so it cannot
certify the pipeline. This module provides the missing machinery:

* **strip** the key fields from every candidate (:func:`strip_to_blind`);
* **expand** the set with historical positives + fresh decoys (from
  :mod:`.corpus`);
* **separate custody**: the key is split out into a :class:`CustodyKey` whose
  SHA-256 commitment is published while the labels stay sealed — the scorer runs
  against the stripped inputs and never sees the key;
* **blind scoring runner** (:func:`blind_run`) executes the Phase-0/1/2-patched
  pipeline on the stripped inputs and emits verdicts;
* **grade** (:func:`grade`) is the *separate-custody* step that finally opens the
  key and measures kill-rate / recovery / abstention.

The single thing this validates: does the mandatory null layer actually catch
FP-01/02/04/08 when the answer is not inline?
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from enum import Enum

from .corpus import CorpusItem
from .pipeline import GateOutcome, evaluate_family
from .promotion import GateInputs
from .thresholds import ThresholdPolicy, Tier


class Verdict(str, Enum):
    CLAIM = "claim"  # CONFIRM tier: claim-eligible (human co-sign still required)
    ENTERED = "entered"  # ENTRY tier: on the shortlist as a clean signal
    FLAG = "flag"  # surfaced for human attention but not a clean signal
    ABSTAIN = "abstain"  # produced no actionable signal


def strip_to_blind(item: CorpusItem) -> GateInputs:
    """Return only the model-visible inputs; drop every key/answer field.

    ``ground_truth`` / ``expected_verdict`` / ``gates_probed`` /
    ``how_old_gate_would_kill`` / ``illegitimate_reward`` never cross into the
    scored object — the whole point of Phase 3.
    """
    return item.inputs


@dataclass(frozen=True)
class CustodyKey:
    """The sealed answer key, held by a second party (separate custody)."""

    labels: dict[str, str]  # candidate_id -> "positive" | "negative"
    commitment: str  # sha256 over the sorted labels; publishable before scoring

    @staticmethod
    def build(items: list[CorpusItem]) -> CustodyKey:
        labels = {it.inputs.candidate_id: it.label for it in items}
        payload = json.dumps(labels, sort_keys=True, separators=(",", ":"))
        return CustodyKey(
            labels=labels,
            commitment=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    def verify_commitment(self) -> bool:
        payload = json.dumps(self.labels, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest() == self.commitment


@dataclass(frozen=True)
class SealedSet:
    """A blinded candidate set + a separately-held custody key + its commitment."""

    blind_inputs: tuple[GateInputs, ...]  # the scorer sees ONLY these
    key: CustodyKey  # held by a second party; opened only at grade()
    seed: int


def seal(items: list[CorpusItem], *, seed: int = 0) -> SealedSet:
    """Strip, shuffle, and split custody. The scorer receives ``blind_inputs``
    and the published ``key.commitment``; the labels stay in :class:`CustodyKey`.
    """
    rng = random.Random(seed)
    shuffled = list(items)
    rng.shuffle(shuffled)
    blind = tuple(strip_to_blind(it) for it in shuffled)
    return SealedSet(blind_inputs=blind, key=CustodyKey.build(items), seed=seed)


def outcome_to_verdict(o: GateOutcome) -> Verdict:
    """Map a gate outcome onto the blind-scoring verdict vocabulary."""
    if o.tier == Tier.CONFIRM:
        return Verdict.CLAIM
    if o.tier == Tier.ENTRY and o.entered:
        return Verdict.ENTERED
    # Surfaced-but-not-a-clean-signal: reserved slot, instrument-systematic,
    # or an UNCALIBRATED candidate that still carries a null sigma / surprise.
    if (
        o.reserved_slot
        or o.instrument_systematic_flag
        or (o.sigma_under_null is not None)
        or o.surprise_sigma > 0.0
    ):
        return Verdict.FLAG
    return Verdict.ABSTAIN


def blind_run(
    sealed: SealedSet,
    *,
    policy: ThresholdPolicy | None = None,
    run_id: str = "blind-run",
) -> dict[str, Verdict]:
    """Run the patched pipeline on the stripped inputs — no key in scope."""
    result = evaluate_family(list(sealed.blind_inputs), policy=policy, run_id=run_id)
    return {o.candidate_id: outcome_to_verdict(o) for o in result.outcomes}


@dataclass(frozen=True)
class BlindReport:
    """Kill-rate / recovery / abstention, opened by the custody holder."""

    positives: int
    negatives: int
    recovered: int  # positives surfaced (CLAIM/ENTERED/FLAG)
    killed: int  # negatives not admitted as a clean signal (FLAG/ABSTAIN)
    abstained_positives: int  # positives that produced no signal (silence)
    leaks: tuple[str, ...] = field(default_factory=tuple)  # negatives that leaked

    @property
    def recovery_rate(self) -> float:
        return self.recovered / self.positives if self.positives else 0.0

    @property
    def kill_rate(self) -> float:
        return self.killed / self.negatives if self.negatives else 0.0

    @property
    def abstention_rate(self) -> float:
        return self.abstained_positives / self.positives if self.positives else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "positives": self.positives,
            "negatives": self.negatives,
            "recovered": self.recovered,
            "killed": self.killed,
            "recovery_rate": round(self.recovery_rate, 4),
            "kill_rate": round(self.kill_rate, 4),
            "abstention_rate": round(self.abstention_rate, 4),
            "leaks": list(self.leaks),
        }


def grade(verdicts: dict[str, Verdict], key: CustodyKey) -> BlindReport:
    """Separate-custody grading: open the key and measure the three rates.

    * A **positive** is *recovered* if it was surfaced at all (CLAIM/ENTERED/
      FLAG) — the recalibration's sensitivity goal.
    * A **negative** is *killed* unless it was admitted as a clean signal
      (CLAIM or ENTERED); FLAG/ABSTAIN both count as caught. A negative that
      reaches CLAIM/ENTERED is a **leak**.
    """
    if not key.verify_commitment():
        raise ValueError("custody key failed its own commitment check")
    pos = neg = recovered = killed = abstained = 0
    leaks: list[str] = []
    for cid, label in key.labels.items():
        v = verdicts.get(cid, Verdict.ABSTAIN)
        if label == "positive":
            pos += 1
            if v in (Verdict.CLAIM, Verdict.ENTERED, Verdict.FLAG):
                recovered += 1
            if v == Verdict.ABSTAIN:
                abstained += 1
        else:  # negative
            neg += 1
            if v in (Verdict.CLAIM, Verdict.ENTERED):
                leaks.append(cid)
            else:
                killed += 1
    return BlindReport(
        positives=pos,
        negatives=neg,
        recovered=recovered,
        killed=killed,
        abstained_positives=abstained,
        leaks=tuple(sorted(leaks)),
    )

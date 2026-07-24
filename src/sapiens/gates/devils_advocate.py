"""B-06 — DevilsAdvocate permutation test at ~3-sigma-equiv.

When the DevilsAdvocate reviewer finds a strong correlation between a
candidate's "signal" and a nuisance/confound (Pearson r >= 0.90 by default),
a naive pipeline can mistake the confound for the discovery. The fix is a cheap
label-permutation test on the *independence* null: shuffle the confound many
times, rebuild |r|, and ask whether the observed correlation is beyond chance.
If the signal<->confound correlation IS significant at ~3-sigma-equiv
(empirical p <= 2-sided 3-sigma ~= 0.0027) the confound **explains** the signal,
so the candidate must NOT earn a boost (``passed = False``). Only a candidate
whose signal is *not* significantly tied to the confound survives.

Deterministic given a seed. Pure stdlib (``random``, ``statistics``, ``math``).
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

from .fdr import sigma_to_pvalue


def pearson_r(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation; 0.0 for degenerate (zero-variance) inputs."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return num / (dx * dy)


@dataclass(frozen=True)
class PermutationResult:
    triggered: bool  # was |r| >= trigger_r, i.e. did the guard fire at all
    observed_r: float
    empirical_p: float | None  # None when not triggered
    passed: bool  # True if the signal survives (or guard did not fire)
    n_permutations: int


def devils_advocate_permutation(
    signal: list[float],
    confound: list[float],
    *,
    trigger_r: float = 0.90,
    alpha_sigma: float = 3.0,
    n_permutations: int = 2000,
    seed: int = 0,
) -> PermutationResult:
    """Run the B-06 guard: permutation test only when ``|r| >= trigger_r``.

    ``passed`` is True either because the guard never fired (weak confound
    correlation) or because the observed signal<->confound correlation is NOT
    significant at ~3-sigma-equiv. A small permutation p (significant
    correlation) means the apparent signal is explained by the confound, so the
    candidate fails.
    """
    observed = abs(pearson_r(signal, confound))
    if observed < trigger_r:
        return PermutationResult(
            triggered=False,
            observed_r=observed,
            empirical_p=None,
            passed=True,
            n_permutations=0,
        )
    rng = random.Random(seed)
    shuffled = list(confound)
    at_least_as_extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(shuffled)
        if abs(pearson_r(signal, shuffled)) >= observed:
            at_least_as_extreme += 1
    # +1 smoothing (Phipson-Smyth) so p is never exactly 0.
    empirical_p = (at_least_as_extreme + 1) / (n_permutations + 1)
    alpha = sigma_to_pvalue(alpha_sigma)
    return PermutationResult(
        triggered=True,
        observed_r=observed,
        empirical_p=empirical_p,
        passed=empirical_p > alpha,
        n_permutations=n_permutations,
    )

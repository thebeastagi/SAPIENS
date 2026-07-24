"""Family-wide Benjamini-Hochberg FDR and sigma<->p conversions.

The recalibration (GATES-RECALIBRATION.md) moves *all* remaining specificity
onto the null/FDR layer. The single most important property here: FDR is
computed **across the candidate family**, not per-candidate. A per-test
p<0.05 alone is a multiplicity trap (FP-09 / the look-elsewhere effect); the
family-wide BH step is what actually controls the false-discovery rate when
many candidates are screened at once.

Pure stdlib (``math`` only). Two-sided Gaussian tail is used to move between a
"sigma-equivalent" and a p-value so a domain that reasons in sigma (physics)
and one that reasons in q-values (bio) share one arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def sigma_to_pvalue(sigma: float) -> float:
    """Two-sided Gaussian tail probability for a |z| = ``sigma`` deviation.

    ``sigma_to_pvalue(3) ~= 0.0027``, ``sigma_to_pvalue(5) ~= 5.7e-7``.
    Negative sigma is treated as its magnitude; 0 -> 1.0.
    """
    z = abs(float(sigma))
    return math.erfc(z / math.sqrt(2.0))


def pvalue_to_sigma(pvalue: float) -> float:
    """Inverse of :func:`sigma_to_pvalue` (two-sided). Clamps to (0, 1)."""
    p = min(max(float(pvalue), 1e-300), 1.0)
    # erfc(x) = p  ->  x = erfcinv(p); invert erfc via bisection (monotone).
    lo, hi = 0.0, 40.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if math.erfc(mid) > p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi) * math.sqrt(2.0)


@dataclass(frozen=True)
class FDRResult:
    """Outcome of a family-wide BH-FDR run for a single member."""

    index: int
    pvalue: float
    qvalue: float  # BH-adjusted p (monotone), the family-corrected significance
    rejected: bool  # significant at the requested family q


def benjamini_hochberg(pvalues: list[float], q: float = 0.05) -> list[FDRResult]:
    """Benjamini-Hochberg step-up across a whole candidate *family*.

    Returns one :class:`FDRResult` per input p-value **in the original order**.
    ``rejected`` is True where the candidate survives the family-wide FDR
    control at level ``q``. An empty family returns an empty list.
    """
    if not 0.0 < q < 1.0:
        raise ValueError("q must be in (0, 1)")
    n = len(pvalues)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvalues[i])
    # Monotone BH-adjusted q-values, computed from the largest rank down.
    adjusted = [0.0] * n
    prev = 1.0
    for rank in range(n, 0, -1):
        i = order[rank - 1]
        raw = min(1.0, pvalues[i] * n / rank)
        prev = min(prev, raw)
        adjusted[i] = prev
    # Rejection threshold: largest rank k with p_(k) <= k/n * q.
    max_k = 0
    for rank in range(1, n + 1):
        i = order[rank - 1]
        if pvalues[i] <= (rank / n) * q:
            max_k = rank
    reject_below = pvalues[order[max_k - 1]] if max_k > 0 else -1.0
    return [
        FDRResult(
            index=i,
            pvalue=pvalues[i],
            qvalue=adjusted[i],
            rejected=pvalues[i] <= reject_below,
        )
        for i in range(n)
    ]

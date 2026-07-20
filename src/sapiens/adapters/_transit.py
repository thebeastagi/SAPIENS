"""Stdlib transit-search primitives for the Kepler photometry adapter.

Ported from this repository's own Apache-2.0 `demos/ledger-grok` pipeline
(same methods, tuned for bounded CI runtime): running-median detrend, an
unweighted box-least-squares-style matched filter over a uniform frequency
grid with a refine pass, phase-fold measurement (depth / SNR / epoch /
odd-even / secondary), and harmonic power checks. Pure standard library;
no network; no astrophysics claims beyond arithmetic on the input curve.

The Kepler-10 C transit mask (BKJD 138.54–138.86, a ~450 ppm event from a
different, also already-known planet) is applied by the caller and
disclosed in every result, exactly as the demo does.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

DEFAULT_DURATIONS = (0.03, 0.05, 0.07, 0.09, 0.11)

# Known Kepler-10 C transit inside the Q1 segment; masked and disclosed.
MASK_EVENTS = ({"t_start_bkjd": 138.54, "t_end_bkjd": 138.86, "label": "Kepler-10 C"},)


class DataIntegrityError(RuntimeError):
    """Bundled data failed its pinned checksum, or a curve is unusable."""


def load_csv(path: str | Path) -> tuple[list[float], list[float]]:
    """Load a two-column CSV (time BKJD, flux); '#' lines are comments."""
    times: list[float] = []
    fluxes: list[float] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#"):
                continue
            if row[0].strip().lower() in ("time_bkjd", "time"):
                continue
            t, f = float(row[0]), float(row[1])
            if math.isfinite(t) and math.isfinite(f):
                times.append(t)
                fluxes.append(f)
    if len(times) < 10:
        raise DataIntegrityError(f"not enough finite rows in {path}")
    return times, fluxes


def apply_mask(
    times: list[float], fluxes: list[float], mask_events=MASK_EVENTS
) -> tuple[list[float], list[float], int]:
    """Drop rows inside known contaminating events; return (t, f, n_masked)."""
    keep_t: list[float] = []
    keep_f: list[float] = []
    for t, f in zip(times, fluxes, strict=True):
        if any(event["t_start_bkjd"] <= t <= event["t_end_bkjd"] for event in mask_events):
            continue
        keep_t.append(t)
        keep_f.append(f)
    return keep_t, keep_f, len(times) - len(keep_t)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


def detrend(times: list[float], fluxes: list[float], window_days: float = 1.5) -> list[float]:
    """Median-normalise, then divide by a running-median baseline."""
    n = len(times)
    base = _median(fluxes)
    if base == 0:
        raise DataIntegrityError("median flux is zero; cannot normalise")
    y = [f / base for f in fluxes]
    dt = _median([times[i + 1] - times[i] for i in range(n - 1)])
    w = max(5, int(round(window_days / dt)))
    if w % 2 == 0:
        w += 1
    half = w // 2
    out = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        m = _median(y[lo:hi])
        out.append(y[i] / m if m else 1.0)
    return out


def _eval_period(times: list[float], resid: list[float], period: float, ms: list[int]) -> dict:
    """Evaluate the best box (max summed residual) at one trial period."""
    n = len(times)
    order = sorted(range(n), key=lambda i: math.fmod(times[i], period))
    ys = [resid[i] for i in order]
    ph = [math.fmod(times[i], period) / period for i in order]
    mmax = max(ms)
    ext = ys + ys[:mmax]
    pre = [0.0]
    acc = 0.0
    for v in ext:
        acc += v
        pre.append(acc)
    best = None
    for m in ms:
        boxes = [pre[i + m] - pre[i] for i in range(n)]
        i0 = max(range(n), key=boxes.__getitem__)
        s = boxes[i0]
        power = s * s * n / (m * (n - m))
        if best is None or power > best[0]:
            best = (power, s, m, i0)
    power, s, m, i0 = best
    phi_start = ph[i0]
    wsum = 0.0
    csum = 0.0
    for j in range(i0, i0 + m):
        idx = j % n
        w = max(ys[idx], 0.0)
        rel = (ph[idx] - phi_start) % 1.0
        wsum += w
        csum += w * rel
    phi = (phi_start + (csum / wsum if wsum else 0.0)) % 1.0
    return {"power": power, "box_sum": s, "m": m, "q": m / n, "phase_center": phi}


def bls(
    times: list[float],
    y: list[float],
    pmin: float = 0.5,
    pmax: float = 10.0,
    nfreq: int = 1500,
    durations: tuple[float, ...] = DEFAULT_DURATIONS,
    refine: bool = True,
) -> dict:
    """Box-least-squares grid search, uniform in frequency, plus a refine pass."""
    n = len(times)
    if n < 20:
        raise ValueError("need at least 20 points for a meaningful search")
    resid = [1.0 - v for v in y]
    ms = sorted({max(2, int(round(q * n))) for q in durations})
    fmax, fmin = 1.0 / pmin, 1.0 / pmax
    fstep = (fmax - fmin) / (nfreq - 1)
    best_p, best_r = None, None
    for k in range(nfreq):
        p = 1.0 / (fmax - fstep * k)
        r = _eval_period(times, resid, p, ms)
        if best_r is None or r["power"] > best_r["power"]:
            best_p, best_r = p, r
    if refine:
        f_best = 1.0 / best_p
        p_lo = 1.0 / (f_best + 2.5 * fstep)
        p_hi = 1.0 / (f_best - 2.5 * fstep)
        for k in range(801):
            p = p_lo + (p_hi - p_lo) * k / 800
            r = _eval_period(times, resid, p, ms)
            if r["power"] > best_r["power"]:
                best_p, best_r = p, r
    return {
        "period_days": best_p,
        "power": best_r["power"],
        "q": best_r["q"],
        "phase_center": best_r["phase_center"],
        "grid": {
            "pmin": pmin,
            "pmax": pmax,
            "nfreq": nfreq,
            "durations": list(durations),
            "refined": bool(refine),
        },
    }


def _circ_dist(a: float, b: float) -> float:
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


def fold_measure(
    times: list[float], y: list[float], period: float, phase_center: float, q: float
) -> dict:
    """Measure depth, SNR, epoch, odd/even consistency and a secondary-dip check."""
    half = q / 2.0
    phases = [math.fmod(t, period) / period for t in times]
    ins: list[float] = []
    outs: list[float] = []
    for i, ph in enumerate(phases):
        d = _circ_dist(ph, phase_center)
        if d <= half:
            ins.append(y[i])
        elif d > half * 1.6:
            outs.append(y[i])
    if len(ins) < 2 or len(outs) < 10:
        raise ValueError("degenerate fold: too few in/out points")
    mean_out = sum(outs) / len(outs)
    mean_in = sum(ins) / len(ins)
    std_out = math.sqrt(sum((v - mean_out) ** 2 for v in outs) / (len(outs) - 1))
    depth = mean_out - mean_in
    snr = depth / (std_out / math.sqrt(len(ins)))
    t0 = min(times)
    # phase_center is an ABSOLUTE fold phase (fmod origin t=0): transit
    # centres are (m + phase_center) * period; pick the one nearest t0.
    m0 = round(t0 / period - phase_center)
    epoch = (m0 + phase_center) * period
    n_transits = max(1, int(round((max(times) - t0) / period)))

    def depth_for(parity: int) -> tuple[float, int]:
        sel = [
            y[i]
            for i, t in enumerate(times)
            if _circ_dist(phases[i], phase_center) <= half
            and int(round((t - epoch) / period)) % 2 == parity
        ]
        if not sel:
            return float("nan"), 0
        return mean_out - sum(sel) / len(sel), len(sel)

    d_even, n_even = depth_for(0)
    d_odd, n_odd = depth_for(1)
    denom = std_out * math.sqrt(1.0 / max(n_even, 1) + 1.0 / max(n_odd, 1))
    delta_sigma = abs(d_even - d_odd) / denom if denom else float("nan")

    center2 = (phase_center + 0.5) % 1.0
    sec = [y[i] for i, ph in enumerate(phases) if _circ_dist(ph, center2) <= half]
    d_sec = (mean_out - sum(sec) / len(sec)) if sec else float("nan")
    sec_sigma = d_sec / (std_out / math.sqrt(len(sec))) if sec else float("nan")

    return {
        "depth": depth,
        "depth_ppm": depth * 1e6,
        "snr": snr,
        "n_in": len(ins),
        "n_out": len(outs),
        "std_out_ppm": std_out * 1e6,
        "epoch_bkjd": epoch,
        "n_transits": n_transits,
        "odd_even": {
            "depth_even_ppm": d_even * 1e6,
            "depth_odd_ppm": d_odd * 1e6,
            "n_even": n_even,
            "n_odd": n_odd,
            "delta_sigma": delta_sigma,
        },
        "secondary": {
            "depth_ppm": d_sec * 1e6,
            "sigma": sec_sigma,
            "n": len(sec),
        },
    }


def harmonic_powers(
    times: list[float],
    y: list[float],
    period: float,
    durations: tuple[float, ...] = DEFAULT_DURATIONS,
) -> dict:
    """Box power at P/2, P and 2P (odd/even + secondary are the discriminators)."""
    n = len(times)
    resid = [1.0 - v for v in y]
    ms = sorted({max(2, int(round(q * n))) for q in durations})
    out = {}
    for label, mult in (("half", 0.5), ("fundamental", 1.0), ("double", 2.0)):
        r = _eval_period(times, resid, period * mult, ms)
        out[label] = {"period_days": period * mult, "power": r["power"]}
    return out

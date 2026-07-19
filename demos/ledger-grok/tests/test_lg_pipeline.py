"""Pipeline tests: synthetic transit recovery + CSV loading + detrending."""

import math
import random

from ledger_grok.pipeline import bls, detrend, fold_measure, load_csv


def _synthetic_transit(period=1.2345, q=0.06, depth=800e-6, sigma=250e-6, days=40.0, seed=7):
    rng = random.Random(seed)
    dt = 0.02042  # ~Kepler long cadence in days
    n = int(days / dt)
    times = [i * dt for i in range(n)]
    fluxes = []
    for t in times:
        phase = math.fmod(t, period) / period
        d = abs(phase - 0.3) % 1.0
        d = min(d, 1.0 - d)
        box = -depth if d <= q / 2 else 0.0
        fluxes.append(1.0 + box + rng.gauss(0.0, sigma))
    return times, fluxes, period, 0.3


def test_bls_recovers_synthetic_period_and_epoch():
    times, fluxes, period_true, phase_true = _synthetic_transit()
    result = bls(times, fluxes, pmin=0.5, pmax=5.0, nfreq=1500, refine=True)
    assert abs(result["period_days"] - period_true) < 0.002
    meas = fold_measure(times, fluxes, result["period_days"], result["phase_center"], result["q"])
    # epoch recovery (absolute-phase reconstruction) within ~1% of a period
    k = round((phase_true * period_true - meas["epoch_bkjd"]) / result["period_days"])
    delta = abs(phase_true * period_true - (meas["epoch_bkjd"] + k * result["period_days"]))
    assert delta < 0.0125 * period_true
    # depth within 30% of injected value, decent SNR
    assert 0.7 < meas["depth"] / 800e-6 < 1.3
    assert meas["snr"] > 10.0


def test_bls_no_false_positive_on_pure_noise():
    rng = random.Random(11)
    times = [i * 0.02042 for i in range(1500)]
    fluxes = [1.0 + rng.gauss(0, 250e-6) for _ in times]
    result = bls(times, fluxes, pmin=0.5, pmax=5.0, nfreq=600, refine=False)
    meas = fold_measure(times, fluxes, result["period_days"], result["phase_center"], result["q"])
    # noise-only: any "detection" must have low SNR compared to the real-signal case
    assert meas["snr"] < 12.0


def test_detrend_flattens_slope():
    times = [float(i) for i in range(400)]
    fluxes = [1000.0 * (1.0 + 0.001 * t) for t in times]  # slow linear drift
    y = detrend(times, fluxes, window_days=5.0)
    edge = sum(y[:20]) / 20
    tail = sum(y[-20:]) / 20
    assert abs(edge - tail) < 0.002


def test_load_csv_skips_comments_and_header(tmp_path):
    path = tmp_path / "lc.csv"
    rows = "\n".join(f"{i}.0,{100.0 + i}" for i in range(12))
    path.write_text(
        "# provenance line\n"
        "time_bkjd,flux_e_per_s\n"
        f"{rows}\n"
        "NaN,1.0\n"
        "inf,2.0\n"
    )
    times, fluxes = load_csv(path)
    assert len(times) == 12
    assert times[0] == 0.0 and times[-1] == 11.0
    assert fluxes[0] == 100.0 and fluxes[-1] == 111.0

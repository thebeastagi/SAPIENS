# SAPIENS LEDGER demo — Kepler-10 b re-derivation

**What this is:** a public validation demo of the
[SAPIENS](https://github.com/thebeastagi/SAPIENS) hash-chained evidence
ledger. It re-derives the **already known** exoplanet **Kepler-10 b** from a
small public Kepler light curve and records every step — data hash,
hypothesis, analysis, adversarial challenge, verdict — in a tamper-evident
JSONL chain.

**This is a re-derivation of a published result. It is not a discovery, and
nothing here claims one.** Kepler-10 b was discovered by Batalha et al. 2011;
we use the published ephemeris purely as the answer key for validation.

## Naming and endorsement

"LEDGER" is a SAPIENS demo. The hypothesis / adversarial-challenge steps sit
behind a small adapter interface whose optional live backend is Grok (xAI).
Grok and xAI are named only to identify that API; **no affiliation, sponsorship,
or endorsement by xAI is implied**. The committed demo run used the
**deterministic offline mock adapter** — every model-text block you see is a
recorded fixture, not live model output, and no API key or network was used.

## Three distinct lanes (don't mix them up)

1. **Reference data** — the real Kepler Q1 light curve (NASA/MAST) and the
   published ephemeris (NASA Exoplanet Archive). See `data/README.md`.
2. **Model text (recorded fixture)** — the `hypothesis` and
   `adversarial_challenge` ledger entries. In this run they come from
   `grok-mock`, a deterministic offline stand-in seeded by the dataset hash.
   They are labelled `"adapter": "mock"` in the ledger and visibly labelled
   as fixtures on the demo page. A live `RealGrokAdapter` exists
   (`GROK_API_KEY` from the environment, never stored), but was **not** used
   for the committed artifacts.
3. **Deterministic verification** — the pipeline (stdlib-only BLS transit
   search), the ledger hash chain, and `verify_ledger.py`. Everything here is
   reproducible byte-for-byte except timestamps.

## Quickstart (zero install, Python ≥ 3.10, stdlib only)

```bash
python demos/ledger-grok/run_demo.py        # ~25 s: pipeline + ledger + results
python demos/ledger-grok/verify_ledger.py   # verify chain + data hash
pytest demos/ledger-grok/tests              # 19 tests (also wired into repo CI)
```

`run_demo.py` regenerates `out/ledger.jsonl` + `out/results.json`
(committed artifacts are the reference run).

## Result (committed reference run)

| Quantity | This demo (Q1 only) | Published | Check |
|---|---|---|---|
| Period | 0.8373346 d | 0.8374912 d | Δ = 1.6×10⁻⁴ d (≤ 5×10⁻⁴) ✓ |
| Mid-transit | BKJD 131.579626 | BKJD 131.574858 + k·P | Δ = 7.0 min (≤ 30) ✓ |
| Depth | 158.3 ppm | 191 ppm | ratio 0.83 (0.4–2.5) ✓ |
| Transits / SNR | 40 / 34.0 | — | — |
| Odd/even depth | 156.2 / 160.2 ppm (0.42σ) | expect ≈ equal | ✓ |
| Secondary dip | 2.3 ppm (0.49σ) | expect ≈ 0 | ✓ |

Verdict: **MATCH — validation (re-derivation), not a discovery.**
Honest caveat: with a single 33.5-day quarter the periodogram has several
near-equal peaks; the measured period is the global BLS maximum and sits
0.019 % off the 17-quarter published value, inside the demo's stated
tolerance. The demo proves the *pipeline + ledger* end to end, not new
astronomy. One Kepler-10 c transit in the segment is masked and disclosed
(see `data/README.md`).

## Ledger format

One JSON object per line, canonical JSON (sorted keys, no NaN):

```
{"seq", "ts", "actor", "kind", "payload", "previous_hash", "entry_hash"}
entry_hash = sha256(canonical({seq, ts, actor, kind, payload, previous_hash}))
```

`previous_hash` of entry 1 is 64 zeros (genesis). `verify_ledger.py`
recomputes every link, catches any modified/reordered/removed entry, and can
also check that the CSV still matches the sha256 in `data_ingested`
(`--data`). Kinds: `data_ingested`, `hypothesis`, `analysis`,
`adversarial_challenge`, `challenge_response`, `verdict`.

## Grok adapter

```python
from ledger_grok.grok_adapter import get_adapter
adapter = get_adapter("mock", data_sha256)   # default: offline, deterministic
adapter = get_adapter("real", data_sha256)   # needs GROK_API_KEY in env
```

- `MockGrokAdapter` — fixed templates seeded by the dataset hash; zero
  credentials, zero network; used for the committed run and in tests.
- `RealGrokAdapter` — calls the xAI chat-completions API (`GROK_API_KEY` or
  `XAI_API_KEY` from the environment, never stored; `GROK_MODEL` override,
  default `grok-4.20-0309-non-reasoning`, temperature 0).

**Bounded live proof (2026-07-19):** exactly one minimal live call was made
with `tools/grok_live_probe.py` — HTTP 200, 274 tokens total, key read from
the environment only. Model, status, usage, and the sanitized one-sentence
reply are recorded in `out/grok-live-probe.json`. The committed ledger and
all tests remain on the deterministic offline mock; the probe is a separate
one-call proof, not part of the reproducible run.

## Layout

```
data/     committed CSV + provenance
src/ledger_grok/  fits.py pipeline.py ledger.py verify.py grok_adapter.py run.py
tools/    fetch_data.py (one-off networked fetch; everything else is offline)
out/      committed reference run: ledger.jsonl + results.json
site/     static demo page (GitHub Pages)
tests/    19 tests incl. artifact-anchoring (committed ledger must verify)
SHA256SUMS  integrity manifest for data + artifacts
```

## Credit

Developed by The Beast AGI engineering fleet in collaboration with the ASTRA
research program (Prof. Glenn White) — **attribution only; no ASTRA code is
used in this demo**. Kepler data: NASA/MAST. Ephemeris: NASA Exoplanet
Archive. License: Apache-2.0 (see repo root).

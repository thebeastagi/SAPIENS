# Data provenance — Kepler-10 (KIC 11904151) Quarter 1 light curve

`kepler10_kic11904151_q1_lc.csv` (32 KB, 1,432 rows) is a small excerpt of
public NASA Kepler data, used as the *reference dataset* for this demo.

| Field | Value |
|---|---|
| Target | Kepler-10 (KIC 11904151), Kepler magnitude 10.96 |
| Product | Kepler long-cadence light curve (PDCSAP_FLUX), FITS header `QUARTER = 1` |
| Source URI | `mast:Kepler/url/missions/kepler/lightcurves/0119/011904151/kplr011904151-2009166043257_llc.fits` |
| Source URL | <https://mast.stsci.edu/api/v0.1/Download/file?uri=mast:Kepler/url/missions/kepler/lightcurves/0119/011904151/kplr011904151-2009166043257_llc.fits> |
| Retrieved (UTC) | 2026-07-19 (see `# retrieved_utc` comment in the CSV) |
| FITS sha256 | `a47542bd31fa92111f280a29885f6fbe860f0956012b442f780ca6d2cc3a19c6` (192,960 bytes) |
| CSV sha256 | `1d82ef8ced447bb44ac80c7389a8ef3dde93bf1983d619d56fe2f6cda3a56ded` |
| Columns | `time_bkjd` (BJD − 2454833), `flux_e_per_s` (PDCSAP, e-/s) |
| Filtering | rows with `SAP_QUALITY != 0` dropped (207 of 1,639); non-finite dropped |
| Span | BKJD 131.512 – 164.983 (~33.5 days) |

Notes:

- The MAST filename timestamp is *not* the quarter label; the FITS header
  (`QUARTER = 1`) and the time span are authoritative. The neighbouring URI
  (`...-2009131105131_llc.fits`) is the ~9.7-day Q0 commissioning segment.
- The segment contains one **Kepler-10 c** transit (BKJD ~138.58–138.81,
  ~450 ppm, ~5.5 h). Kepler-10 c has a 45.3-day period, outside this demo's
  0.5–10 d search window, so the event is masked during the run and disclosed
  in the ledger `data_ingested` payload (`masked_events`).
- Kepler data are public (NASA/MAST). No proprietary data is used.
- Regenerate with: `python tools/fetch_data.py --out data/kepler10_kic11904151_q1_lc.csv`
  (network used only here; the demo itself runs fully offline on this CSV).

Published reference values for the verdict comparison (see `src/ledger_grok/run.py`):
NASA Exoplanet Archive Planetary Systems (`ps`) table via TAP, retrieved
2026-07-19 — period 0.8374912 d, mid-transit 2454964.574756 BJD, depth
191 ppm, duration 1.8076 h; corroborated by the KOI table (K00072.01:
period 0.837491225 d, `koi_time0bk` 131.574858 BKJD, depth 190.4 ppm).

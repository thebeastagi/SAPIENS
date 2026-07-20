# Adapter data provenance — Kepler-10 (KIC 11904151) Quarter 1 light curve

`kepler10_kic11904151_q1_lc.csv` (32 KB, 1,432 rows) is a small excerpt of
**public NASA Kepler data**, bundled so the Phase-4 adapter can re-derive an
already-published signal offline.

| Field | Value |
|---|---|
| Target | Kepler-10 (KIC 11904151), Kepler magnitude 10.96 |
| Quarter | Q1 (33.5 days; 2009-05-13 → 2009-06-15) |
| Product | PDCSAP flux (pre-search data conditioning simple aperture photometry) |
| Source | NASA/MAST public archive — https://mast.stsci.edu |
| Retrieved | 2026-07-19 via the MAST Kepler archive (public, no authentication) |
| File | `kplr011904151-2009166043257_llc.fits` → two-column CSV (time BKJD, PDCSAP flux) |
| Licence | NASA Kepler data are public-domain works of the US federal government |
| SHA-256 | `1d82ef8ced447bb44ac80c7389a8ef3dde93bf1983d619d56fe2f6cda3a56ded` (pinned; verified at load) |

This is the same reference dataset used by `demos/ledger-grok` (identical
bytes, same checksum). **Data is not code**: this file carries no program
logic, and no ASTRA-family material of any kind is included.

One known Kepler-10 C transit inside this segment (BKJD 138.54–138.86,
~450 ppm) is masked at load time and disclosed in adapter evidence details,
exactly as in the demo — it belongs to a different, also already-known
planet and would otherwise tilt the period search.

The bundled curve is used strictly to **re-derive the published Kepler-10 b
signal as a validation of the pipeline**. It is not used to claim any
discovery.

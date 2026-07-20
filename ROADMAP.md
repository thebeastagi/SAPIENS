# Roadmap

## Phase 0 — shipped in this PR

- Standalone SAPIENS repository.
- Clean-room core package and docs.
- Synthetic integrated orchestration.
- Tests and Python matrix CI.

## Phase 1 — shipped (package version 0.2.0)

Legal/licence gate and adapter hardening:

- ~~Obtain explicit licences/permissions for any ASTRA-family code reuse
  before extraction.~~ Mechanism shipped: `permissions.json` +
  `sapiens.permissions` record owner grants; the manifest is **empty** — no
  ASTRA-family (or any third-party) permissions exist, so every third-party
  adapter is refused until an owner records one.
- ~~Replace synthetic-only adapter gate with a trust-tiered adapter
  registry.~~ Shipped: `sapiens.registry` (SYNTHETIC / CORE / UNTRUSTED).
- ~~Add subprocess isolation and OS-level resource limits for untrusted
  adapters.~~ Shipped: `sapiens.isolation` — rlimit CPU / address-space /
  open-files plus wall-clock timeout, fail-closed; the kernel runs
  UNTRUSTED-tier adapters only through it.
- ~~Add signed ledger checkpoints or external anchoring.~~ Shipped:
  `sapiens.checkpoints` — HMAC-SHA256 checkpoint events (key from
  environment only) plus external anchor export/verify.

Honest limits: rlimits bound resource use but are not a security sandbox;
HMAC proves local key possession, not third-party authorship. No real-data
adapter ships in Phase 1.

## Phase 2 — shipped (package version 0.3.0)

Validation framework v1:

- ~~Expand L0→L2 automated gates~~ Shipped: `sapiens.validation` — L1
  internal-consistency gate (score presence/range, determinism across reruns,
  degenerate constant-score rejection) and L2 holdout-replication gate
  (declared `HoldoutProtocol` per domain; explicit leakage controls on
  dataset collision and (dataset, seed) reuse; pass-fraction threshold).
  Opt-in kernel wiring via `DiscoveryKernel(validation=...)`; gate verdicts
  are logged, never fabricated as evidence; a configured domain without a
  declared protocol fails closed.
- ~~Add seeded-bias fixtures and calibration reports.~~ Shipped:
  `sapiens.fixtures` (known-good / overfit / leakage / degenerate, labelled
  with expected outcomes) and `sapiens.calibration` (`CalibrationReport`:
  catch rate, false-reject rate, sample counts; report ids are content
  hashes).
- ~~Add confidence aggregation only after calibration data exists~~ Shipped:
  `sapiens.confidence.aggregate_confidence` raises `UncalibratedError`
  without a sufficiently sampled calibration report; with one, it emits a
  documented heuristic (raw pass fraction × demonstrated catch rate) with
  full provenance. No invented precision.

## Phase 3 — structured L3 review panels

- Role-specialized reviewer schemas: statistician, domain theorist, methodologist, devil's advocate.
- Multi-round reports, objection tracking, disagreement gates.
- Catch-rate scoring on seeded known-bad and known-good candidates.

## Phase 4 — real domain adapters

- First: one clean-room Kepler photometry adapter on public NASA/MAST data
  (reuses this repository's own Apache-2.0 demo pipeline path).
- ASTRA/GEODISC/BIODISC/SLATE adapters only after licence and owner review.
- Domain-specific validators remain sandboxed behind adapters.
- Cross-domain method transfer enters target domain at L0 every time.

## Phase 5 — external-review workflows

- Human L4 gates.
- Reproduction bundles.
- Prediction tracking and demotion on contradicting evidence.

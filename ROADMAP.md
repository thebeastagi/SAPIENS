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

## Phase 3 — shipped (package version 0.4.0)

Structured L3 review panels:

- ~~Role-specialized reviewer schemas~~ Shipped: `sapiens.review` —
  statistician, domain theorist, methodologist, devil's advocate; typed
  approve/object/abstain verdicts with severity-graded objections.
- ~~Multi-round reports, objection tracking, disagreement gates~~ Shipped:
  bounded deterministic multi-round protocol; objection lifecycle
  (raised/sustained/withdrawn) tracked in every `PanelReport`; sustained
  MAJOR/BLOCKING objections reject, MINOR caveats are recorded but
  non-fatal (documented gate semantics). Deterministic reference reviewers
  in `sapiens.reviewers` re-run the Phase-2 gates independently and hunt
  seeded-bias signatures.
- ~~Catch-rate scoring~~ Shipped: `sapiens.catchrate.score_panel` over the
  seeded fixture suite — per-role and panel-level catch rates plus
  false-reject rate, with an explicit small-sample caveat.
- Kernel integration: with a panel configured, L3 promotion requires panel
  approval, and the verdict is recorded in the ledger as review evidence
  (no side channel). Without a panel, Phase-2 behaviour is unchanged.

## Phase 4 — shipped (package version 0.5.0)

Real domain adapters:

- ~~First: one clean-room Kepler photometry adapter~~ Shipped:
  `sapiens.adapters.kepler.KeplerPhotometryAdapter` (CORE trust tier)
  re-derives the **published** Kepler-10 b signal from a bundled public
  NASA/MAST Q1 light curve (checksum-pinned, provenance in
  `src/sapiens/adapters/data/README.md`). Framed everywhere as validation
  of a published result, never a discovery. The pipeline is this
  repository's own Apache-2.0 demo code path (`adapters/_transit.py`);
  **zero ASTRA-family code** (the permission manifest remains empty).
- ASTRA/GEODISC/BIODISC/SLATE adapters only after licence and owner review.
  (Unchanged; still gated.)
- ~~Domain-specific validators remain sandboxed behind adapters~~ Shipped:
  BLS search, detrending, fold measurement and adversarial checks live
  inside the adapter; the kernel sees only contract evidence.
- ~~Cross-domain method transfer enters target domain at L0 every time~~
  Re-verified against the real adapter (bridge test).
- Negative controls: flat curves propose nothing; tampered curves refuse to
  load (pinned checksum); shifted-period curves fail replication with the
  disagreement shown in evidence details.

## Phase 5 — external-review workflows

- Human L4 gates.
- Reproduction bundles.
- Prediction tracking and demotion on contradicting evidence.

---

# Discovery-Gate Hardening (scout HOW-TO-PROCEED Phases 0–5) — shipped v0.6.0

> **Distinct track, distinct numbering.** The *foundation* phases above (0–4)
> built the ledger/adapter/review plumbing. This second track hardens the
> **discovery-decision gates** against gaming and null-model incompleteness,
> following `beast-scout`'s blind red-team benchmark. It ships as the
> self-contained, stdlib-only `sapiens.gates` subpackage and changes **no**
> foundation behaviour. Honesty invariant unchanged:
> `scientific_discoveries_claimed = 0`.

Status legend: **code-complete** (implemented + tested) · **library-complete**
(decision-support code done; the surrounding human workflow is process, not
code) · **synthetic-corpus** (validated on spec-derived synthetic profiles, not
real datasets — the real measurement is a prospective trial).

### DG-0 — weld the 4 gaming seams — **code-complete**
- **G-03** anomaly boost is conditioned on *literature-measured surprise*
  (`gates.surprise`), never mere absence of a mechanism.
- **G-05** reserved paradigm-breaker slots require `promotion_score >= 0.30`
  **and** the G-03 surprise condition (`gates.promotion.reserved_slot_eligible`).
- **G-06** L2-holdout-passed is a *prerequisite* for CALIBRATED; the additive
  score only ranks *within* the calibrated set (`gates.promotion`,
  `gates.pipeline` entry gate).
- **G-07** MAD/σ baseline is computed on the **full dataset** with a robust
  estimator that consumes every point (`gates.surprise.robust_baseline`).
- **FP-06** conservation-law guard: a violation ⇒ correct null is measurement
  error ⇒ no boost/entry without reproducible orthogonal confirmation.
- **Exit met:** the 7 gaming vectors re-run to **0 leaks** (`gates.criteria.run_gaming_retest`; test `test_phase0_exit_zero_gaming_leaks`).

### DG-1 — mandatory, logged null layer — **code-complete**
- Every candidate carries a `NullProvenance` record (which null, external data
  required/fetched y/n, σ-under-null); no null ⇒ **UNCALIBRATED**, never a
  silent pass (`gates.nulls`).
- **Family-wide** BH-FDR across the candidate family (`gates.fdr`) — the
  multiplicity/look-elsewhere control (FP-09/FP-10).
- **FP-04** "instrument-systematic-not-excluded" is an explicit state that
  surfaces to the human instead of passing as a clean 6σ.

### DG-2 — decoupled threshold architecture — **code-complete**
- **ENTRY** = 3σ-equiv AND survives family BH-FDR q<0.05; **RANK** = continuous
  σ/effect; **CONFIRM** = 5σ (physics) / FDR<0.05 + orthogonal replication (bio)
  / formal proof-check (math) (`gates.thresholds`, `gates.pipeline`).
- Boundary fixes: **B-02** adaptive `ci_floor`, **B-03** hash-committed
  thresholds, **B-05** continuous degree-of-calibration, **B-06** DevilsAdvocate
  r≥0.90 → permutation test at ~3σ-equiv (`gates.devils_advocate`).

### DG-3 — genuine blind re-run harness — **code-complete (synthetic-corpus)**
- Strip `ground_truth`/`expected_verdict`/`gates_probed`/`how_*`; expand with
  ~20 historical positives + fresh decoys; separate-custody key with a
  published SHA-256 commitment; blind scoring runner + grade
  (`gates.blind`, `gates.corpus`).
- *Honest scope:* the positives/decoys are **spec-derived synthetic profiles**,
  and separate custody is implemented in-process. A real sealed set on real
  post-cutoff data with a genuine second-party custody ceremony is the
  next-stage (external) test this unblocks.

### DG-4 — human-in-loop final gate — **library-complete**
- Per-candidate dossier (σ, FDR-q, null used, external-data y/n, replication
  status, UNCALIBRATED/instrument flags, and the single strongest
  **disconfirming** explanation next to the claim); tiered authority
  (only CONFIRM-tier is autonomous-claim-eligible, human co-sign still required);
  bounded top-K throttle; override log feeding recalibration (`gates.dossier`,
  `gates.pipeline` shortlist).
- *Honest scope:* this is the decision-support **data + eligibility layer**; the
  reviewer UI/workflow itself is out of repo scope.

### DG-5 — success-criteria suite — **code-complete (synthetic-corpus)**
- Automated `gates.criteria.run_success_criteria` checks all five ship gates:
  0 gaming leaks · null layer mandatory+logged (100% of shortlisted) · blind
  kill-rate ≥ 8/10 + recovery ≥ 8/10 + abstention < 10% · boundary stability
  ≤ 1 flip/item over 3 seeds · thresholds hash-committed per run. All pass on
  the synthetic corpus (`test_success_criteria_all_pass`).
- *Honest scope:* retrospective/synthetic gates are an intuition pump. The
  **only** real validation is a prospective, pre-registered precision@K /
  false-positive-rate trial on a post-cutoff stream — stated in the suite output
  and not faked here.

CLI: `sapiens gates` (full suite) · `sapiens gates --mode gaming` (Phase-0 re-test).

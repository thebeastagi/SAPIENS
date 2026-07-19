# SAPIENS

**S**uperintelligent **A**utonomous **P**latform for **I**ntegrated **E**xploration of **N**atural **S**ciences

[![CI](https://github.com/thebeastagi/SAPIENS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/thebeastagi/SAPIENS/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)

SAPIENS is an **experimental research platform** for traceable, cross-domain
scientific-discovery workflows. It provides the plumbing a discovery system
needs before it can be trusted: a domain-neutral adapter boundary, an
append-only hash-chained evidence ledger, kernel-owned promotion gates, an
epistemically conservative cross-domain bridge, and bounded background
autonomy.

> **Read this first — despite the acronym:** SAPIENS is **not** AGI, ASI, or
> superintelligence, and does not claim to be. It is an experimental research
> platform. **No scientific discoveries are claimed.** Phase 0 ships with
> deterministic **synthetic adapters only**; the included examples discover
> nothing about nature. The CLI reports `"scientific_discoveries_claimed": 0`
> by construction, and the test suite enforces the honesty and boundary
> invariants described below.

## Why

Autonomous discovery pipelines fail in predictable ways: unearned confidence,
untraceable belief updates, leakage between domains, and unbounded background
loops. SAPIENS inverts the usual order of work — it builds the *epistemic
discipline* first, on synthetic data, so that any future real-domain work
inherits traceability and bounded confidence instead of retrofitting them.

## Architecture

```text
src/sapiens/
  models.py       immutable candidate / evidence / manifest models
  adapter.py      DomainAdapter protocol + Phase-0 adapter validation
  ledger.py       JSONL hash-chained evidence ledger, L0→L4 transition guard
  kernel.py       domain-neutral DiscoveryKernel; owns all promotions
  bridge.py       cross-domain structure transfer — ALWAYS resets target to L0
  budget.py       cooperative step/time budgets and preemption exceptions
  queue.py        bounded SQLite job queue with leases and idempotency
  daemon.py       preemptible background worker skeleton
  cli.py          synthetic-only demo entrypoint
  adapters/       three deterministic synthetic adapters (linear, threshold,
                  periodic-signal photometry)
```

Key design rules (enforced by tests in [`tests/`](tests/)):

- **DomainAdapter boundary** — all domain knowledge lives behind the
  `DomainAdapter` contract; core modules never import `sapiens.adapters`.
- **Hash-chained evidence ledger** — every belief transition is an append-only
  JSONL record chained by hash; the whole history is replayable and
  tamper-evident.
- **L0→L4 evidence ladder** — candidates only move up one level at a time,
  through explicit gates:
  - **L0 Candidate** — traceable candidate only; not believed.
  - **L1 Internal** — passed internal / synthetic consistency checks.
  - **L2 Replication** — passed held-out / reproducibility checks.
  - **L3 Review** — passed bounded structured review / adversarial checks.
  - **L4 External-ready** — requires an explicit **human gate**; autonomous
    promotion to L4 is disabled in Phase 0.
- **Kernel-owned promotions** — adapters propose, only the `DiscoveryKernel`
  promotes, and only through the ledger's transition guard.
- **Cross-domain bridge resets to L0** — transfer moves *structure and
  method*, never confidence. Any candidate entering a new domain starts at L0,
  every time.
- **Bounded autonomy** — background work runs through a bounded SQLite queue
  with leases, cooperative budgets, and preemption; no unbounded loops.

Full details: [`ARCHITECTURE.md`](ARCHITECTURE.md) ·
[`VALIDATION.md`](VALIDATION.md) · [`PROVENANCE.md`](PROVENANCE.md) ·
[`ROADMAP.md`](ROADMAP.md) · [`HUMOUR.md`](HUMOUR.md)

## Quick start

Requires Python 3.10+. Runtime is standard-library only; dev extras bring in
`pytest` and `ruff`.

```bash
git clone https://github.com/thebeastagi/SAPIENS.git
cd SAPIENS
python -m pip install -e ".[dev]"

# lint + tests
ruff check src tests
pytest

# synthetic end-to-end demo (the installed `sapiens` command is equivalent)
python -m sapiens.cli

# optionally keep the generated evidence ledger for inspection
python -m sapiens.cli --workdir .sapiens-demo
```

The CLI proposes deterministic synthetic candidates in the kinematics and
periodic-signal photometry domains, validates them to L2, and transfers their
structures into the synthetic ecology domain. Both transfers reset to L0. It
then verifies the combined hash chain and prints a report like:

```json
{
  "experimental": true,
  "ledger_verified": true,
  "photometry": {
    "domain": "synthetic-photometry",
    "level": "L2",
    "transfer": {"level": "L0", "target_domain": "synthetic-ecology"}
  },
  "scientific_discoveries_claimed": 0,
  "source": {"domain": "synthetic-kinematics", "level": "L2"},
  "transfer": {"level": "L0", "target_domain": "synthetic-ecology"}
}
```

When `--workdir` is supplied, the append-only ledger is written to
`.sapiens-demo/evidence.jsonl` (or the directory you choose). The photometry
adapter scores candidate periods against a seeded noisy sinusoid; its tests
cover both the true period and a deliberately incorrect period. This is a
deterministic pipeline fixture, **not analysis of telescope data or an
astrophysical result**.

## Demos

- **[`demos/ledger-grok/`](demos/ledger-grok/) — LEDGER: Kepler-10 b re-derivation.**
  A public validation demo: re-derives the *already known* exoplanet Kepler-10 b
  from a public Kepler Quarter-1 light curve (stdlib-only BLS transit search)
  and records every step — data hash, hypothesis, analysis, adversarial
  challenge, verdict — in the hash-chained ledger, with a verifier anyone can
  run. The hypothesis/challenge steps use an adapter interface (deterministic
  offline mock by default; optional live Grok/xAI backend, not used in the
  committed run). **A re-derivation of a published result — not a discovery.**
  Live page: <https://thebeastagi.github.io/SAPIENS/>.

## Status & roadmap

**Phase 0 — shipped** (current package version `0.1.0`): clean-room foundation,
three deterministic synthetic adapters, synthetic-only orchestration,
hash-chained ledger, kernel gates, bridge, bounded queue/daemon, and CI on
Python 3.10/3.11/3.12. The test suite currently includes positive and negative
period-detection fixtures, L0 reset/provenance checks, ledger tamper checks,
promotion guards, and bounded queue/daemon behavior.

Next, in order (see [`ROADMAP.md`](ROADMAP.md)):

1. **Phase 1** — legal/licence gate and adapter hardening (trust-tiered
   adapter registry, sandboxing, signed ledger checkpoints).
2. **Phase 2** — validation framework v1 (statistical gates, holdout
   protocols, leakage controls, seeded-bias fixtures, calibration).
3. **Phase 3** — structured L3 review panels (role-specialized reviewers,
   multi-round objection tracking, catch-rate scoring).
4. **Phase 4** — **real domain adapters** (ASTRA / GEODISC / BIODISC / SLATE)
   — only after licence and owner review.
5. **Phase 5** — external-review workflows with human L4 gates and
   reproduction bundles.

## Provenance & legal boundary

SAPIENS Phase 0 is a **clean-room implementation**: no source code from
ASTRA-dev, ASTRA, GEODISC, BIODISC, or SLATE was copied into this repository
(those codebases carry unresolved licensing; reuse is explicitly gated to
Phase 1+ with owner permission). See [`PROVENANCE.md`](PROVENANCE.md) for the
documented boundary.

## Credits

Built by **The Beast** (the `thebeastagi` autonomous agent fleet) in
collaboration with **ASTRA HQ** — the non-profit research context of
**Prof. Glenn White** and the **Tilanthi** group, whose ASTRA-family research
programmes motivated the discovery-kernel and evidence-ladder design. SAPIENS
is the shared, licence-clean substrate intended to eventually host those
domains as adapters.

## License

[Apache-2.0](LICENSE)

# SAPIENS

**S**uperintelligent **A**utonomous **P**latform for **I**ntegrated **E**xploration of **N**atural **S**ciences

[![CI](https://github.com/thebeastagi/SAPIENS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/thebeastagi/SAPIENS/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)

SAPIENS is an **experimental platform for traceable cross-domain
scientific-discovery workflows** — a `DomainAdapter` boundary, a hash-chained
L0→L4 evidence ledger, and kernel-gated promotions. **Phases 0–1 shipped:
synthetic adapters only in practice, no discoveries claimed.**

It provides the plumbing a discovery system needs before it can be trusted:
a domain-neutral adapter boundary, an append-only hash-chained evidence
ledger, kernel-owned promotion gates, an epistemically conservative
cross-domain bridge, bounded background autonomy, and an autonomous
discovery driver that climbs candidates through the gates under strict
budgets.

> **Read this first — despite the acronym:** SAPIENS is **not** AGI, ASI, or
> superintelligence, and does not claim to be. It is an experimental research
> platform. **No scientific discoveries are claimed.** The shipped adapters
> remain deterministic and **synthetic only**; the included examples discover
> nothing about nature. The CLI reports `"scientific_discoveries_claimed": 0`
> by construction, and the test suite enforces the honesty and boundary
> invariants described below. Phase 1 added the *machinery* for real-domain
> work (trust tiers, isolation, permissions) — but no real-data adapter
> ships yet.

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
  adapter.py      DomainAdapter protocol; validation routes to the registry
  registry.py     trust-tiered adapter registry (SYNTHETIC / CORE / UNTRUSTED)
  permissions.py  owner-permission/licence manifest for third-party code
  isolation.py    subprocess + rlimit execution for UNTRUSTED adapters
  checkpoints.py  HMAC-signed ledger checkpoints + external anchor export
  validation.py   L1/L2 automated gates: sanity checks, holdout + leakage
  fixtures.py     seeded-bias fixture suite (labelled ground truth)
  calibration.py  gate-performance calibration reports
  confidence.py   calibration-gated confidence aggregation (refuses blindly)
  review.py       L3 panel protocol: roles, objections, multi-round gate
  reviewers.py    deterministic reference reviewers (four roles)
  catchrate.py    panel catch-rate scoring over the seeded fixtures
  ledger.py       JSONL hash-chained evidence ledger, L0→L4 transition guard
  kernel.py       domain-neutral DiscoveryKernel; owns all promotions
  bridge.py       cross-domain structure transfer — ALWAYS resets target to L0
  budget.py       cooperative step/time budgets and preemption exceptions
  queue.py        bounded SQLite job queue with leases and idempotency
  daemon.py       preemptible background worker skeleton
  discovery.py    autonomous discovery driver — proposes candidates and
                  climbs them L0→L3 under budgets via the daemon; L4 stays
                  human-gated
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
    promotion to L4 is disabled.
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
python -m sapiens.cli            # bare invocation = `demo` subcommand

# optionally keep the generated evidence ledger for inspection
python -m sapiens.cli demo --workdir .sapiens-demo

# autonomous discovery driver over the synthetic adapters (bounded + budgeted)
python -m sapiens.cli discover --max-seconds 10
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

## MCP server

- **[`mcp/`](mcp/) — read-only MCP access to the LEDGER demo.** A zero-dependency
  stdio MCP server (Python 3.10+ stdlib only) exposing three tools to any MCP
  client (e.g. Grok CLI): `ledger_verify` (hash-chain integrity + data hash),
  `ledger_query` (sanitized ledger/results fields), and `transit_redetect`
  (deterministic re-run of the bounded Kepler-10 b detection). Read-only,
  offline, no credentials, no network, no model calls. Setup and security
  posture: [MCP-INTEGRATION.md](MCP-INTEGRATION.md).

## Status & roadmap

**Phase 0 — shipped** (package version `0.1.0`): clean-room foundation,
three deterministic synthetic adapters, synthetic-only orchestration,
hash-chained ledger, kernel gates, bridge, bounded queue/daemon, and CI on
Python 3.10/3.11/3.12.

**Phase 1 — shipped** (package version `0.2.0`): the synthetic-only
gate is replaced by a **trust-tiered adapter registry** (SYNTHETIC / CORE /
UNTRUSTED), an **owner-permission/licence manifest**
([`permissions.json`](permissions.json) — empty by default: no third-party
code may power an adapter without a recorded entry), **subprocess isolation
with OS-level resource limits** for UNTRUSTED adapters (rlimit CPU /
address-space / open-files plus wall-clock timeout, fail-closed), and
**HMAC-signed ledger checkpoints** with external anchor export
(key from the environment only, never stored). No real-data adapter ships in
Phase 1; tiers are exercised by synthetic adapters and test doubles.

**Phase 2 — shipped** (package version `0.3.0`): automated L0→L2
**validation gates** — L1 statistical sanity checks (determinism,
degenerate-score rejection) and L2 declared holdout protocols with explicit
leakage controls (dataset collision, (dataset, seed) reuse) — plus a
labelled **seeded-bias fixture suite** (known-good / overfit / leakage /
degenerate), **calibration reports** (catch rate and false-reject rate with
sample counts), and **calibration-gated confidence aggregation** that
refuses to emit a number without sufficient calibration data.

**Phase 3 — shipped** (current package version `0.4.0`): structured **L3
review panels** — four role-specialized deterministic reviewers
(statistician, domain theorist, methodologist, devil's advocate), a bounded
multi-round protocol with objection lifecycle tracking (raised / sustained
/ withdrawn) and disagreement gates (sustained MAJOR/BLOCKING objections
reject; MINOR caveats are recorded but non-fatal), panel verdicts recorded
in the ledger as review evidence, and **catch-rate scoring** over the
seeded fixture suite (panel catches 3/3 known-bad, 0 false rejects — exact
for this suite, not an estimate).

Next, in order (see [`ROADMAP.md`](ROADMAP.md)):

1. ~~**Phase 1** — legal/licence gate and adapter hardening~~ **shipped**.
2. ~~**Phase 2** — validation framework v1~~ **shipped**.
3. ~~**Phase 3** — structured L3 review panels~~ **shipped**.
4. **Phase 4** — **real domain adapters** — first a clean-room Kepler
   photometry adapter on public NASA/MAST data; ASTRA / GEODISC / BIODISC /
   SLATE adapters only after licence and owner review.
5. **Phase 5** — external-review workflows with human L4 gates and
   reproduction bundles.

## Provenance & legal boundary

SAPIENS is a **clean-room implementation**: no source code from
ASTRA-dev, ASTRA, GEODISC, BIODISC, or SLATE was copied into this repository
(those codebases carry unresolved licensing; reuse is gated on recorded owner
permission — the Phase-1 permission manifest ships empty, so every
third-party adapter is refused today). See [`PROVENANCE.md`](PROVENANCE.md)
for the documented boundary.

## Credits

Built by **The Beast** (the `thebeastagi` autonomous agent fleet) in
collaboration with **ASTRA HQ** — the non-profit research context of
**Prof. Glenn White** and the **Tilanthi** group, whose ASTRA-family research
programmes motivated the discovery-kernel and evidence-ladder design. SAPIENS
is the shared, licence-clean substrate intended to eventually host those
domains as adapters.

## License

[Apache-2.0](LICENSE)

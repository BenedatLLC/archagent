# Calibration round 3 (2026-08-23) — wardrowbe, and what two signals actually measure

Six findings from `wardrowbe` at `wardrowbe-v1.7.0`, labelled blind to severity, confidence and
recommendation. Three `unstable-interface`, three `layer-inversion`. Run to break the round-2 tie on
`unstable-interface`, where both confirmations were archagent and both dismissals were fastapi-template.

## Standing totals

| signal | n | confirm | partial | dismiss | strict | 95% CI |
|---|---|---|---|---|---|---|
| `scattered-source-of-truth` | 9 | 8 | 0 | 1 | 89% | [0.56, 0.98] |
| `enum-value-escape` | 10 | 6 | 3 | 1 | 60% | [0.31, 0.83] |
| `layer-inversion` | 7 | 3 | 0 | 4 | 43% | [0.16, 0.75] |
| `unstable-interface` | 7 | 2 | 0 | 5 | **29%** | [0.08, 0.64] |
| `layer-skip` | 3 | 0 | 0 | 3 | 0% | [0.00, 0.56] |
| `cycle-subsystem` | 2 | 2 | 0 | 0 | 100% | [0.34, 1.00] |
| `god-component` | 1 | 0 | 1 | 0 | 0% | [0.00, 0.79] |

Round 3 alone: `unstable-interface` 0 of 3, `layer-inversion` 1 of 3.

## `layer-inversion` — the split is total, and it is not about layering

Across three repositories, every label falls on one side of a single attribute:

| verdict | subsystem | repository | what it is |
|---|---|---|---|
| confirm | `extraction` | archagent | production |
| confirm | `backend-core` | fastapi-template | production |
| confirm | `backend-platform` | wardrowbe | production |
| dismiss | `backend-ops` | fastapi-template | migrations / startup |
| dismiss | `backend-tests` | fastapi-template | tests |
| dismiss | `backend-migrations` | wardrowbe | migrations |
| dismiss | `backend-tests` | wardrowbe | tests |

**Four of four dismissals are test or migration packages. Three of three confirmations are production
code.** No exceptions in either direction.

The mechanism is visible in the artifacts: both repositories tier their test package as `infra`, the
*bottom* rank. Everything a test imports is therefore "upward", so a test subsystem generates an
inversion against every production subsystem it exercises — four of them in wardrowbe. The reviewer put
it plainly: *"tests are supposed to exercise API, domain, services, and worker code, so these dependency
edges are not a layer-inversion problem."* Migrations are the same shape: *"`migrations/env.py` imports
models to register Alembic metadata, an expected migration dependency."*

**This is now independent evidence.** Round 2's `backend-tests` dismissal restated a sentence the
worksheet guidance itself supplied, so it was discounted. That sentence was removed before round 3, and a
reviewer reached the same conclusion unprompted, in a different repository, about a different test
package. The round-2 label can now be read at face value.

## `unstable-interface` — the pre-registered question is *not* resolved

Design §22.10 was written before these results and says a dismissed outcome "may **not** be written up as
having resolved the question". It came back dismissed 0 of 3, so that holds:

| verdict | subsystem | repository |
|---|---|---|
| confirm | `drift`, `extraction` | archagent |
| dismiss | `backend-core`, `backend-domain` | fastapi-template |
| dismiss | `backend-domain`, `backend-platform`, `backend-services` | wardrowbe |

Both confirmations are still archagent and every dismissal is still a web backend. wardrowbe was chosen
knowing it is architecturally the same shape as fastapi-template, and it behaved like it. **"The signal is
weak" and "web backends with shared modules co-change for ordinary reasons" both predict this, and these
three repositories cannot separate them.** The aggregate result is 5 dismissals, not an answer.

### But the reasons carry something the aggregate does not

*A deviation from the pre-registration, recorded as one:* §22.10 anticipated only the verdict counts. The
five dismissals turn out to give one mechanism, stated three different ways in round 3 alone:

> "models and schemas are the intentionally shared data contract; changes to that contract appropriately
> require API, migration, service, worker, and test updates."
> "this subsystem **deliberately** supplies shared configuration, database access, and utilities."
> "the service layer is **intentionally** shared directly by the API and worker."

And fastapi-template's two said the same thing: *"backend-core is intentionally shared configuration,
database, and security infrastructure."*

**A module that is deliberately a shared contract co-changes with its consumers by construction.** That
is not instability; it is the contract working. `unstable-interface` measures fan-in and co-change, and
neither distinguishes a shared kernel that is *supposed* to be there from an interface that is churning
because it is badly placed.

The two confirmations fit the same rule rather than contradicting it. archagent's `drift` and
`extraction` are *also* shared hubs — but ADR 0003 records that sharing as a **defect with a planned
remedy**, not as design. The reviewer confirmed them on exactly that basis: *"ADR 0003 identifies moving
that plumbing to a leaf module as the deferred remedy."*

So a single rule — **intended sharing is not instability; accidental sharing is** — explains all seven
labels. It is architecture-independent in principle, which is why it is worth stating. It is also
untested: no repository in the sample has an *intended* shared kernel that was confirmed, or an
*accidental* one that was dismissed, so the rule has not yet been given a chance to fail.

## What this suggests, and what it does not

**`layer-inversion` is ready to act on.** The evidence is 4 dismissals across 2 repositories in 2
categories with a total split and no anchoring. See §22.11 for the decision.

**`unstable-interface` is not.** 29% precision with an interval spanning [0.08, 0.64] is consistent with
anything from "badly broken" to "acceptable", and the confound is unresolved. What the round produced is
a sharp, falsifiable hypothesis about *why* it misfires, which is a better position than round 2's "the
split falls along the repository boundary and we cannot say more". Testing it needs a repository whose
sharing is accidental and which is not a Python web backend — which is obstudio, blocked by
[#25](https://github.com/BenedatLLC/archagent/issues/25).

## Provenance

- Worksheet `spotcheck/worksheet-2026-08-23.md`, 6 items, wardrowbe at `wardrowbe-v1.7.0` (`eda843f`)
- Findings captured by archagent `bc02f6d`; capture verified deterministic across two runs
- Reviewer: jeff, 2026-08-23; severity, confidence and recommendation withheld until ingest
- The `layer-inversion` worksheet guidance had its test-subsystem sentence removed before this round,
  deliberately, so that the `backend-tests` judgement would be independent

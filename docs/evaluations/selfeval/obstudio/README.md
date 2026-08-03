# obstudio — calibration round 2

**Target:** [signalfx/obstudio](https://github.com/signalfx/obstudio) at `88aebe8` (2026-07-31).
Chosen because neither of us wrote it, and because it is unlike archagent in every way that matters:
three languages, a real deployed product, an existing `docs/design.md` to check the artifact against.

**Scope:** the shipped product only. `pytest-codex-evals/`, `evals/` and `examples/` are test scaffolding
and excluded; `archagent.toml` here records that.

**Working clone:** `~/.cache/archagent/selfeval/obstudio` (not committed). `artifact/` is a snapshot of
the generated `docs/architecture/` at the time of scoring.

## Why this repo is a hard case for archagent

64 of ~148 product source files are **Go**, including the entire Observer service — the core of the
system. archagent analyses Python and TypeScript only. So the artifact describes Go (the `describe` phase
is agent-driven and language-agnostic) while every deterministic check is blind to it.

That produced four bugs, three in archagent and one class of unavoidable false positive:

| | Effect |
|---|---|
| `_resolve_ref` never handled wildcards | every backticked `**Covers:** `svc/*.go`` glob reported as "names code that no longer exists" — 43 false dangling refs |
| `_resolve_ref` searched only configured-language files | accurate `main.go` citations reported as missing, about code sitting in the tree |
| `**Config:**` was read to end-of-line | a wrapped manifest had half its keys honoured; the rest reported as undeclared |
| Go `**Connects:**` edges and Go-read config keys | **not fixable without a Go back end.** 15 stale-dep and 7 dangling-config findings are false and are documented as such in the artifact's `constitution.md` |

The first three are fixed and regression-tested (`tests/test_as_of.py`). The fourth is why
`Artifact agrees with the code` scores 0.00 on a repo whose documents are accurate.

## Deterministic score

**0.813** — `scorecard-2026-08-02.json`. Two checks are not at ceiling:

- **drift 0.00** — all 22 remaining items are the Go blind spot above. Nothing to fix in the artifact.
- **concentration 0.32** — one subsystem (`web-client`) holds 68% of the *countable* files, because the
  React client is 69 of the 84 Python/TS files while the Go majority counts as zero. The criterion is
  measuring the language gap, not the artifact. Whether the client should also be split into more
  subsystems is a fair question the judged half should answer.

## Status

Awaiting two independent scorings of `review-brief.md` — one human, one blind model judge — so an
agreement rate can be computed. Round 1's failure was a single scorer whose citations turned out to be
fabricated; see `../archagent/CALIBRATION.md`.

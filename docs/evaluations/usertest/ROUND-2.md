# End-to-end user test, round 2 — httpx, archagent 1.0.0rc2

One worksheet, returned 2026-08-23. **`docs_path = bundled`** — the round 1 failure is fixed and the
documentation was actually read.

| dimension | round 1 | round 2 |
|---|---|---|
| ease of use | 2 | **3** |
| correctness | 1 | **2** |
| completeness | 2 | **4** |
| impact | 2 | **3** |

**Not a series, and the ledger refuses to treat it as one.** `docs_path` differs (`fallback` → `bundled`)
and so does `archagent_version`, both of which are comparability keys. Every dimension moved up, but the
two rounds asked different questions of different testers, and only one of those differences is the
tool getting better. Read the numbers as two observations, not a trend.

**The tester was an AI agent** (Codex), self-described as having no prior knowledge of archagent, working
in a coding-agent environment. Recorded in the ledger. It finished in **11 minutes** against the kit's
60–90 minute estimate, which is itself a finding about who this kit can be given to: an agent reads at
machine speed and does not experience the friction a person would. Round 3 still needs a human stranger.

## What round 2 establishes that round 1 could not

Round 1's tester never reached the documentation. Round 2's did, and the parts of the tool that depend on
a reader having read it scored much better — `completeness` 2 → 4, and the setup path drew unprompted
praise for the second round running:

> The strongest experience was `init`: it detected the exact silent-failure risk, suggested the correct
> root source path, and the diagnostics proved 60 modules were in scope before any checks.

Both rounds independently named `init`'s source-path guard as the single most useful thing the tool did.
That path is two days old.

**The #33/#34/#35 fixes held.** No endpoint finding on production code, no mismatched investigation
brief, and `status`'s claimed-versus-described distinction was read correctly and reported as intended.
None of the three recurred.

## Six defects, all verified against the code

The dismissal rate went **up**: 33 of 35 candidates dismissed, ~94%, against round 1's ~80%. Every claim
below was reproduced before being recorded.

**[#36](https://github.com/BenedatLLC/archagent/issues/36) — `finding_id` collides.** `da39a3ee` is
`sha1("")[:8]`. Only group F passes a value set, so **every other finding hashes the empty string** and
the id degenerates to `sign:subjects[0]`. Two `layer-inversion` findings out of the same subsystem share
one id. That id is the key for the label store, for `investigations/`, and for `archagent investigate`,
so a recorded verdict can silently answer a finding nobody investigated.

**[#37](https://github.com/BenedatLLC/archagent/issues/37) — `TYPE_CHECKING` imports count as runtime
edges.** The tester opened `_types.py` and found the back-edges of a "high confidence" five-node tangle
were type-only. Reproduced exactly: `httpx/_exceptions.py`'s *only* internal import is
`if typing.TYPE_CHECKING: from ._models import ...`, and the graph reports a `_exceptions ↔ _models`
cycle that does not exist at runtime.

This is a systematic false-positive generator, not one finding — the graph feeds `cycle-subsystem`,
`layer-inversion`, `layer-skip`, `unstable-dependency`, god-component fan-in and the `_external_pull`
seam analysis. And a type-only back-edge is the standard Python idiom for *breaking* a real import
cycle, so **the graph is most wrong exactly where a project has been careful**.

**[#38](https://github.com/BenedatLLC/archagent/issues/38) — `check` contradicts itself.** It prints
"asserted in invariants.md, **verified by nobody**", then six lines later "9 state how they are verified"
and lists the tests. The wording predates the `Verification` column (#16), which exists to draw precisely
that distinction.

**[#39](https://github.com/BenedatLLC/archagent/issues/39) — `history-profile` learns archagent's own
scaffolding.** Its "domain terms" for httpx include `Columns` and `Record every invariant as a row` —
prose from archagent's own `invariants.md` template. `_GLOSSARY` matches any `**Bold** —` line under the
architecture directory, which is the style archagent scaffolds in.

This is a **feedback loop**, a worse category than a noisy heuristic: the tool scaffolds the docs, learns
from them, and caches the result as a fact about the target. It strengthens as more scaffolding appears
and is invisible in the output because the terms look plausible.

**[#40](https://github.com/BenedatLLC/archagent/issues/40) — `scan-invariants` calls test assertion
fragments "high confidence".** On httpx that list includes `response`, `123, 456` and `Transfer-Encoding`.
The confidence is about having detected a marker, not about the marker stating a rule, and the label
transfers the first to the second.

**[#41](https://github.com/BenedatLLC/archagent/issues/41) — star re-exports produce no edges.**
`httpx/__init__.py` is entirely `from ._api import *`; the graph gives it no imports at all. So a
correctly declared `interfaces -> auth` edge reads as stale, and the tester left the artifact accurate
rather than editing it to make `drift` green:

> Changing the artifact to make this report green would make the documentation less accurate.

That is the worst shape a drift tool can take — penalising an accurate artifact and rewarding an
inaccurate one.

## The theme, in the tester's words

> The weakest recurring issue was confidence calibration. `scan-invariants` calls value fragments from
> plain assertions "high confidence"; `check` says prose rules are "verified by nobody" despite
> immediately showing their verification metadata; and `evaluate` labels type-checking-only cycles high
> confidence. The docs repeatedly say to judge candidates, which is honest, but the terminal language
> still overstates what the extractors established.

Three of the six defects (#37, #38, #40) are that one sentence. Round 5 of calibration reached the same
conclusion from the other side — `finding_coverage_honesty` scored 5 of 5 because that part of the report
says exactly what it knows. The tool can do this; it does not do it uniformly.

## What separates round 2's verdict from round 1's

Round 1: *"I would not use the current evaluator as an action list without substantial manual review."*

Round 2 splits the tool in two:

> I would use init/status/graph/lint and reviewed BOUNDARY checks, because the configuration guardrails
> and coverage visibility were good. I would use scan/drift/evaluate only as a source of review prompts,
> never as a gate or backlog generator.

That is a sharper result than a low score. The deterministic half — config, coverage, compiled invariant
checks — is rated usable now. The candidate-generating half is not, and #36/#37/#41 are most of why.

## Provenance

- Worksheet: `usertest/httpx/worksheet-httpx-b5addb6-rc2.md` in the data repo
- Ledger: `usertest/usertest.csv`, run `2026-08-23-httpx-1.0.0rc2-bundled`
- Kit: `/tmp/archagent-usertest-round2`, built by `usertest.py kit` at `v1.0.0rc2`

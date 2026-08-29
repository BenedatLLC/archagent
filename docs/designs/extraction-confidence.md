---
status: proposed
date: 2026-08-29
---

# Design: Extraction the tool can vouch for

Three changes to how archagent extracts facts and reports what it could not see. They come out of a
retrospective on the evaluation work, held after the 1.0.0 release, and they exist to answer one
question that the evaluation record raises and cannot currently settle: **is the tool converging, or is
each new repository going to keep producing a fresh batch of defects?**

## Where this came from

Between 2026-08-02 and 2026-08-29 archagent went from 0.3.0 to 1.0.0 through five calibration rounds and
two end-to-end user tests. Three of those encounters were with a repository the tool had never seen, and
each produced defects:

| encounter | target | defects |
|---|---|---|
| calibration round 5 | dspy | 3 |
| user test round 1 | httpx | 3 |
| user test round 2 | httpx (after round 1's fixes) | 6 |

That pattern prompted the review this design records. The proposition put to me was:

> The current approach seems to be too dependent on specific heuristics in the code that only work for a
> few repositories. As soon as we try against a fresh repository, we find a bunch of bugs. We fix them in
> a way that addresses the specific issues, but does not generalize. I don't see convergence. Perhaps we
> should rely more on the flexibility of the agents and less on heuristics.

The conclusion is right and the stated reason is mostly not, and the difference decides what to build.
Classifying the twelve defects:

| class | count | examples |
|---|---|---|
| universal logic bugs | 5 | `__init__.py` relative imports, `TYPE_CHECKING`, `finding_id` collision, `lstrip("./")`, `_module_of` |
| presentation / calibration | 4 | "verified by nobody", "high confidence", coverage %, wrong questionnaire |
| feedback loop | 1 | `history-profile` learning its own scaffolding |
| genuine heuristic tuning | 2 | docstring exclusion, reserved address ranges |

The largest defect of the set is the clearest case against the "heuristics" reading. Relative-import
resolution in `__init__.py` was wrong for **every Python package ever written**; it is not a heuristic and
has no tuning parameter. It survived because of what the corpus contained:

```
ansible 0   django 0   dspy 0   fastapi-template 0   flask 0
homeassistant 0   litellm 0   datasette 2      ← relative imports in __init__.py
httpx 13
```

Six tuning repositories, every one with an effectively empty package initialiser. The bug was invisible
because the corpus was **uniform**, not because it was small — and more agent flexibility would not have
helped, since an agent handed a wrong import graph produces confidently wrong output too. Round 2's
tester caught it only by opening the file and re-deriving the extraction by hand.

Where the proposition is right, the evidence is sharper than the framing. Precision by sign, across every
labelled round:

| sign | confirm | dismiss | rate |
|---|---|---|---|
| `scattered-source-of-truth` | 8 | 1 | **89%** |
| `enum-value-escape` | 6 | 1 | **86%** |
| `cycle-subsystem` | 2 | 0 | 100% (n=2) |
| `layer-inversion` | 3 | 4 | **43%** |
| `unstable-interface` | 2 | 5 | **29%** |
| `layer-skip` | 0 | 3 | **0%** |

The split is not heuristic-versus-agent. It is **code scanning versus graph inference over a model**: the
two signals that work scan source for value sets, and the three that do not infer architectural meaning
from a dependency graph. Those same three generated most of this period's defects.

So the direction — deterministic code surfaces candidates, the agent judges — is the one the evidence
supports, and it is already the design. What has to change is *which* deterministic layer we trust, and
what it is allowed to claim. That is what these three changes are.

**On convergence specifically: we cannot currently answer it.** Round 1 found 3 defects and round 2 found
6, but round 2's tester got much further, so the counts are not comparable. The one real signal is that
all three of round 1's fixes held in round 2. Change 2 is the mechanism that would make the question
answerable rather than a matter of impression.

---

# Change 1 — A shape matrix, not a repo list

**Short form.** Synthetic fixtures per Python idiom — root package, `src/`, namespace packages, star
re-exports, `TYPE_CHECKING`, conditional imports, `__init__` re-exports. Minutes to write, and would have
caught 5 of the 12 defects before any human saw them.

## The explanation

Instead of "test against N real repositories", enumerate the **idioms extraction has to handle** and write
one tiny synthetic fixture per idiom. Assert the *extracted graph*, not the findings — so the assertions
stay stable as signals change.

Two of the 1.0.0 fixes already work this way (`tests/test_package_init_imports.py`,
`tests/test_type_only_imports.py`). This change stops writing them one-per-incident and enumerates the
cells up front.

**Why not just add more repositories.** Cost: litellm is 132 MiB and a ~90-second git walk; the nine
shapes probed while writing this design took under two seconds in total. Uniformity: the table above shows
six repositories that all shared one shape, so a seventh contributes whatever idioms it happens to hold,
chosen by accident.

And the decisive property — **a matrix is enumerable and reviewable**. You can look at a table and see
which cells are empty. You cannot look at "six repositories" and see what is missing, which is precisely
why `__init__.py` resolution stayed broken.

## The matrix, as it stands

Filled in during the review. The "verified" rows were unknown before it.

| shape | status |
|---|---|
| package under `src/` | covered (archagent itself) |
| package at repository root | fixed — dspy, `_module_of` |
| package one level down (`backend/app`) | fixed — `_guess_python_root` |
| `__init__.py` star re-export | fixed — #41 |
| `__init__.py` `from . import x` / `from .m import N` | fixed — #41 |
| `if TYPE_CHECKING:` bare and dotted | fixed — #37 |
| `if TYPE_CHECKING: … else:` | covered |
| **`TYPE_CHECKING` bound under an alias** | **gap — found during this review, unfixed** |
| namespace package (PEP 420) | verified |
| conditional `try/except ImportError` import | verified |
| import inside a function body | verified |
| module shadowing a stdlib name | verified |
| relative import at level ≥ 3 | verified |
| two source roots (monorepo) | verified |
| dot-directories in paths | fixed — `lstrip("./")` |
| non-Python majority → declared-only graph | covered |

The gap found: `from typing import TYPE_CHECKING as TC` followed by `if TC:` is not recognised as a guard,
so its imports are counted as runtime edges. That is #37 surviving in an aliased spelling, found in ninety
seconds by enumerating spellings rather than waiting for a repository to use one. The failure direction is
the safe one (a real edge is kept, a false cycle is possible), which is why it has not shown up in a
finding yet.

## What this does not replace

The corpus keeps its place for questions synthetic fixtures cannot answer: does the pipeline survive
scale, what is a signal's precision across real codebases, does the git walk finish. The split is
**matrix tests extraction correctness; corpus tests judgment quality and scale**. Today those are
conflated, and extraction defects are being found by the expensive instrument.

## Implementation

1. **Add `tests/shapes.py`** — a declarative table of `(name, source_paths, files, root_package,
   expected_runtime_edges, expected_type_only_edges)`. Files are inline dicts of a few lines each; no git,
   no network, no clone.
2. **Add `tests/test_shapes.py`** — parametrised over the table, asserting the exact graph. One test per
   cell so a failure names the idiom rather than "the graph is wrong".
3. **Seed it with the sixteen rows above**, converting the two existing shape-fixture files into table
   rows so there is one home rather than three.
4. **Fix the aliased-`TYPE_CHECKING` cell.** Resolve `from typing import TYPE_CHECKING as X` to the local
   binding and match `if X:` against it. Two lines in `_is_type_checking` plus a module-level pass to
   collect aliases.
5. **Add a coverage assertion**: every shape named in this document has a row. That keeps the table and
   the design from drifting apart, the same way `tests/test_usertest.py` ties the README's pinned version
   to `pyproject.toml`.
6. **Extend to JS/TS** once the Python table settles — the regex scanner has its own idiom set (`import
   type`, re-export barrels, `.js` specifiers resolving to `.ts`) and no fixtures at all.

**Cost.** Roughly a day for the harness plus the sixteen cells; a few minutes per idiom after that.

---

# Change 2 — Extractors verify their own preconditions

**Short form.** Every silent-clean failure this period had a check available for free: did `source_paths`
match files? did the glob resolve? did the graph get edges? "I extracted nothing" should be a reported
state everywhere, not only where we remembered to add it.

## The explanation

This is the counter-measure to the one failure mode that recurred all period: **a condition rendering as
a plausible clean result.**

Every extractor has assumptions about its input that nothing checks. When they fail it returns *few or no
facts*, which is byte-identical to correctly finding nothing there:

| what broke | what the tool said |
|---|---|
| `source_paths = ["src"]` on a root-package repository | "All invariants hold" |
| ast-grep given `./dspy/**`, which it silently ignores | rule PASSED (0 of 154 sites matched) |
| `git log` walk timed out on litellm | every history check quiet, run looks clean |
| `__init__.py` relative imports misresolved | package root "imports nothing" |

None produced an error. Each produced a *smaller true-looking answer*.

**The pattern already exists in the codebase, retrofitted one incident at a time**: `CoChange.mining_failed`,
`check.py` reporting *skipped* rather than passing, `EvaluationResult.inactive` carrying the signs it
stands for, `graph_is_declared_only`, `archagent modules` as a diagnostic. Each was added after a specific
silent failure. This change makes it a protocol rather than a reflex.

### Two kinds of check, and why the second matters more

**Preconditions** ask *was my input sane?* — did `source_paths` match anything, is git available, did the
generated glob match a file. Cheap, and mostly present already.

**Postconditions** ask *is my output plausible given my input?* This is the one that catches #41 and #37,
because in both cases the input was fine. A precondition check cannot see them. This is the gap.

### The concrete postcondition, demonstrated

For the import graph the best available postcondition is exact rather than heuristic: **a relative import
must resolve to a file in the source set.** `import numpy` legitimately resolves to nothing internal;
`from . import x` cannot. So "a relative import that resolved to nothing" is a defect counter with no
false-positive mode, which is what makes it safe to report loudly.

Run against httpx at `b5addb6`, with only the resolution rule varied:

```
pre-fix rule    18 of 88 relative imports resolved to nothing  (20%)
                  httpx/__init__.py: 13
                  httpx/_transports/__init__.py: 5
current rule     0 of 88 relative imports resolved to nothing  (0%)
```

That single counter would have caught #41 before any human ran the tool, on any repository with a
re-exporting package initialiser — no corpus addition, no user test, no reviewer opening a file.

### The general form

**Count candidate sites seen, count sites resolved, report the ratio.** Seeing candidates is usually
cheap — a node type, a regex. Resolving them is the hard part. The gap between the two is the extractor's
blind spot, and it is reportable *without knowing the right answer*.

| extractor | sites seen | resolved | would have caught |
|---|---|---|---|
| import graph | relative-import nodes | edges into the source set | #41, `source_paths`, module collisions |
| `generate.py` | globs emitted | files each glob matches | the `./dspy/**` silent PASS |
| `configscan` | textual `getenv` / `process.env` hits | keys returned | wrapper and pydantic resolution failures |
| `webapi` | decorator-shaped lines | `Route` objects | framework not recognised |
| `datamap` | table-definition-shaped lines | table defs returned | ORM dialect not recognised |
| `cochange` | — | — | already done (`mining_failed`) |

### Why this is the convergence mechanism

Finding #41 required: build a kit, recruit a tester, have them run a full describe, notice a `drift`
result was wrong, open the source, report it. That loop is weeks long and depends on someone being both
careful and skeptical.

With the counter, `archagent modules` on httpx says *"20% of relative imports resolved to nothing"* on the
first run, day one, with the offending files named. The same holds for the next idiom nobody anticipated.
**We would not have to predict an idiom to be told our extraction of it failed** — which is what turns
"are we converging?" from an impression into a number the tool reports about itself.

### The honest limit

It reports *unexplained gaps*, not wrong answers. `TYPE_CHECKING` produced edges that resolved fine; they
were semantically wrong, and no coverage counter sees that. This closes the "went quiet" class, which is
most of what bit us, and leaves "confidently wrong" to review and to Change 1.

One more caution, learned immediately: the first prototype of this probe reported a clean `0 of 0` over
an empty file set — it committed the exact error it was written to detect, on its first run. That argues
for a shared reporting type rather than a check each extractor remembers to write.

## Implementation

1. **Add `src/archagent/coverage.py`** with a small `Coverage` record: `what` (the extractor), `seen`,
   `resolved`, `unresolved_examples: list[str]`, and a `sound` property. Deliberately a leaf module, like
   `tiers.py`, so any extractor can use it without a cycle.
2. **`Coverage` refuses to be empty-clean.** `seen == 0` is a distinct state from `seen > 0 and
   unresolved == 0`, and the renderer must never print the two the same way. A test asserts this directly,
   because the prototype failed exactly here.
3. **Instrument the import graph first** — it has a proven catch. `_imports_of` already walks the nodes;
   count relative-import statements and how many resolved into `module_index`.
4. **Surface it in `archagent modules`**, which exists for this class of diagnosis, and in `status`, which
   is where a new user looks first. Report the ratio and name up to five offending files.
5. **Add the generated-glob precondition to `generate.py`**: a rule whose globs match zero files is
   reported `skipped`, never `PASS`. This is the `./dspy/**` case and it is the highest-severity one, since
   it currently reports a passing check over nothing.
6. **Then `configscan`, `webapi`, `datamap`**, in that order — most-used first. Each needs a cheap
   "candidate site" counter, which is a regex over the same text the scanner already reads.
7. **Wire the ratio into `evaluate`'s coverage report**, which already has the right vocabulary
   (`inactive`, `signs`, degraded-versus-absent) and already scored 5 of 5 for honesty in calibration
   round 5. This is an extension of the part of the tool that already works.

**Cost.** Half a day for `coverage.py` and the import graph; an hour or so per additional extractor.

---

# Change 3 — Severity and confidence leave the deterministic layer

**Short form.** Hand the agent evidence and uncertainty; let it produce the judgement. Three of round 2's
six defects were one sentence from the tester: *"the terminal language still overstates what the
extractors established."*

## The explanation

This is the part of the original proposition I think is unambiguously right, and the evaluation record
supports it from two directions at once.

**From the calibration side.** Round 3 disputed none of 14 measurements. Round 5 rated 11 of 19 sampled
findings as noise and scored `finding_actionability` 2 of 5 — while `finding_coverage_honesty` scored
**5 of 5**. The measurements are sound; the *labels attached to them* are not. Round 5's conclusion was
that the loss sits between computing a fact and telling a reader what to do about it.

**From the user-test side.** Round 2's tester split the tool in two without being asked to:

> I would use init/status/graph/lint and reviewed BOUNDARY checks, because the configuration guardrails
> and coverage visibility were good. I would use scan/drift/evaluate only as a source of review prompts,
> never as a gate or backlog generator.

And named the reason, which accounts for three of the six defects that round:

> `scan-invariants` calls value fragments from plain assertions "high confidence"; `check` says prose
> rules are "verified by nobody" despite immediately showing their verification metadata; and `evaluate`
> labels type-checking-only cycles high confidence. The docs repeatedly say to judge candidates, which is
> honest, but the terminal language still overstates what the extractors established.

Each of those was fixed individually (#38, #40, #37). The pattern was not: **the deterministic layer keeps
emitting words that assert more than a count can support.** `severity` is computed from file and commit
counts and rendered as HIGH/MED/LOW; `confidence` is computed from how a fact was obtained and rendered
next to a recommendation. A reader cannot tell either from a judgement, and the report does not currently
make them.

The distinction to preserve, because it is real: `severity` is *mechanical* and documented as such, and
the caveat now prints alongside the findings (fixed after round 5, where a run with 65 findings and zero
flagged printed HIGH and MED and never said what those words meant). But a caveat competing with a
coloured HIGH loses. The fix is not better wording again — it is to stop emitting the word.

**What the deterministic layer should emit instead**: the measurement, the evidence, and what it could not
establish. `evaluate --json` already carries all three. The agent then produces severity, priority and
recommendation with the code in front of it, which is exactly what `/archagent-evaluate` exists for and
what round 2's tester did by hand — retaining 2 of 35 candidates and writing a judged report.

This also removes a category of defect rather than an instance of one. #37's "high confidence tangle" was
damaging because of the label, not the edge: a cycle reported as *an edge we inferred, from imports we
could not tell were type-only* would have prompted exactly the check the tester performed.

## Implementation

Staged, because the raw output has direct consumers (`spotcheck.py`, `ledger.py`, the corpus harness) and
changing it changes their comparability keys.

1. **Add `Finding.basis`** — a structured record of what produced the finding: the rule that fired, the
   counts, the evidence sites, and what could not be established (feeding on Change 2's coverage). Purely
   additive; nothing reads it yet.
2. **Make the human-facing renderer basis-first.** The default `archagent evaluate` output leads with the
   measurement and the evidence, and prints severity only in a trailing, uncoloured position — or not at
   all once step 4 lands. `--json` is unchanged so the harness keeps working.
3. **Move the severity vocabulary into the `/archagent-evaluate` prompt** with instructions to derive it
   from the basis plus the code, not to echo the tool's. The prompt already clusters and prioritises; it
   should own the whole judgement.
4. **Retire `severity` from the default human output** once step 3 is calibrated, keeping it in `--json`
   under a name that says what it is — `mechanical_rank` — so no consumer reads it as a verdict.
5. **Demote or retire the signals that cannot earn their keep.** `layer-skip` is 0-for-3 and has been
   narrowed twice; `unstable-interface` is 2-for-7 with a pre-registered confound that three rounds did
   not resolve. Publish precision per sign in the coverage report, and set a rule in advance: a sign below
   a stated confirm rate over a stated sample is demoted to `--group` opt-in rather than tuned again.
   **This is the convergence mechanism for judgement** the way Change 2 is for extraction — a signal that
   cannot earn its keep gets removed rather than retuned.
6. **Re-measure.** Steps 2–5 change `FINDINGS_KEYS` comparability, so the first round after them starts a
   new series. Say so in the write-up rather than presenting a step change as an improvement.

**Cost.** Step 1 is an afternoon. Steps 2–4 are a week including prompt calibration. Step 5 needs a
pre-registered threshold agreed before the numbers are looked at again, per `evaluating-archagent.md` §12.

---

# Sequencing

1. **Change 2 for the import graph, plus Change 1's harness** — they share a first target and one
   validates the other. The aliased-`TYPE_CHECKING` cell is a two-line fix folded in here.
2. **Change 2 for `generate.py`** — the highest-severity silent failure still live, since a scoped rule
   matching nothing currently reports PASS.
3. **Change 1's remaining cells, and the JS/TS table.**
4. **Change 3**, which is the largest and wants a user-test round after it rather than before.

## What would falsify this

If a fresh target after Changes 1 and 2 still produces extraction defects that the coverage counters did
not flag, then the diagnosis in this document is wrong — the problem would be heuristic fragility after
all, and the response should be to move extraction itself toward the agent. That is a real possible
outcome and it should be recorded as such before round 3 rather than after.

The measurement to keep, either way: **defects per fresh target, with a fixed protocol**, so the
convergence question stops being a matter of impression on anyone's part.

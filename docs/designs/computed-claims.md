---
status: proposed — acceptance gated on the evaluation in §8
date: 2026-08-16
author: Jeff Fischer (proposal), written up with Claude
---

# Design: Computed claims

Architecture documents state facts about code: *nineteen tables*, *four locks*, *three routes change
state*, *retries are bounded at three*. Two things go wrong with those facts, and this project has now
recorded both dozens of times.

**They can be written from memory rather than from the code in front of us.** A writing agent that has
read one of five sibling files generalises to all five; one that has seen a directory listing infers what
is in the files. The claim reads exactly like a claim that was checked.

**They stop being true.** A number correct at the commit it was written for is silently wrong three months
later, and nothing notices, because nothing knows the number was a claim about anything in particular.

This design proposes making such claims **computed, citable and checked**: each one is produced by a
deterministic command, recorded in a table with its command and its value, and re-run on demand to detect
divergence. Architecture prose then cites the claim rather than stating a number.

## Terms used in this document

- **Claim** — one fact about the code that a deterministic command can establish: a count, an
  enumeration, the presence or absence of a construct. *Nineteen tables* is a claim. *The store is the
  system's only state* is not.
- **Claims file** — the Markdown table holding every claim for one artifact: an identifier, the command,
  the recorded value, and a note saying what the claim is for.
- **`check`** — run every command, compare against the recorded values, report divergences and command
  failures. Read-only.
- **`regenerate`** — update recorded values from current command output, as a diff a person accepts.
- **The ADL** — archagent's Architecture Description Language (`docs/ADL-SPEC.md`), the format of the
  documents archagent generates.
- **Invariants** — the ADL's existing table of checkable design rules. **Not the same thing**; see §2.
- **Artifact / target / drift** — as defined in `evaluating-archagent.md`.

## 1. What is proposed

Alongside the architecture documents, archagent maintains one more file — say `claims.md`:

```markdown
| id | claim | command | value | last checked |
|----|-------|---------|-------|--------------|
| C-001 | ORM tables declared | `rg -c '__tablename__' backend/app/models/ \| awk -F: '{s+=$2} END {print s}'` | 19 | 2026-08-16 |
| C-002 | item lifecycle states | `rg -A6 'class ItemStatus' backend/app/models/item.py \| rg '= "' \| wc -l` | 4 | 2026-08-16 |
| C-003 | tagging retry limit | `rg 'TAGGING_MAX_TRIES = ' backend/app/workers/tagging.py` | `TAGGING_MAX_TRIES = 3` | 2026-08-16 |
```

Prose then cites the claim beside the fact:

> The worker tags an item through a queue, retrying at most three times [C-003] before writing a terminal
> status. `ItemStatus` has four values [C-002].

A script maintains the file in two modes:

- **`check`** — run every command, compare to `value`, report each divergence and each command that failed
  or returned nothing. This is what makes drift mechanical: a code change that moves a number is reported
  by comparison rather than inferred from a diff.
- **`regenerate`** — re-run and update, emitting a diff for a human or agent to accept (§5.2).

Three things follow. Each claim is **objectively justified**, because the command is recorded next to it.
Each is **re-checkable at any later commit** without re-reading the code. And an artifact-wide sweep
becomes a cheap, deterministic operation instead of an agent-driven review.

## 2. This is not the invariants table

The ADL already has a table of checkable rules, and confusing the two would be easy.

|  | Invariants | Claims |
|---|---|---|
| What it constrains | the **software under development** | the **documentation** |
| A violation means | someone broke a design rule | the documents no longer describe the code |
| Who acts on it | the developer changing the code | whoever maintains the artifact |
| Failure mode it prevents | architectural erosion | documentation drift and fabricated detail |

An invariant says *no route may bypass the service layer*. A claim says *there are 47 routes, and here is
the command that counts them*. Breaking the first is a bug. Breaking the second is not a bug at all — the
code was allowed to change, and the documentation simply has to catch up.

## 3. Evidence that this targets a real failure

Not a projection. Every confirmed defect from calibration rounds 2 and 3 was classified by whether a
deterministic command could have settled it.

**17 of the 28 confirmed defects are claims of exactly this shape** — a number or an enumeration taken
from memory or generalised from one sample. A representative selection:

| the artifact said | the truth | the command that settles it |
|---|---|---|
| "64 Go files" | 57 | `find observer -name '*.go' \| wc -l` |
| "eight SQLAlchemy tables" | 19 | `rg -c '__tablename__' models/` |
| "65 backend Python files" | 125 | `find backend -name '*.py' \| wc -l` |
| "schemas for seven of eight models" | five | `ls schemas/ models/` |
| "`Store` is one `sync.Mutex`" | four locks | `rg 'sync\.(RW)?Mutex' store.go` |
| "`validate_security` logs rather than raises" | raises | `rg 'raise RuntimeError' config.py` |
| "falls back to local auth" | no such mode | `rg -A6 'def get_auth_mode'` |
| "per-skill scripts are shims" | 2,616 lines across four | `wc -l skills/*/scripts/*.py` |
| "only `POST /api/validation/*` mutates" | plus `DELETE /api/data` | `rg 'HandleFunc\("(POST\|DELETE)'` |

Three more are partially reachable. **Eight are outside its reach, and they divide cleanly:**

- **Omissions** — a wide-open cross-origin policy, a server-side fetch of a caller-supplied URL, per-user
  ownership enforced only by convention. A claims table cannot make you claim something you never thought
  of. Both of the security-relevant findings in this project's history are of this kind.
- **Presentation** — subsystem documents with no diagram, a generated map with no caption.

**Stating that boundary is part of the proposal.** This addresses claims made wrongly. It does nothing
about claims never made, and it must not be described as making the artifact trustworthy.

The instruments that would measure it sit in the right place too: **23 of the 33 per-repository checklist
items (§14 of `evaluating-archagent.md`) are claims a command could compute**, four more partially, and
only six are genuinely semantic.

## 4. Where the ADL changes

Three additions, all optional in the ADL's existing sense — a document without them stays conformant.

1. **A claims file** at the artifact root, with the table shape of §1. New document type.
2. **A claim reference** in prose: `[C-003]`, resolvable against the claims file. This is the part that
   complicates the format for a reader, and it is the part that earns the change: an uncited number is
   visibly an uncited number.
3. **`Claims:` in subsystem front-matter** (optional) — which claims that document depends on, so a
   divergence can name the documents that need revisiting rather than only the claim.

### The tension with an existing design principle

ADL §1.2 states: *"Static and non-executing. All extraction is by text/AST analysis; the described system
is never run."*

This proposal runs commands. It does not run the described system — `rg`, `wc`, `ast-grep` and `find`
analyse source text and never execute it — but the principle as written says "non-executing" and would
need amending to something narrower:

> **Static with respect to the described system.** The described system is never run. Claim commands are
> restricted to read-only source analysis (§5.3).

If that amendment is unacceptable, this design should be rejected rather than weakened, because the whole
mechanism is the execution.

## 5. Design risks, and what to do about each

### 5.1 A command that returns the right number for the wrong reason

`rg -c '__tablename__' | ...` → 19 is sound. `rg -c 'class.*Base' | ...` → 19 is a coincidence that will
pass `check` forever. This is the failure this project has recorded six times — *a citation that resolves
and does not support its claim* — moved up one level, and it is the most serious objection to the design.

**Partial defence: store output, not just a count, when the output is small.** `19` tells a reviewer
nothing; the nineteen table names tell them at a glance whether the command measures the right thing. A
claim whose value is a bare integer with no visible derivation should be treated as the weak kind.

There is no complete defence. The claims file makes numbers *honest*; whether they are *relevant* still
takes a reader.

### 5.2 `regenerate` is where honesty leaks

If `regenerate` silently overwrites values, drift is erased rather than reported, and the tool quietly
launders the exact change it exists to catch. It must emit a diff that is read and accepted deliberately —
the same rule the pinned-corpus regression already operates under (`evaluating-archagent.md` §6), for the
same reason.

Concretely: `regenerate` prints every change, exits non-zero if run non-interactively with changes
pending, and never runs as a side effect of `describe`.

### 5.3 Determinism is a recurring cost, and a checker that cries wolf gets ignored

`rg` version, `find` ordering, locale, working directory, whether `.gitignore` is honoured, trailing
newlines. Any of these can produce a divergence that is not a code change. A checker with a false-positive
rate gets switched off, which is worse than not having it.

Mitigation: constrain commands to a small allowlist of read-only tools, run from a defined working
directory with normalised output (sorted, trailing whitespace stripped), and record the tool versions in
the claims file header. Arbitrary shell should be an escape hatch that is visibly an escape hatch.

### 5.4 The claims file is executable content

Running commands from a file that lives in the repository being described is arbitrary code execution
driven by repository content. Acceptable for your own repositories; it needs stating plainly before
archagent is pointed at a repository the operator does not control. The §5.3 allowlist is most of the
mitigation; the rest is a prominent warning and, for untrusted targets, a refusal.

## 6. Alternative considered: a generated maintenance script

The alternative is for archagent to generate a per-repository shell script that maintains the Markdown,
with the script as the source of truth and the Markdown as a human-readable summary.

**Rejected, though it is easier to implement.** Two files can disagree, and nothing would check that they
do not — a stale summary beside a correct script is a *new* way for documentation to be wrong, added by a
change whose purpose is to stop documentation being wrong. Keeping the Markdown authoritative means there
is one artifact, and the parser is the only thing that has to be right.

The precedent is local: the recurrence suite (`evaluating-archagent.md` §13) has exactly this shape —
declarative entries in a file, a runner that executes them — and it works.

## 7. Related work

**ESAA: Event Sourcing for Autonomous Agents in LLM-Based Software Engineering** (arXiv 2602.23193, dos
Santos Filho, Feb 2026) is the closest framing. Its core separation — the agent emits only structured
intentions, while a deterministic orchestrator validates them, persists them, and projects a *verifiable
materialized view* checkable by replay — is the same division of labour proposed here: the probabilistic
writer proposes a claim, a deterministic mechanism establishes and re-establishes it. Its `esaa verify`
plays the role of `check`.

Two differences worth keeping in view. ESAA's log records the agent's *actions*; the claims file records
facts about *the code as it stands*, which is what survives a change made outside the agent. And its
evidence is two self-reported case studies with no comparison, so it supports the framing and not the
effect.

SpecKit's `analyze` pass — generating checklists from a design and then quality-controlling against them —
is the same instinct applied to specifications rather than to code facts.

**arXiv 2502.13069 is not related.** It is *Ambig-SWE: Interactive Agents to Overcome Underspecificity in
Software Engineering* (Vijayvargiya et al.), about detecting underspecified instructions and asking
clarifying questions. Recorded here so the reference is not chased twice.

## 8. The evaluation that decides this

Pre-registered, in the sense §7 of `evaluating-archagent.md` uses: the thresholds below are fixed **before
the measurement runs**, and a deviation is recorded rather than quietly absorbed.

### Step 1 — retrospective, costs no generation and no judge

Build the mechanism. Write claims files for obstudio at `88aebe8` and wardrowbe at `wardrowbe-v1.7.0`,
covering every numeric or enumerable fact the **existing** artifacts state. Run `check`.

This asks one question: *of the facts these artifacts assert, how many can be expressed as a command, and
how many of those commands disagree with the artifact today?*

**Prediction, recorded before running: at least 17 divergences**, since 17 known defects are of this shape.
Materially fewer means the mechanism does not reach the failures it was designed for, and steps 2 and 3
should not be run.

### Step 2 — generation variance, the missing prerequisite

An ADL change forces regeneration, so the relevant noise is how much two artifacts of the *same*
repository differ under *identical* prompts. That has never been measured; the noise floor on record is
judging variance, which holds the artifact fixed.

Describe one target three times under the current ADL. Score all three. The spread is the floor any later
comparison is read against, and the same runs serve as the before arm of step 3.

### Step 3 — two arms

Regenerate under the current ADL and under the amended one, on targets **excluding** whichever repository
prompted the change (`evaluating-archagent.md` §18). Score both arms with the per-repository checklists
and with a count of citations carrying a line number.

**Accept if:** items move from `wrong`/`absent` to `correct` on at least five more items than move the
other way, paired item by item across the arms; and the unit suite, the recurrence suite and the
pinned-corpus regression all still pass; and no `serious` checklist item regresses.

**Reject if** the net movement is under three items, or any arm shows a regression the recurrence suite
catches.

**Between three and five: undecided, and gather another target** rather than deciding on the number.

### One thing the measurement will overstate

The obstudio and wardrowbe checklists were written **from those artifacts' own defects**, so they are
enriched for precisely what this change fixes. A large improvement there is real and is *not* an estimate
of the effect on a repository nobody has looked at. An unbiased figure needs a fresh target — calibration
round 4, which is scheduled regardless.

## 9. Status

**Proposed. Not accepted.** The next action is step 1, which is cheap and can retire the idea before any
further cost.

This document is kept whatever the outcome. If the change is rejected the status becomes `rejected`, the
measurements are recorded here, and the reasoning stays on file — a rejected design with evidence is worth
more than a silence someone re-derives in six months.

| Step | Result |
|---|---|
| 1 — retrospective divergence count | not run |
| 2 — generation variance | not run |
| 3 — two arms | not run |

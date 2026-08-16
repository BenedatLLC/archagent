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
- **`check`** — run every command, compare against the recorded values, and report each divergence with
  both the recorded and the observed value. The only mode; see §5.2.
- **Stage** — one element of a claim command's pipeline. `rg foo src/ | wc -l` has two stages.
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

**One mode: `check`.** It runs every command, compares the result to `value`, and reports each divergence
with both numbers, plus every command that failed or returned nothing. It never writes. This is what makes
drift mechanical: a code change that moves a number is reported by comparison rather than inferred from a
diff. §5.2 explains why there is no second mode.

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

**The ADL conformance checker gains a fourth job**, alongside resolving claim references: statically
validating every command in the claims file against the rules of §5.4, and reporting a claim whose command
is unsafe or malformed as a conformance failure. That check is worth running even when nobody intends to
execute anything, because it is what makes an unsafe command visible in review — the commands are written
by an agent, and nobody re-derives them by hand.

### The tension with an existing design principle

ADL §1.2 states: *"Static and non-executing. All extraction is by text/AST analysis; the described system
is never run."*

This proposal runs commands. It does not run the described system — `rg`, `wc`, `ast-grep` and `find`
analyse source text and never execute it — but the principle as written says "non-executing" and would
need amending to something narrower:

> **Static with respect to the described system.** The described system is never run. Claim commands are
> restricted to read-only source analysis, executed without a shell, from an allowlist of tools
> (§5.3, §5.4).

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

### 5.2 There is no `regenerate`, and that is deliberate

An earlier draft had a second mode that re-ran the commands and updated the recorded values, emitting a
diff for someone to accept. **It is removed.** The argument for removing it is stronger than the argument
for constraining it.

**It is not needed.** `check` already computes the new value — that is how it detects a divergence. So it
can simply report `C-002: recorded 4, observed 5`, and whoever is revising the documents copies it across
in the same edit where they revise the prose that cites it. A mode that writes the number adds nothing but
the writing.

**And the writing is the whole risk.** ESAA (§7) names the failure directly: an agent "may rewrite
specifications to bypass local compilation failures." A one-command path from *this check is failing* to
*this check is passing*, with no obligation to touch the prose, is exactly that path. Given it, an agent
under instruction to make things pass will take it, and the artifact silently loses the fact rather than
gaining a correction. Without it, the only way to clear a divergence is to edit the document — which is
the work that actually needed doing.

**The asymmetry decides it.** The cost of not having the mode is transcription effort, which is bounded
and visible. The cost of having it is a mechanism that erases drift while reporting success, which is
unbounded and invisible — and is the failure shape this project has hit seven times.

If bulk churn ever makes hand-editing genuinely painful — a refactor moving forty claims at once — the
answer is `check --format=patch`, printing a patch the caller applies themselves, not a mode that applies
it. Even then it should print the affected documents so the prose is not forgotten. Do not build it until
the pain is real.

### 5.3 Determinism is a recurring cost, and a checker that cries wolf gets ignored

`rg` version, `find` ordering, locale, working directory, whether `.gitignore` is honoured, trailing
newlines. Any of these can produce a divergence that is not a code change. A checker with a false-positive
rate gets switched off, which is worse than not having it.

Mitigation: constrain commands to a small allowlist of read-only tools, run from a defined working
directory with normalised output (sorted, trailing whitespace stripped), and record the tool versions in
the claims file header. Arbitrary shell should be an escape hatch that is visibly an escape hatch.

### 5.4 The claims file is executable content

A file that lives in the repository being described, containing commands archagent runs, is arbitrary code
execution driven by repository content. Two distinct exposures:

- **The repository is not yours.** Its claims file was written by someone else. Running it is running
  their code.
- **The repository is yours, and the writer is an agent.** A command that is subtly wrong or subtly
  dangerous reads exactly like one that is neither, and the whole point of the file is that nobody
  re-derives its contents by hand.

**The governing rule, which decides every case below: prefer an uncomputed claim to an unsafe command.**
A claim that cannot be established within these limits is written as ordinary prose without a `[C-nnn]`
reference. Losing a computed claim costs a little coverage. Admitting one unsafe command costs the
property that makes the mechanism worth having.

#### Defence 1 — no shell, ever

Do not hand the command string to a shell. Split it on `|` into stages, `shlex.split` each stage, and wire
the pipeline with `subprocess` using `shell=False`.

This is the strongest single measure, because it makes whole categories *unrepresentable* rather than
detected: redirects (`>`, `>>`), command substitution (`` ` ``, `$(...)`), chaining (`;`, `&&`, `||`),
background (`&`), globbing, and variable expansion never happen, because nothing ever interprets them. A
command containing them fails to parse and is reported as a malformed claim.

#### Defence 2 — an allowlist of stages, with per-tool flag rules

Each stage's program must be on a short list of read-only analysis tools: `rg`, `grep`, `ast-grep`, `find`,
`ls`, `wc`, `sort`, `uniq`, `head`, `tail`, `cut`, `tr`, `awk`, `sed`, `jq`, and `git` restricted to
`log`, `ls-files`, `grep`, `show`, `rev-parse`.

Several of these can write or execute despite being "read-only tools", and the flag rules are where that
is handled. This list is the part most likely to be incomplete, and it should be treated as a live
security surface rather than a settled constant:

| tool | rejected because |
|---|---|
| `find -exec`, `-execdir`, `-delete`, `-fprintf`, `-fls` | executes or writes |
| `sed -i`, `--in-place`; any `w` or `W` command in the script | writes |
| `awk` script containing `system(`, `print >`, `printf >`, `\|&`, `close(` | executes or writes |
| `rg --pre`, `--pre-glob`, `--hostname-bin`, `-z/--search-zip` | `--pre` runs an arbitrary preprocessor |
| `git` outside the subcommand list | `git config`, `git push`, `-c core.pager=...` all execute or mutate |
| any interpreter — `sh`, `bash`, `python`, `node`, `perl`, `ruby` | arbitrary by definition |
| `xargs`, `env`, `nice`, `time`, `sudo` | execute something else |
| any network tool — `curl`, `wget`, `nc`, `ssh` | exfiltration |

#### Defence 3 — contain what does run

- **Working directory is the target root**, and every path argument must resolve inside it: no absolute
  paths, no `..` escaping, no symlink following out of the tree.
- **Scrubbed environment.** Pass only `PATH`, `LANG` and `HOME` if strictly needed. A command cannot print
  a token it cannot see, and CI environments are full of tokens.
- **No stdin**, a wall-clock timeout, and an output size cap.
- **Record tool versions** in the claims file header, so a version bump is diagnosed as a version bump
  rather than as drift (§5.3).

#### Defence 4 — the recorded value is the thing that gets committed

The output is written into a file that goes into version control, so this is where a secret would actually
leak, and it is checkable cheaply:

- **Refuse paths that name secret-bearing files** — `.env*`, `*.pem`, `*.key`, `id_rsa*`, `.npmrc`,
  `.netrc`, `.git-credentials`, `.aws/`, `.ssh/`, `credentials*`, `*secret*` — in any stage's arguments.
- **Cap the recorded value** at a few hundred characters. Nearly every real claim is a count or a short
  list of identifiers; a long opaque value is a signal in itself.
- **Scan the value before recording it** for known credential prefixes and long high-entropy strings, and
  refuse to record rather than truncating. Truncating would store a partial secret and report success.

#### Defence 5 — the prompts

Whichever agent writes or revises a claim is told, in the `describe` guidance:

- a claim command **reads and counts; it never writes, never fetches, never executes**;
- its output must contain **no secrets, credentials, tokens or personal data** — write the claim as prose
  rather than as a command if that cannot be guaranteed;
- prefer the **narrowest path** that establishes the claim, not the repository root;
- **an uncomputed claim is an acceptable outcome.** This has to be said explicitly, or an agent measured
  on coverage will reach for a command it should not.

Prompts are the weakest of the five and are listed last for that reason. They shape what gets *written*;
defences 1–4 decide what gets *run*, and only the latter holds against a claims file archagent did not
author.

#### What is still not covered

A command that is entirely within the rules and still reads something it should not — `rg 'password'
config/` returning matched lines. Defence 4's value scan is the only thing standing in front of that, and
it is heuristic. For a target the operator does not control, the honest position is that `check` should
refuse to run at all unless explicitly enabled for that repository, and say so.

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
Santos Filho, Feb 2026; `~/research/architecture-agent/papers/2602.23193v1.pdf`) is the closest framing.
Its core separation — the agent emits only structured intentions, while a deterministic orchestrator
validates them, persists them, and projects a *verifiable materialized view* checkable by replay — is the
same division of labour proposed here: the probabilistic writer proposes a claim, a deterministic
mechanism establishes and re-establishes it. Its `esaa verify` plays the role of `check`.

Its framing of the failure mode is the sharper contribution, and it is the reason §5.2 below removes a
command rather than constraining it. From the introduction: an agent "may rewrite specifications to bypass
local compilation failures." **The artifact is most at risk from the step that updates it** — not from the
step that writes it and not from the step that checks it.

Two differences worth keeping in view. ESAA's log records the agent's *actions*; the claims file records
facts about *the code as it stands*, which is what survives a change made outside the agent. And its
evidence is two self-reported case studies with no comparison arm, so it supports the framing and not the
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

Step 1 also produces the first honest measure of the safety rules' cost. **Record how many facts had to be
left uncomputed** because no command within §5.4's limits would establish them. That number is the price of
the rules, and it is better known now than discovered later; if it is large, the allowlist is the thing to
revisit, not the rules.

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
| 1 — facts left uncomputed under the safety rules | not run |
| 2 — generation variance | not run |
| 3 — two arms | not run |

### Revisions

- **2026-08-16** — `regenerate` removed (§5.2); the safety rules written out as five defences with the
  governing rule *prefer an uncomputed claim to an unsafe command* (§5.4); ESAA read and cited.

---
status: proposed — predicate redesign passed step 1 on 2026-08-16; step 2 next
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
  both the recorded and the observed value. The only mode; see §5.2. *Within this document only* — it is
  not a command name, and archagent's existing `check` command means something else (§5.6).
- **Stage** — one element of a claim command's pipeline. `rg foo src/ | wc -l` has two stages.
- **The ADL** — archagent's Architecture Description Language (`docs/ADL-SPEC.md`), the format of the
  documents archagent generates.
- **Invariants** — the ADL's existing table of checkable design rules. **Not the same thing**; see §2.
- **Artifact / target / drift** — as defined in `evaluating-archagent.md`.

## The workflow — what runs when

Three moments in a claim's life: it is **authored**, it is **checked** repeatedly, and eventually it is
**revised**. Different commands drive each, and only the first and the last write anything.

### Authoring — during `describe`

While writing the documents, the agent reaches a fact that is a count or an enumeration: *nineteen tables*,
*four lifecycle states*, *three routes change state*. For each one:

1. It writes a claim row — an id, a description, and the command that establishes the fact.
2. archagent **validates the command statically** against §5.4's rules, and refuses it if it is malformed,
   uses a tool outside the allowlist, or touches a path it should not.
3. archagent **executes the accepted command** — parsed into pipeline stages, no shell — and records the
   result as the claim's value.
4. The agent writes the fact into prose with a `[C-nnn]` reference beside it.

If step 2 refuses, or the agent judges that no safe command establishes the fact, **the fact goes into the
prose as ordinary text with no reference.** That is the expected outcome for a fair number of claims and is
not a failure (§5.4).

This is the only place a value is written from a command, and it is the same act as writing the sentence
that cites it — which is what distinguishes it from the update mode §5.2 removes.

### Checking — during `drift`, `check`, and CI

Nothing is written. Every command runs, each result is compared to its recorded value, and three things
can come back:

- **divergence** — `C-002: recorded 4, observed 5`. The code changed and the documents have not caught up.
- **command failure** — the command errored or returned nothing. Usually a file moved; occasionally the
  command was always wrong and nothing had changed enough to reveal it.
- **conformance failure** — a `[C-nnn]` reference with no matching row, a row nothing references, or a
  command that no longer passes static validation. These are defects in the artifact rather than changes
  in the code, and they are reported separately for that reason.

Divergences are findings. They do not fail a build (§5.5).

### Revising — during an update pass

The agent is given the divergences. For each, `Claims:` in subsystem front-matter names the documents that
depend on it, so the work is scoped rather than a re-read of everything. The agent opens those documents,
revises the prose, and **updates the recorded value in the same edit**.

No command does that step. Clearing a divergence requires editing the document, which is the work that
actually needed doing — see §5.2 for why a mode that did it automatically was removed.

### The full loop

```
describe        →  claims file written, prose cites [C-nnn]
     │
     ▼
code changes    →  a number moves; nobody notices yet
     │
     ▼
drift / check   →  "C-002: recorded 4, observed 5"   ← every run, until fixed
     │
     ▼
update pass     →  prose revised + value updated in one edit
     │
     └──────────→  back to checking
```

A divergence nobody acts on is reported again on every run and stays visibly stale. That is intended: the
alternative is a number that quietly stops being true, which is the failure this design exists to remove.

### Summary

| command | claims behaviour | writes? |
|---|---|---|
| `init` | nothing; may set `[claims] enabled` in `archagent.toml` | — |
| `describe` | authors new rows, computes their values, inserts `[C-nnn]` references | yes |
| `drift` | runs every command; divergences appear among drift findings | no |
| `check` | runs every command; divergences reported under their own heading, beneath invariants | no |
| an update pass | revises prose and recorded values together | yes, by editing |

All of it is on by default; `--no-claims` and `[claims] enabled = false` turn it off, and the default
inverts for a target the operator does not control (§5.5).

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

To be precise about what is removed, since values plainly do get written somewhere: **authoring a new
claim computes and records its value**, because that happens inside the act of writing the sentence that
cites it. What is removed is *updating an existing value* — the operation whose whole purpose is to clear
a divergence, and which can therefore be performed without touching the prose the divergence is about.

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

### 5.4 The claims file is executable content — how much that actually matters

**The threat model is milder than it first appears, and the honest statement of it is this:** archagent
normally runs inside, or alongside, an agent session that already has read/write access to the repository
and a shell. In that setting a claim command grants no capability the agent does not already have. An
agent that wanted to do harm has far more direct means, and treating `rg -c '__tablename__'` as the
dangerous part would be security theatre.

So **claim checking runs by default** (§5.5), and the rules below are not the reason it is safe to run.

Two narrower exposures remain, and they are why the rules exist anyway:

- **The non-agentic context.** `archagent drift` in CI is not an agent session. A CI runner holds
  credentials a developer's laptop does not, and there the commands are genuinely new capability sourced
  from repository content.
- **The repository is yours, and the writer is an agent.** A command that is subtly wrong reads exactly
  like one that is not, and the whole point of the file is that nobody re-derives its contents by hand.
  This is a correctness problem before it is a security one.

**Most of what follows earns its place on correctness grounds regardless of the threat model.** Executing
without a shell removes quoting and globbing bugs, not just redirects. A fixed working directory and a
scrubbed environment prevent *false drift*, which is the failure that gets a checker switched off. A cap
on the recorded value stops a runaway command committing a megabyte of output. Read the section that way:
these are the rules that make claim checking reliable, and they happen to also make it defensible in CI.

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

### 5.5 Defaults: on, with an opt-out

**Claim checking runs by default.** A capability that has to be remembered is a capability that does not
run, and the value here is entirely in it running every time rather than when someone thinks of it.

| where | what happens |
|---|---|
| `describe` | writes and updates the claims file; every numeric or enumerable claim it puts in prose gets a row and a `[C-nnn]` reference |
| `drift` | runs every claim command and reports divergences as drift findings — this is the mechanical half of drift the design exists to create |
| `check` | reports divergences alongside invariant results, under their own heading (see the naming note below) |

**Disabling** is `--no-claims` on any of the three, and `[claims] enabled = false` in `archagent.toml`
for a repository that should never do it. Configuration lives in `archagent.toml` rather than in the
artifact, consistent with how the project already splits configuration from described architecture.

**One case where the default flips: a target the operator does not control.** In a non-agentic context —
`archagent drift` in CI — the commands come from repository content and the runner holds credentials.
There, running a claims file the operator has not looked at should require `--claims` explicitly rather
than being the default. This is the one place the mild threat model of §5.4 does not carry.

**A divergence is a finding, not a failure.** It does not exit non-zero by default and does not gate a
build. A number moving because the code changed is the normal case and the expected one; treating it as a
build break would train people to disable the whole thing. A malformed or unsafe *command*, by contrast,
is a conformance failure (§4) — that is a defect in the artifact rather than a change in the code.

### 5.6 A naming collision to resolve before building

archagent already has a `check` command, and it checks **invariants** — the rules constraining the
software. This design has used "`check`" throughout for claim verification, which constrains the
**documentation**, and §2 exists precisely because those two are easy to confuse.

Do not add a second top-level command. Claim results belong inside the existing surfaces:

- `archagent check` gains a **Claims** section beneath its invariant results;
- `archagent drift` reports claim divergences among its findings, which is where they most belong;
- `--no-claims` suppresses that section in both.

Within this document, "`check`" continues to mean the claim-verification operation because the design
reads better that way. **In the implementation and in user-facing output it must not.** The word to use
with a reader is *claim divergence*.

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

### The drift justification did not survive its own experiment (2026-08-16)

`docs/evaluations/claims/RESULTS-drift.md`. Real later history — wardrowbe v1.7.0 → v1.8.0, 21 commits, 95
files — with the artifact and the claims file both fixed beforehand.

**`drift` caught 3 of 8 staleness items. The claims file caught 0.**

The reason is structural, and it is this design's own doing. The predicate redesign removed value
comparison, which is exactly the capability that would have caught the counts that moved (routes 104→106,
migrations 22→26, tests 401→470). It was removed for a good reason — those three are precisely the trivia
that trains people to ignore a checker — but the consequence has to be stated: **§1's claim that this
"makes much of the drift computation mechanical" is not supported.** Compare values and you detect drift
that is mostly trivia; do not compare them and you detect no value drift at all. Neither version of this
design resolves that.

**One narrower justification does survive, and should replace the broad one.** A post-hoc check confirmed
that a `set` claim over the settings fields would have caught the release's two new config keys — and
`drift` structurally cannot, because pydantic-settings resolves field names to environment keys at
runtime. Run 1's own `drift` output contains 56 "dangling config" findings that are all this false
positive. So: **a claims file earns its place where it covers a closed collection archagent's static
analysis cannot see.** That is a real gap, already documented in the artifacts as a tool limitation, and
nothing else fills it. It is much narrower than "drift becomes mechanical", and it points at the same
targets §3's evidence does — repositories in languages the tool cannot parse.

**And the boundary is worth recording once, plainly.** The most consequential staleness in the release was
the stale-item sweep being rewritten from a blind time-based condemn to a Redis job-state check — inside a
file that did not move, changing no declaration and no count the artifact asserts. It is invisible to
`drift`, to computed claims, to the recurrence suite and to the checklist. **Every mechanical instrument
this project has built would report that artifact as clean.** That is not an argument against any of them.
It is the boundary of the whole approach, and it is why §14's judged checklists and the calibration rounds
are not optional extras.

### The blind-spot case holds, tested where it should bite (2026-08-16)

`docs/evaluations/claims/RESULTS-obstudio-drift.md`. obstudio declares `python` and `typescript`, so its
entire Go codebase is outside archagent's static analysis. Real history, `88aebe8` → `17797b9`: two
commits adding a fifth `obstudio install` target.

**`drift`'s output was byte-identical before and after. The claims file caught it**, naming `windsurf` as
the missing member and the three documents that assert the old set — a table, a command line, and a
sentence in the constitution.

**The coverage number is the stronger result, and it does not depend on the change at all: `drift` can
check 0 of the 16 Go closed collections the artifact asserts.** Not few — none. And its 22 findings on this
target are all false positives *that the artifact itself predicts*, because the empty Go import graph
cannot confirm any declared edge. On obstudio a claims file is not an improvement on `drift`; it is the
only mechanical check that functions.

Disclosed: the fifteen other claims predate this diff, the install-target claim does not. So this
demonstrates the mechanism on the class rather than estimating a rate, and the coverage figure is the part
that is independent of the change.

### What the evidence now supports, which is narrower than §1

Taking steps 1–3 and both drift experiments together:

- **`set` claims over closed collections are the load-bearing kind.** They caught the defects in step 1,
  they caught this, and they are the only kind that has caught anything no reader found first.
- **The value proposition is coverage of blind spots, not drift in general.** Where archagent parses the
  language, `drift` already does the structural work and the value drift claims would add is mostly the
  trivia this design's own rule says not to write. Where it does not parse the language, a claims file is
  the only mechanical check available.
- **That suggests a cheaper shape than the full design.** Rather than claims for everything, a claims file
  scoped to *the part of the system archagent cannot see* — which `describe` already has to identify, and
  which obstudio's artifact already documents in a dedicated section.

## 9. Status

**Proposed. Not accepted.** The next action is step 1, which is cheap and can retire the idea before any
further cost.

This document is kept whatever the outcome. If the change is rejected the status becomes `rejected`, the
measurements are recorded here, and the reasoning stays on file — a rejected design with evidence is worth
more than a silence someone re-derives in six months.

| Step | Result |
|---|---|
| 1 — retrospective divergence count | **8, against a predicted 17 — gate not met** |
| 1 — facts left uncomputed under the safety rules | 22 of 56 (39%), none refused *by* the rules |
| 1 (predicates) — named defects caught | **12 of 12 predicted, plus 1 not predicted — gate passed** |
| 1 (predicates) — authoring error rate | 7 of 35 commands (20%), down from 27% |
| 2 — generation variance | **bounded at 1 checklist item in 16 — step 3 can proceed** |
| 3 — two arms | **not run: instrument saturated, baseline nearly clean** |
| drift experiment (wardrowbe) | **run: `drift` 3 of 8, claims 0 of 8 — the broad drift claim is not supported** |
| drift experiment (obstudio) | **run: `drift` 0 of 1 and byte-identical, claims caught it — the blind-spot case holds** |

### Step 3: blocked on an instrument ceiling, not on the design (2026-08-16)

Both step-2 instrument defects are fixed — conditional checklist items now score `absent` as a pass, and a
guard flags recurrence entries whose `require` patterns split one obligation. Fixing the first changes the
arm-A baseline: the three current-ADL artifacts score **1.00, 1.00 and 0.94** on the wardrowbe checklist.

The pre-registered gate needed five items to move. **At most one can.** Two arms cannot be separated by
five items when one is already at sixteen of sixteen, so step 3 was not run —
`docs/evaluations/claims/RESULTS-step3.md`.

Rather than assume there was nothing to find, the headroom was measured directly: fifteen predicate claims
written against a freshly generated artifact's own assertions. **Fourteen hold; one is false**, and it is
exactly the targeted class — *"the only place a third-party API is called: the OpenAI-compatible model
endpoints and Open-Meteo"*, where the code also calls `nominatim.openstreetmap.org` and `exp.host`. An
exhaustiveness claim with two members missing.

So the mechanism works and the baseline is ~1 false assertion in 15. At that rate, three artifacts per arm
gives about 3 defects against 0 — Fisher exact p ≈ 0.24. **Detecting the effect needs roughly ten times the
sample**, which is not what step 3 was scoped to.

Two honest ways forward, neither of which is "run it anyway":

- **The drift experiment.** The claim that a claims file makes drift mechanical has never been tested, and
  §16's machinery has never run. It is cheap, needs no generation, and covers the half of this proposal
  that is not about accuracy.
- **Two arms on obstudio**, whose checklist baseline is 0.24 and which archagent cannot analyse statically
  at all. A repository the tool is *bad* at is where grounding claims in commands should pay — and it also
  satisfies §18 better, since obstudio is not the repository whose defects shaped this design most.

### Step 2: generation variance (2026-08-16)

Three independent generations of the wardrowbe artifact, same model, prompt and revision, each in its own
copy with the prior artifact removed first. Method fixed in advance in
`docs/evaluations/claims/STEP2-METHOD.md`; results in `RESULTS-step2.md`.

**Generation variance is no larger than judging variance.** Three independently generated artifacts differ
on **one checklist item of sixteen** — the same magnitude as two judges reading one artifact. And both
judges who scored that item `correct` flagged it, unprompted, as a borderline call on the
`wrong`/`absent` boundary, so the single difference in the whole measurement may be the judge rather than
the artifact. Generation variance is bounded above by 1 in 16 and may be smaller.

**The deterministic rubric cannot see generation variance at all.** 0.889 / 0.888 / 0.888, from artifacts
carving the system into 18, 17 and 14 subsystems, with 56 / 48 / 28 invariant rows. It measures
conformance, all three conform, and it was never built to rank two conforming artifacts. **It must not be
the score in a two-arm comparison**; it is a gate, and the checklist is the measure.

**All three regenerated artifacts clear all 10 recurrence entries, where the original fails all 10**, and
score 0.81–0.88 on the checklist against the original's 0.12. The original failing everything is
arithmetic — the entries were written from its defects. The other side is not: three artifacts produced by
a different route get 13–14 of 16 right on questions written from another artifact's mistakes, including
all four `serious` items the original got wrong and both ownership items, the gap four reviewers named as
its largest.

Two instrument defects surfaced. A recurrence entry demanded both word orders of the same pair as separate
`require` patterns, which means "all must match" and reported an artifact that covers ownership properly as
silent on it — the second entry defect on record, both crying wolf. And the checklist scores an `absent` on
a *conditional* item as a miss, so an artifact that sensibly declines to state an incidental count is
penalised for it. That has to be fixed before step 3, or the arm following this design's own advice about
incidental counts is marked down for taking it.

### Second attempt, with predicate claims (2026-08-16)

The redesign — claims as predicates over closed sets and properties, never magnitudes — was
pre-registered in `docs/evaluations/claims/PREREGISTRATION-2.md` with the 12 defects it should catch named
individually, and the gate set at 10 of 12 by name rather than by count. Results:
`docs/evaluations/claims/RESULTS-2.md`.

**All 12 were caught, each by the claim and kind predicted for it**, plus one that was predicted *not* to
be: the artifact citing the wrong file for the UI embed. Written as a `holds` claim it fails outright,
because forcing an assertion into a form a command can refute is itself the mechanism — a mis-attribution
does not need a prose-to-claim comparison after all. Thirteen of the 28 recorded defects are now reachable,
against eight under the value-based design.

**The authoring error rate fell from 27% to 20%**, and the residue is instructive. `absent` and `holds`
removed the *reproduce an exact figure* class entirely; what remains is **scoping** — a command that looks
in the right place and takes in more than the claim covers, like sweeping three enums where one was meant.
That class does not go away with a different claim kind, and in production those errors would still be
silent. Five of the seven are visible on sight once the command's *output* sits next to the claim, which
settles that recording output is a requirement rather than a nicety.

**Two prototype defects surfaced that no test had caught**, both in the safety layer and both would have
shipped: a URL prefix (`/api/validation/`) refused as an absolute path — and it was the `absent` claim for
the most valuable finding — and the output cap making broad `absent` claims unrunnable, because a failing
`absent` claim legitimately produces a lot of output and only its emptiness matters. The cap belongs where
evidence is recorded, not where the command runs.

**What stays out of reach is unchanged**: omissions, presentation, judgements, and the incidental counts
this design deliberately stops treating as claims. Both security findings in this project's history are
omissions, and no version of this mechanism reaches them.

**Step 1 ran on 2026-08-16 and the pre-registered gate was not met.** Full write-up:
`docs/evaluations/claims/RESULTS.md`. Three results decide what happens next.

**The count fell short because §3 asked the wrong question.** Its classification — *could a deterministic
command settle this fact?* — was right about 17 of 28 defects. But a claims table only catches a defect
when the artifact **commits to a value**, and most of those 17 were stated as prose behaviour: "logs
rather than raises", "falls back to local auth", a diagram edge, *which* file embeds the UI. The mechanism
as designed asks whether a recorded number still holds; most fabricated claims are not numbers.

**The design that would reach them is a different one: a claim as a predicate rather than a value** — 
"`validate_security` raises", settled by a command's exit status. That needs its own prediction before
anything is built, not a reinterpretation of this one.

**The safety rules turned out to be nearly free.** Exactly one command was ever refused by static
validation, and rewriting it took seconds. The 22 uncomputed facts were beyond *any* command — import
graphs, properties of every code path, reasons, hedges — not beyond the allowlist. That question is
settled favourably and does not need revisiting.

**The real risk was measured, and it is worse than the yield.** Of 37 commands written, **ten measured
something other than what the prose meant** — counting `.d.ts` files, counting volume names as compose
services, counting `os.Getenv` inside `_test.go`. In this retrospective those errors were loud, because
the recorded value came from the prose. **In production they would be silent**, because the recorded value
comes from the command: a command measuring the wrong thing records a plausible number, agrees with itself
forever, and lends a fabricated claim the appearance of verification. §5.1 named this; step 1 measured it
at 27% of first attempts. Storing the command's *output* rather than a bare count would have caught about
half, and should be a requirement in anything built from this design.

**Two findings argue the other way.** Two of the eight divergences had never been found — by four
reviewers across two calibration rounds and eight checklist judgings. `skills/` ships nine skills where an
invariant's rationale says eight; `k8s/` holds eleven manifests where `deployment.md` enumerates ten. Both
cost seconds and no judge, and both are the kind of small factual error a reviewer's attention never
reaches.

### Revisions

- **2026-08-16** — `regenerate` removed (§5.2); the safety rules written out as five defences with the
  governing rule *prefer an uncomputed claim to an unsafe command* (§5.4); ESAA read and cited.
- **2026-08-16** — workflow section added at the top: what runs during authoring, checking and revising,
  and the distinction that authoring computes a new claim's value while nothing recomputes an existing one.
- **2026-08-16** — threat model corrected (§5.4): archagent normally runs where an agent already has a
  shell and write access, so claim commands grant no new capability and the rules stand on correctness
  grounds rather than security ones. Claim checking therefore runs **by default** in `describe`, `drift`
  and `check`, with `--no-claims` and a config key to disable, and the default inverted for a target the
  operator does not control (§5.5). Naming collision with the existing `check` command recorded (§5.6).

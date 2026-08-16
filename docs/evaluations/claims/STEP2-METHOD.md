# Step 2 — generation variance: method, fixed before the results

Written and committed while the three generation runs were still in flight, so the scoring plan is not
chosen with the numbers visible.

## The question

Everything measured so far holds the artifact fixed and varies the judging. The judge noise floor
(`../noise-floor/RESULTS.md`) is the spread of six judgings of *one* artifact; the checklist agreement
figures are two judges reading *one* artifact. **None of it says how much two artifacts of the same
repository differ when nothing but the run varies.**

That number is the prerequisite for step 3, because an ADL change forces regeneration. A two-arm
comparison is unreadable without it: a difference between arms means nothing until you know how much two
runs of the *same* arm differ.

`scripts/selfeval.py` has said so since it was written — its docstring gives this as the reason the
end-to-end loop is deliberately unfinished: *"how much of the score is agent variance rather than artifact
quality. Until a repeat run on identical inputs establishes that noise floor, comparing two scorecards
would be reading tea leaves."*

## Setup

Target: **wardrowbe @ `wardrowbe-v1.7.0`** (`eda843f`) — the only target with all four instruments
(deterministic rubric, checklist, recurrence suite, judged rubric).

Three independent copies of the checkout at `~/.cache/archagent/variance/run-{1,2,3}`, each with:

- **the existing artifact removed before the copy was made.** The canonical copy is archived in the data
  repo, and `diff -rq` confirmed the checkout's copy was identical to it before removal. An agent that
  found the old artifact would copy it, and the measurement would read as near-zero variance.
- `archagent init --yes --agents none` run to scaffold empty templates — the real starting state.
- an instruction not to read the other runs, the archived artifact, or `archagent/docs/`, which holds the
  reviews and defect lists for this exact repository.

Same model (Opus) for all three, same prompt, same revision. Only the run varies.

## What gets measured, decided now

1. **Deterministic score** — `selfeval.py score` on each. Spread of the three.
2. **Structure** — subsystem count, which subsystems each run chose, prose words per file, diagrams,
   invariant rows. Two runs can score the same and carve the system differently, and *that* is the
   variance that matters for a two-arm comparison.
3. **Recurrence suite** — the 10 wardrowbe entries against each artifact. These are facts about the
   target, so they apply to any artifact of it. A regenerated artifact should fail *fewer* than the
   original, which failed all 10 by construction.
4. **Checklist** — the 16 items, one blind Opus judge per artifact. Same worksheet, three artifacts.
5. **Judged rubric** — not run. Six judgings of one artifact already cost ~470k tokens, and the mean is
   the only stable part of it; the checklist is the better instrument and is already validated at 94%
   between judges.

## How the result will be read

- **The headline is the spread of the deterministic score and of the checklist score across three runs.**
- A spread comparable to the judge floor (±0.10 on the rubric mean) means generation is not the dominant
  noise source and step 3 can proceed with the arm sizes already planned.
- A spread several times larger means a two-arm comparison on N targets is underpowered, and step 3 needs
  either more targets, replicates per arm, or a paired per-item design rather than a score comparison.
- **Structural divergence is reported whatever the scores do.** Three runs agreeing on a number while
  disagreeing on how many subsystems the system has is a finding about the instrument, not about the tool.

## What this cannot answer

One target, one model, three runs. It bounds generation variance for this repository under this prompt at
this revision, and nothing wider. Whether a smaller or messier repository varies more is a separate
measurement, and the checklist and recurrence entries used here were written from an *earlier* artifact of
the same target, so they are enriched for that artifact's failure modes rather than neutral.

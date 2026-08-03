# Judged rubric, calibration round 1 (2026-08-02) — archagent reviewing its own artifact

The first completed run of the judged half (`docs/designs/evaluating-archagent.md` §9): six criteria over
`docs/architecture/`, scored by a reviewer other than the artifact's author. It was meant to calibrate the
rubric against a human. It did that, but the larger result is about the harness: **two of the rubric's
three defences did not work, and the way they failed produced a plausible-looking number.**

## What the harness reported before the fixes

    accuracy               discarded: no file:line citation
    completeness      2/5
    prose                  discarded: no file:line citation
    diagrams               discarded: no file:line citation
    invariant_strength     discarded: no file:line citation
    invariant_criticality  discarded: no file:line citation

    mean: 2.0

The reviewer's own summary table said 3.0. The harness said 2.0 and gave no indication it was averaging a
single criterion out of six. This is the silent-failure class the corpus work already ran into twice: the
output is not an error, it is a well-formed low score, and a low score on an architecture artifact is
exactly what one half-expects to see.

## Failure 1 — fields were read one line at a time

`parse_brief` matched `^\s*why\s*:\s*(.*)$`, so a field ended at its newline. The reviewer wrote a summary
sentence after `why:` and then the claim-by-claim evidence — every citation in the review — indented
beneath it. All of it was discarded before the citation rule ran. The citation rule then found no
`file:line` in the surviving sentence and threw the score away as unevidenced.

So the most thoroughly cited review received was rejected *for having no citations*. Fields now run to the
next `score:`/`evidence:`/`why:` key, and the brief says so, since a reviewer had no way to guess the
constraint from the template.

With that fixed the mean is 3.0 — matching the reviewer's own arithmetic, which is the check that the
parser is now reading what was written.

## Failure 2 — the citation rule checked form, not truth

This is the more interesting one. The rule asked whether a `file:line` was *present*. A fabricated
citation is present in exactly the same way a real one is, and fabrication is the specific hazard here:
an artifact review is mostly unfalsifiable prose, which is what a language model generates most readily.

Verifying by hand, four citations in `accuracy` point at nothing:

| citation | reality |
|---|---|
| `src/archagent/check.py` line 1593–1594 | the file is 248 lines |
| `src/archagent/__init__.py` line 22, 25 | the file is 5 lines |
| `src/archagent/invscan.py` line 266 | the file is 122 lines |
| `docs/architecture/decisions/0003-cycle-breaker.md` | no such file; the ADR is `0003-drift-holds-shared-git-plumbing.md` |

And the substance was wrong wherever it was checkable:

- **"`cli.md` says `check.py` is leaf-only"** — `cli.md` never mentions `check.py`. No document in the
  artifact claims it. The quoted imports (`load_config`, `read_invariants_table`) are not its imports
  either; they are `Config`, `Invariant`, `parse_property`. The finding, its evidence and its citation
  were all invented.
- **"`generate.py` and `rules.py` have zero coverage"**, driving the `completeness` score of 2, with the
  supporting cite *"`invariant-pipeline.md` exists but never names `generate.py` or the DSL"*. That
  document names both in its `**Covers:**` line, gives each a row in its module table, and puts both in
  its sequence diagram. The cite asserts the negative of what the cited line says.

`unresolved_citations` now resolves every citation against the tree — the path must exist, the line must
be within the file — and a criterion whose citations all fail is discarded like an uncited one. Run
against this review it flags those four and nothing else. A bare basename that matches in several places
resolves if any candidate supports it: vagueness is not fabrication, and conflating them would make the
check untrustworthy in the direction that matters.

This does not catch a citation that resolves but does not support the claim — the `invariant-pipeline.md`
case above. Nothing mechanical will. It removes the cheapest fabrication, which is the one that occurred
here in four of five instances.

## Failure 3 — a mean over the surviving fragment looked like a mean

Nothing distinguished "2.0 across six criteria" from "2.0 from the one criterion that parsed". The record
now carries `scored`/`answered`, the caveat states the ratio in words, and the CLI prints
`NOT A SCORE OF THE ARTIFACT` when any criterion was discarded.

## What survived: the one real defect

ADR 0003 stated that `invscan.py` *and* `connscan.py` both import `drift`, closing the `drift ↔ extraction`
cycle. Only `invscan.py:24` does; `connscan.py` imports `configscan` alone. The cycle is real and the ADR's
argument is unaffected, but it named a module that is not part of it. Corrected.

The organisational criticisms also hold up and needed no citation to verify: `index.md` opened with a note
about `architecture_dir` — configuration trivia as the first thing a reader meets — offered no statement
of what the tool does, no reading order, and no account of how ADRs relate to invariants. All three are
now in the index and the config note has moved to the bottom.

## Postscript (2026-08-02): the qualitative findings, once acted on

The organisational criticisms were treated as sound because they needed no citation to verify, and the
generation prompts and `index.md` were corrected on that basis. Working through the two filed as issues
sharpened the picture, and it cuts the same way as everything above.

**#5 (abstractions named before grounding) held on all three counts.** `evaluate.md` used "groups A–F" in
its opening sentence, its CLI flag and its report without ever enumerating them; `extraction.md` said what
each scanner extracts but never what one returns; `invariant-pipeline.md` had no worked example. All three
are fixed with concrete instances rather than more prose. Worth noting against my own reliability: two of
the examples I first wrote were *also* wrong when checked — `read_config_keys` returns a bare `set[str]`
with no file map, and `Route` carries the source file rather than a handler. Writing a grounded example is
where the checking happens; that is the argument for grounding them.

**#4 (decorative captions) did not hold.** All five existing captions already state a takeaway rather than
naming the diagram, and the finding-lifecycle state diagram it called missing was already in `evaluate.md`.
The one real gap was the one the review misdescribed: it reported `drift.md` as having a decorative
dependency graph, and `drift.md` had no diagram at all.

So the pattern extends past the citations. The review's *scores* on the artifact-readable criteria were
defensible, and its *specific claims about which file contained what* were unchecked whether or not they
carried a resolvable citation — including in the criteria that scored well. Resolving citations catches
the invented path; it does not catch a true path attached to a false claim about its contents, and the
`diagrams` criterion is where that showed up.

The one incidental find: writing the drift caption surfaced a hardcoded `architecture/` in the drift
header, printing a path that exists on no repo configuring `architecture_dir`. Neither the review nor any
check found it. Describing a thing carefully still finds more than grading it does.

## Second scoring pass (2026-08-02, `71ec378`) — and why 1.0 is not good news

The deterministic scorecard now reads **1.0**, up from 0.963. Two things about that, in the order that
matters.

**I changed the rubric, and the change raised my own score.** `check_evaluate_coverage` counted every
inactive `evaluate` family against the artifact. Two of the families it was charging archagent for cannot
be activated by any edit to any document: family E is inactive when no bug-fix commit convention can be
learned from the git history, and family A needs `**Service:**` on two subsystems when this repo is a
single process with no services at all. The check claimed to measure whether the *artifact* was
under-specified and was partly measuring the *repository*. Fixing it moved the score from 0.963 to 1.0.

That is precisely the §13.3 hazard — a criterion becomes a target once someone optimises against it — with
the twist that here the optimiser and the rubric author are the same. The reasoning holds on its merits
(the alternative fix was to declare fictional services in `deployment.md`, which is writing a false
document to raise a score) but the conflict of interest is real and the change should be read with it in
view. Mitigations: excused families are named in the output rather than dropped, so "not applicable here"
never reads as "measured and fine"; families B and B/C stay counted because a missing `**Tier:**` or
`**Connects:**` genuinely is an under-specified artifact; and a test asserts a repo that *does* ship a
`docker-compose.yml` still gets charged for family A.

**A perfect deterministic score mostly means the deterministic half has run out of things to say.** Eight
of nine checks were already at ceiling before any of the last three days' work. Between the first pass and
this one the artifact gained five invariants, a system map, an entry narrative, three worked examples and
a flowchart for its central subsystem — and the score moved 0.037, all of it from the rubric change rather
than from the artifact. `check_specificity` could not see the five new rules at all, because
`CATEGORY_CAP` caps any one category at half the target and invariants were already at the cap.

So the number is now useless as a progress signal for this artifact, which is an argument for the judged
half rather than a complaint about the deterministic one. It is doing its actual job — it is a floor, not
a ranking.

## What this says about the scores

**Nothing yet.** 3.0 is one review by one reviewer whose evidence was wrong in every instance it was
checked. That is not agreement data; it is a demonstration that the rubric could not previously tell a
grounded review from an ungrounded one. The criteria remain uncalibrated and gate nothing (§13.2).

The findings calibration (`docs/evaluations/labels/CALIBRATION.md`) reached 68% agreement and concluded *a
verdict reached from the finding's summary is not a verdict*. The same rule turns out to hold one level
up: **a score reached from the documents alone is not a score.** Four of six criteria here are answerable
from the artifact text, and those scored 3–4 with no fabricated citations. The two that require opening
the code — `accuracy` and `completeness` — are exactly the two that were fabricated, and they are the two
lowest scores in the set.

## Limits

- One reviewer, one artifact, six criteria — no agreement rate can be computed from a single review.
- The artifact is archagent's own, which is the easiest case for me to check and the least
  representative: I already knew where the bodies were, which is why the fabrications were visible at all.
- Round 2 needs a reviewer scoring a repository neither of us wrote, with the resolution check active
  during the review rather than after it.

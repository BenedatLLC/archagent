# Evaluation write-ups

The reasoning lives here; **the data lives in
[BenedatLLC/archagent-evaluations](https://github.com/BenedatLLC/archagent-evaluations)** (private).

The split is by kind, not by size. Numbers without their reasoning are unreadable, and a write-up split
from its evidence is untrustworthy — so each document below states its conclusions and cites the data repo
by path. Clone the two side by side and the citations resolve:

```
code/
├── archagent/                 # the tool, and these write-ups
└── archagent-evaluations/     # flagged sets, labels, worksheets, artifact snapshots
```

Evaluation data was previously committed here and moved out on 2026-08-02, because it grows without bound:
every defect-study run adds per-repo flagged-file dumps, and every calibration round adds a whole generated
artifact. The archagent test suite does not read it — all tests pass with the data repo absent.

| Document | What it concludes |
|---|---|
| [`defect-study/RESULTS.md`](defect-study/RESULTS.md) | Files flagged change-prone-and-complex accumulate significantly more defect-fixing commits than churn-matched controls, in 3 of 4 adequately powered repositories. Pre-registered; every deviation recorded. Magnitudes are **not** comparable across repositories. |
| [`usertest/ROUND-2.md`](usertest/ROUND-2.md) | rc2, and the first round where the documentation was actually read. Ease **3**, correctness **2**, completeness **4**, impact **3** — **not a series with round 1**, which the ledger refuses on two comparability keys. Six defects verified, including a `finding_id` that collides for every finding without a value set and `TYPE_CHECKING` imports counted as runtime edges. The round 1 fixes held. |
| [`usertest/ROUND-1.md`](usertest/ROUND-1.md) | The first round to ask whether someone can install the tool and get a result at all. Ease of use **2**, correctness **1**, completeness **2**, impact **2** — never averaged, n=1. Three defects verified against the source (#33, #34, #35); one tester claim checked and found wrong. **The tester could not reach the pinned docs**, so this round did not measure the question it asked — recorded as a comparability key, not a footnote. The `init` source-path guard was the single best-rated thing in the tool. |
| [`selfeval/dspy/CALIBRATION.md`](selfeval/dspy/CALIBRATION.md) | Round 5, artifact **and** findings on a fresh target. Artifact 3.0, evaluate report 3.0. The new result is the impact distribution: **11 of 19 sampled findings are noise** — 6 describe nothing real, 5 are true and not worth acting on — and none reached critical. Also cost four archagent bugs, three found before a human read anything. |
| [`labels/CALIBRATION-3.md`](labels/CALIBRATION-3.md) | Findings, round 3 — wardrowbe. `layer-inversion`'s four dismissals across three repos are **all** test or migration packages, with three of three confirms on production code. `unstable-interface` 0 of 3, and the pre-registered confound is **not** resolved. |
| [`labels/CALIBRATION-2.md`](labels/CALIBRATION-2.md) | Findings, round 2 — groups B and C, labelled for the first time. **Not one of the 14 measurements was disputed**; every error was in the judgement, not the extraction. `layer-skip` 0 of 3 with a single shared cause, since fixed. |
| [`labels/CALIBRATION.md`](labels/CALIBRATION.md) | Findings, round 1. 68% agreement between an independent reviewer and the person who built the checks, with errors in **both** directions. Precision by signal, with intervals. |
| [`selfeval/archagent/CALIBRATION.md`](selfeval/archagent/CALIBRATION.md) | Judged rubric, round 1. The instrument broke three ways before it measured anything, and the review's evidence was fabricated wherever it was checkable. |
| [`selfeval/obstudio/README.md`](selfeval/obstudio/README.md) | Judged rubric, round 2 setup: a Go-majority repo neither of us wrote, and the three archagent bugs running on it exposed. |
| [`spotcheck/worksheet-2026-08-01-item-12-explanation.md`](spotcheck/worksheet-2026-08-01-item-12-explanation.md) | The worked example of what a finding write-up should look like — litellm's drifted `CallTypes` vocabulary leaving a security hook scanning nothing and reporting success. |

## Evaluating `evaluate` as well as the artifact

Every describe evaluation from 2026-08-22 also captures `evaluate` output and runs four judge-free checks
over it (design §22). The capture is not optional housekeeping: the history signals are computed from the
git log as it stood, so a run that does not record its findings cannot get them back, and every round
before this one discarded them.

Three signals of roughly twenty have ever been checked against anything outside our own judgement —
`change-prone-file` by the defect study, `scattered-source-of-truth` and `enum-value-escape` by the first
spot-check round. Groups A, B, C and D have none. The capture does not fix that; it makes the data to fix
it accumulate by default rather than requiring a fresh expedition.

The three judged criteria added to the review brief ask about the **report** — is it actionable, is it
restrained about what it established, is it clear about what never ran. They deliberately do not ask
whether a finding is true, because the brief shows the reviewer every severity, and that question asked
in the open measures agreement with our own prior. It stays in the blinded spot-check.

## What lives where

**Code and conclusions here; measurements there.** The rule is one question:

> Does this file change when **archagent** changes, or when the **target repo** changes?

A regression baseline changes when the tool's behaviour changes — it is an assertion about archagent, so
it belongs beside archagent. A flagged-file set changes when litellm gets a new commit — it is a
measurement of someone else's repository, so it belongs in the data repo.

| Kind | Where | Why |
|---|---|---|
| Harness modules (`tests/rubric.py`, `rubric_judged.py`, `findings.py`, `defect_study.py`, `corpus.py`, `spotcheck.py`, `blindcomp.py`) | archagent | code |
| Runner CLIs (`scripts/*.py`) | archagent | code |
| The reviewer brief a judge fills in (`render_brief`) | archagent | it is the instrument, generated fresh per run |
| Manifests pinning what to run (`tests/*_manifest.toml`, `blindcomp_truth.toml`) | archagent | inputs, versioned with the code that reads them |
| **Regression baselines** (`tests/corpus/*.json`, `tests/golden/*.json`) | archagent | the awkward case: they *are* recorded `evaluate` output, but their job is "fail if archagent's behaviour changes". They move when the tool moves. |
| These write-ups | archagent | conclusions, useless without the reasoning around them |
| Flagged sets, outcome measurements, labels, worksheets, completed reviews, generated artifact snapshots, scorecards, **`evaluate` captures** | archagent-evaluations | measurements of target repositories |

Nothing evaluation-related ships in the wheel: neither `scripts/` nor the harness modules are installed by
`pip install archagent`.

## Where scripts write

`scripts/selfeval.py`, `defect_study.py`, `spotcheck.py` and `blindcomp.py` resolve their output root in
this order:

1. `$ARCHAGENT_EVAL_HOME`
2. `../archagent-evaluations/` if that checkout exists
3. `./evaluations/` — a gitignored local working area

So a fresh clone with no data repo still runs; it just keeps its output out of git.

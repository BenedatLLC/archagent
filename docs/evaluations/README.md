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
| [`labels/CALIBRATION.md`](labels/CALIBRATION.md) | Findings, round 1. 68% agreement between an independent reviewer and the person who built the checks, with errors in **both** directions. Precision by signal, with intervals. |
| [`selfeval/archagent/CALIBRATION.md`](selfeval/archagent/CALIBRATION.md) | Judged rubric, round 1. The instrument broke three ways before it measured anything, and the review's evidence was fabricated wherever it was checkable. |
| [`selfeval/obstudio/README.md`](selfeval/obstudio/README.md) | Judged rubric, round 2 setup: a Go-majority repo neither of us wrote, and the three archagent bugs running on it exposed. |
| [`spotcheck/worksheet-2026-08-01-item-12-explanation.md`](spotcheck/worksheet-2026-08-01-item-12-explanation.md) | The worked example of what a finding write-up should look like — litellm's drifted `CallTypes` vocabulary leaving a security hook scanning nothing and reporting success. |

## Where scripts write

`scripts/selfeval.py`, `defect_study.py`, `spotcheck.py` and `blindcomp.py` resolve their output root in
this order:

1. `$ARCHAGENT_EVAL_HOME`
2. `../archagent-evaluations/` if that checkout exists
3. `./evaluations/` — a gitignored local working area

So a fresh clone with no data repo still runs; it just keeps its output out of git.

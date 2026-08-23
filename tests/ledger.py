"""The evaluation ledger (`docs/designs/evaluating-archagent.md` §17).

One CSV, one row per evaluation run, in the evaluation data repository. Without it every round informs the
next only through whoever remembers it, which is how three rounds of expensive review have been run so far.

**The scores are the least interesting columns.** What decides whether two rows can be compared at all are
the inputs: which model generated the artifact, which model judged it, and which version of the rubric it
was judged against. The first two calibration rounds used different review briefs, so their means were
never comparable — and nothing recorded that, which is the specific mistake this file exists to make
impossible to repeat.

So the ledger does one thing beyond storing rows: **it refuses to compare rows that are not comparable**,
and says which key differs. A ledger that silently averages a 4-criterion brief with a 6-criterion one
produces a number that looks like a trend and is an artifact of the schema. That is the same failure shape
as `check` printing "All invariants hold" having checked none of them.

A row whose comparability keys are unknown is still stored — the historical runs genuinely did not record
their model or brief version, and deleting that history would be worse than marking it. It is excluded
from comparisons and reported as excluded, never silently dropped.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

#: Values meaning "this was never recorded". Distinct from empty, which means "not applicable to this
#: kind of run" — a scoring run has no human reviewer, and that is not the same as having lost the record.
UNKNOWN = {"unknown", "?"}

#: Differ on any of these and two rows are measuring different things. This is the whole point of the file.
#:
#: These are the keys for metrics about the **artifact** — what a describe run produced. The generating
#: model dominates, and `archagent_commit` is recorded but deliberately does not gate: an artifact is the
#: model's output, and the tool that scored it afterwards does not change what the model wrote.
COMPARABILITY_KEYS = ("rubric_version", "judge_model", "generating_model")

#: And these are the keys for metrics about **`evaluate` output**, where the asymmetry runs the other way.
#: Findings are the *tool's* output, so the archagent build gates a comparison exactly as the generating
#: model gates an artifact comparison — a changed threshold or a new signal makes two finding sets
#: incomparable with identical models on both sides. Meanwhile the artifact's rubric version is irrelevant
#: to them, so gating on it would refuse sound comparisons.
FINDINGS_KEYS = ("evaluate_rubric_version", "judge_model", "archagent_commit")

#: Which key set governs which metric. There is no default on purpose. A metric absent from this table is
#: one nobody has decided the comparability of, and quietly comparing it under the artifact keys is the
#: precise mistake the whole file exists to prevent — it is how three calibration means across three
#: different briefs came to look like a rising line.
METRIC_KEYS: dict[str, tuple[str, ...]] = {
    "judged_mean": COMPARABILITY_KEYS,
    "deterministic_score": COMPARABILITY_KEYS,
    "checklist_correct": COMPARABILITY_KEYS,
    "checklist_wrong": COMPARABILITY_KEYS,
    "checklist_absent": COMPARABILITY_KEYS,
    "recurrence_pass": COMPARABILITY_KEYS,
    "evaluate_mean": FINDINGS_KEYS,
    "findings_count": FINDINGS_KEYS,
    # Precision is a property of the findings, so the archagent build gates it: a retired or rescoped
    # signal changes what the population even contains. Round 1 and round 2 differ on it and are
    # correctly not a series.
    "precision_confirmed": FINDINGS_KEYS,
    "precision_n": FINDINGS_KEYS,
}


def keys_for(metric: str) -> tuple[str, ...]:
    """The comparability keys governing one metric, or a refusal naming it.

    Raising beats guessing. The cost of the error this prevents is a number that looks like a finding,
    and the cost of the refusal is one line added to `METRIC_KEYS` by whoever knows what the new metric
    measures — which is the person adding it, at the moment they know.
    """
    try:
        return METRIC_KEYS[metric]
    except KeyError:
        raise ValueError(
            f"no comparability keys declared for metric {metric!r}. Add it to METRIC_KEYS: use "
            f"COMPARABILITY_KEYS if it scores the artifact, FINDINGS_KEYS if it scores `evaluate` "
            f"output. Comparing it under a guess is how an artifact of the table becomes a trend."
        ) from None


@dataclass
class Row:
    run_id: str                      # primary key; date-target-what, readable on sight
    date: str                        # ISO
    archagent_commit: str            # the archagent that GENERATED the artifact
    target_url: str
    target_commit: str               # a target is a repository *at a revision*, never a repository
    target_fresh: str                # yes / no — had this target ever been used before?
    run_kind: str                    # calibration | scoring | noise-floor | checklist
    #: The archagent the REVIEW ran against, when it is not the one that generated. Separate from
    #: `archagent_commit` for the same reason `judge_model` is separate from `generating_model`: they are
    #: two different tools doing two different jobs, and round 4 used two builds six weeks apart while
    #: recording one.
    reviewing_tool: str = ""
    generating_agent: str = ""
    generating_model: str = ""       # likely the largest single source of variance
    judge_model: str = ""            # a judge is not interchangeable with another judge
    rubric_version: str = ""         # criteria and briefs change under the same name
    replicate_id: str = ""           # which repeat of an identical configuration — the noise floor lives here
    blinding: str = ""               # what the reviewer could see
    deterministic_score: str = ""
    judged_mean: str = ""
    judged_scored: str = ""          # a mean over part of a review is not a score of the artifact,
    judged_answered: str = ""        #   so both denominators are stored beside it
    recurrence_pass: str = ""
    recurrence_total: str = ""
    checklist_correct: str = ""
    checklist_wrong: str = ""
    checklist_absent: str = ""
    checklist_items: str = ""
    #: The `evaluate` half. Captured on every describe run from 2026-08-22 onward, because the output is
    #: not recoverable afterwards — the history signals are computed from the log as it stood.
    findings_capture: str = ""       # path of the capture, relative to the data repo; "" = not captured
    findings_count: str = ""
    findings_deterministic: str = "" # yes / no / "" for not checked — never silently assumed
    evaluate_rubric_version: str = ""
    evaluate_mean: str = ""
    evaluate_scored: str = ""        # same two denominators as the artifact half, for the same reason:
    evaluate_answered: str = ""      #   a mean over part of a review is not a score of the output
    #: A `precision` round: findings labelled by a reviewer with the tool's claim withheld. Per-signal
    #: precision is the useful form and does not fit a row, so it lives in the write-up; these are the
    #: aggregates, which are what a later round can be compared against.
    precision_n: str = ""            # findings rated (excludes `unsure`, which is missing data)
    precision_confirmed: str = ""
    precision_partial: str = ""      # something real, but not what the finding claimed
    precision_dismissed: str = ""
    precision_groups: str = ""       # which signal groups the round covered, e.g. "B,C"
    predecessor_run_id: str = ""     # set on the second run of an update pair (§16)
    notes: str = ""

    def comparable(self, metric: str = "judged_mean") -> bool:
        return all(self.key(k) is not None for k in keys_for(metric))

    def key(self, name: str) -> str | None:
        """The value of a comparability key, or `None` if it was never recorded."""
        v = (getattr(self, name) or "").strip()
        return None if not v or v.lower() in UNKNOWN else v

    def signature(self, metric: str = "judged_mean") -> tuple:
        return tuple(self.key(k) for k in keys_for(metric))


COLUMNS = [f.name for f in fields(Row)]

#: `precision` is a spot-check round: findings labelled by a reviewer who did not build the checks, with
#: the tool's severity and confidence withheld. Distinct from `calibration`, which scores an artifact.
RUN_KINDS = {"calibration", "scoring", "noise-floor", "checklist", "recurrence", "precision"}


def tool_skew(row: Row) -> str:
    """Whether this row's review used a different archagent than its generation, or "" if not.

    Not an error. Round 4's artifact was generated by the working tree and reviewed against a build six
    weeks older, and the problem was not that the two differed — it was that nothing said so, and a
    reviewer reasonably read a missing command as a stale document. A row where they differ is legible;
    a row that hides it is not.
    """
    if not row.reviewing_tool or not row.archagent_commit:
        return ""
    if row.reviewing_tool.strip() == row.archagent_commit.strip():
        return ""
    return f"generated with {row.archagent_commit}, reviewed against {row.reviewing_tool}"


def validate(row: Row, existing: list[Row]) -> list[str]:
    """Reasons this row should not be written. Empty means it is fine.

    Deliberately strict about identity and lenient about scores: a run with a missing score is a run that
    partly failed, which is worth recording. A run with a duplicate id or an unpinned target is a row that
    will mislead somebody later.
    """
    bad = []
    if not row.run_id:
        bad.append("no run_id")
    if any(r.run_id == row.run_id for r in existing):
        bad.append(f"run_id {row.run_id!r} is already in the ledger")
    if row.run_kind not in RUN_KINDS:
        bad.append(f"run_kind {row.run_kind!r} is not one of {sorted(RUN_KINDS)}")
    if not row.target_commit or row.target_commit.lower() in UNKNOWN:
        bad.append("no target_commit — a target is a repository at a revision, and an unpinned row "
                   "cannot be reproduced or compared")
    if row.predecessor_run_id and not any(r.run_id == row.predecessor_run_id for r in existing):
        bad.append(f"predecessor_run_id {row.predecessor_run_id!r} is not in the ledger")
    return bad


def load(path: Path) -> list[Row]:
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        extra = set(reader.fieldnames or []) - set(COLUMNS)
        if missing or extra:
            # A schema that has drifted silently is worse than one that fails: every row read under the
            # wrong header is a plausible-looking row with values in the wrong columns.
            raise ValueError(f"ledger schema mismatch at {path}: missing {sorted(missing)}, "
                             f"unexpected {sorted(extra)}")
        return [Row(**{k: (v or "") for k, v in rec.items()}) for rec in reader]


def save(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


@dataclass
class Comparison:
    rows: list[Row]                              # rows carrying the metric
    excluded: list[tuple[Row, str]]              # row, why — only ever "no <metric>"
    differs_on: list[str]                        # keys with two different recorded values — fatal
    unverifiable_on: list[str]                   # keys unrecorded on some row — a caveat, not fatal
    keys: tuple[str, ...] = COMPARABILITY_KEYS   # which key set governed this comparison

    @property
    def sound(self) -> bool:
        return bool(self.rows) and not self.differs_on


def compare(rows: list[Row], metric: str) -> Comparison:
    """Assemble a series on one metric, and say what is wrong with it.

    Two distinct problems, and collapsing them makes the tool useless. **`differs_on` is fatal**: the rows
    record different judge models, generating models or rubric versions, so they measure different things
    and a series across them is an artifact of the table rather than a result. **`unverifiable_on` is a
    caveat**: some row never recorded that key, so a difference cannot be ruled out.

    The historical runs mostly fall in the second category — nobody wrote down which model generated the
    obstudio artifact, and that is unrecoverable now. Excluding them entirely would throw away the only
    history there is; presenting them as sound would launder an unknown into a trend. So they are shown,
    with the gap named.

    **Which keys apply depends on the metric**, and getting that wrong in either direction is a real
    error. Gating an artifact score on the archagent build would refuse sound comparisons; not gating a
    findings score on it would compare output from two different tools. `keys_for` decides, and refuses
    a metric nobody has classified rather than guessing.
    """
    keys = keys_for(metric)
    usable, excluded = [], []
    for r in rows:
        (usable if getattr(r, metric, "") else excluded).append(
            r if getattr(r, metric, "") else (r, f"no {metric}"))
    differs, unverifiable = [], []
    for k in keys:
        seen = {r.key(k) for r in usable}
        if None in seen:
            unverifiable.append(k)
            seen.discard(None)
        if len(seen) > 1:
            differs.append(k)
    return Comparison(rows=usable, excluded=excluded,
                      differs_on=differs, unverifiable_on=unverifiable, keys=keys)

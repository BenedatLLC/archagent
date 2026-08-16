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
COMPARABILITY_KEYS = ("rubric_version", "judge_model", "generating_model")


@dataclass
class Row:
    run_id: str                      # primary key; date-target-what, readable on sight
    date: str                        # ISO
    archagent_commit: str            # the tool version under evaluation
    target_url: str
    target_commit: str               # a target is a repository *at a revision*, never a repository
    target_fresh: str                # yes / no — had this target ever been used before?
    run_kind: str                    # calibration | scoring | noise-floor | checklist
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
    predecessor_run_id: str = ""     # set on the second run of an update pair (§16)
    notes: str = ""

    def comparable(self) -> bool:
        return all(self.key(k) is not None for k in COMPARABILITY_KEYS)

    def key(self, name: str) -> str | None:
        """The value of a comparability key, or `None` if it was never recorded."""
        v = (getattr(self, name) or "").strip()
        return None if not v or v.lower() in UNKNOWN else v

    def signature(self) -> tuple:
        return tuple(self.key(k) for k in COMPARABILITY_KEYS)


COLUMNS = [f.name for f in fields(Row)]

RUN_KINDS = {"calibration", "scoring", "noise-floor", "checklist", "recurrence"}


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
    """
    usable, excluded = [], []
    for r in rows:
        (usable if getattr(r, metric, "") else excluded).append(
            r if getattr(r, metric, "") else (r, f"no {metric}"))
    differs, unverifiable = [], []
    for k in COMPARABILITY_KEYS:
        seen = {r.key(k) for r in usable}
        if None in seen:
            unverifiable.append(k)
            seen.discard(None)
        if len(seen) > 1:
            differs.append(k)
    return Comparison(rows=usable, excluded=excluded,
                      differs_on=differs, unverifiable_on=unverifiable)

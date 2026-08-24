"""The user-test ledger — deliberately not `ledger.csv`.

`ledger.py` records runs of the tool scored against a rubric: the unit is an artifact, and comparability
is gated by what produced it (`generating_model`) and what judged it (`rubric_version`, `judge_model`).

A user test has a different unit. The subject is not the artifact but **whether a person can get a result
at all**, and the things that decide whether two rounds are comparable are different in kind: which
documentation they read, whether they had a coding agent, and how much they already knew. Putting these
rows in the same table would mean a dozen columns that are meaningless on one side or the other, and
would invite the one mistake the comparability machinery exists to prevent — a chart of "quality over
time" mixing artifact rubric means with usability ratings.

Two rules this file enforces that the other ledger does not need:

**The four dimensions are never averaged.** `ease_of_use` measures something this design supports;
`correctness` is a spot check whose weight depends entirely on how many claims the tester actually
verified. A mean over the two is a number with no referent — the same reason impact ratings are reported
as a distribution.

**The documentation path is a comparability key.** Round 1's tester could not fetch the pinned GitHub
tree and fell back to `--help` and the installed skill files, so round 1 did not measure the question it
was designed to ask. That is not a footnote; a later round read against it without the caveat would be
comparing two different experiments.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: The four rubric dimensions, in worksheet order. Reported as a vector, always.
DIMENSIONS = ("ease_of_use", "correctness", "completeness", "impact")

#: What must match for two user-test rounds to be comparable.
#:
#: `docs_path` is here because it decides what the round measured, not merely how well it went.
#: `archagent_version` because the tool under test is the subject. `rubric_version` because the
#: questions changed. Deliberately absent: the target repository — a different repository is a different
#: round, and pretending otherwise is how "the tool got easier" would come to mean "httpx is smaller".
COMPARABILITY_KEYS = ("rubric_version", "archagent_version", "docs_path")

#: How the tester actually obtained instructions.
#:
#: `published` is the design: they read the pinned documentation. `fallback` means they could not, and
#: worked from the CLI's own help and the installed prompts. `mixed` is some of each. Only `published`
#: rounds answer the question the kit was built to ask.
DOCS_PATHS = ("published", "fallback", "mixed")


@dataclass
class UserTestRow:
    run_id: str
    date: str
    #: Provenance, shared in spirit with `ledger.py` — a result nobody can locate is not evidence.
    archagent_version: str
    archagent_commit: str
    target_url: str
    target_commit: str
    rubric_version: str
    docs_path: str
    #: Who did it, and what they knew going in. A tester who has seen the tool before is measuring
    #: something else, and the honest place to say so is a column rather than prose.
    tester: str = ""
    prior_exposure: str = ""       # "none" | "read docs" | "author" | free text
    had_coding_agent: str = ""     # "yes" | "no" | "partial"
    #: The four ratings. Empty string means "could not judge", which is data and must survive as distinct
    #: from a zero.
    ease_of_use: str = ""
    correctness: str = ""
    completeness: str = ""
    impact: str = ""
    #: What the correctness rating is worth. Round 5 established that findings which read as plausible
    #: are often wrong, so a correctness score carries no weight without this.
    claims_verified: str = ""
    #: Process measurements — the part of a user test no other harness produces.
    minutes_to_installed: str = ""
    minutes_to_first_output: str = ""
    minutes_total: str = ""
    blockers: str = ""             # count of distinct stuck points recorded in Part 1
    dismissal_rate: str = ""       # tester's estimate of findings not worth acting on
    completed: str = "yes"         # "no" when they gave up — a kit that cannot be finished is a result
    notes: str = ""

    def __post_init__(self) -> None:
        if self.docs_path not in DOCS_PATHS:
            raise ValueError(
                f"docs_path must be one of {DOCS_PATHS}, got {self.docs_path!r}. This is not a "
                f"formality: a round where the tester could not reach the documentation did not measure "
                f"the question the kit asks, and recording it as though it did makes the next round "
                f"incomparable in a way nobody will notice.")
        for d in DIMENSIONS:
            v = getattr(self, d)
            if v not in ("", "1", "2", "3", "4", "5"):
                raise ValueError(f"{d} must be 1-5 or empty (could not judge), got {v!r}")


def scores(row: UserTestRow) -> dict[str, int | None]:
    """The four ratings as a vector. There is deliberately no `mean()` beside this.

    Averaging `ease_of_use` with `correctness` produces a number with no referent: the first is a direct
    observation of the thing this design measures, the second is a spot check whose weight is
    `claims_verified` and nothing else. Round 1 would read 1.75, which says less than "1" and "2" do.
    """
    out: dict[str, int | None] = {}
    for d in DIMENSIONS:
        v = getattr(row, d)
        out[d] = int(v) if v else None
    return out


def comparable(a: UserTestRow, b: UserTestRow) -> tuple[bool, str]:
    """Whether two rounds may be read as a series, and if not, which key differs."""
    for k in COMPARABILITY_KEYS:
        if getattr(a, k) != getattr(b, k):
            return False, (f"{k} differs ({getattr(a, k)!r} vs {getattr(b, k)!r}) — these rounds are not "
                           f"a series")
    return True, ""


def refuse_join(*_args, **_kwargs):
    """There is no join between this ledger and `ledger.csv`, by construction.

    Calling this is always an error. It exists so that the intent is greppable and a future reader who
    reaches for a combined chart finds the reason rather than the absence of an obstacle: artifact rubric
    means and usability ratings share a 1-5 scale and measure nothing in common.
    """
    raise NotImplementedError(
        "user-test rows and calibration rows are not joinable. They share a 1-5 scale and no subject: "
        "one scores an artifact the tool produced, the other scores whether a person could produce one. "
        "If you want both in a write-up, cite them separately and say what each measures.")


def append(path: Path, row: UserTestRow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    d = asdict(row)
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(d))
        if new:
            w.writeheader()
        w.writerow(d)


def load(path: Path) -> list[UserTestRow]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [UserTestRow(**r) for r in csv.DictReader(f)]

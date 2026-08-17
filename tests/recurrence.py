"""The recurrence suite (`docs/designs/evaluating-archagent.md` §13).

Every confirmed defect is a fact about a pinned target. This turns those facts into mechanical assertions,
so a defect found once is checked for on every artifact generated for that target afterwards — and so that
three rounds of expensive human and judge review stop existing only as prose somebody has to remember.

**Entries are phrased against the target, not the artifact.** An assertion like "the artifact must not mark
SKILL-002 as active" breaks the first time a regenerated artifact numbers its invariants differently, and
it does, every run. "Any claim that per-skill scripts are shims is false, because `validate_gap_closure.py`
is 712 lines" survives regeneration, because it is a fact about a commit.

**Every `forbid` needs a `require` where the topic is load-bearing.** Left alone, negative assertions
reward silence: an artifact passes "must not describe `Store` as a single mutex" by never mentioning
concurrency. That is the direction `check_specificity` exists to punish, so an entry may demand that the
artifact *engage* with the evidence as well as not misstate it.

**What this catches and what it cannot.** `forbid` catches a claim restated. `require` catches an omission
— the artifact never looked. Neither catches *misreading*: a citation that resolves and does not support
its claim, which is the failure this project has now recorded six times across three rounds. §14's
checklists are for that, and they need a judge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:                       # py < 3.11
    tomllib = None


@dataclass(frozen=True)
class Entry:
    id: str
    target: str
    rev: str
    ground_truth: str                              # the fact, in prose, for whoever reads a failure
    forbid: tuple[str, ...] = ()                   # regexes the artifact must not match
    require: tuple[str, ...] = ()                  # regexes it must match (the positive pair)
    severity: str = "moderate"
    found_by: str = ""
    note: str = ""
    kind: str = "claim"                            # "claim" about the target, or see below


# `kind = "guard"` marks the exception to the rule in this module's docstring: an entry that is *not* a
# fact about the target but about the artifact's own text integrity. There is one so far — a paragraph
# emptied by shell command-substitution during an edit, leaving grammatical prose with no content. It is
# deliberately forbid-only, because silence genuinely does pass it: an artifact that never writes the
# corrupted paragraph is correct. Guards are exempt from the require-pair rule; claims are not.


@dataclass
class Result:
    entry: Entry
    restated: list[str] = field(default_factory=list)   # forbidden patterns that matched
    missing: list[str] = field(default_factory=list)    # required patterns that did not

    @property
    def ok(self) -> bool:
        return not self.restated and not self.missing

    def explain(self) -> str:
        lines = [f"{self.entry.id}  [{self.entry.severity}]",
                 f"    ground truth: {self.entry.ground_truth}"]
        for pat in self.restated:
            lines.append(f"    RESTATED  the artifact matches /{pat}/, which the target contradicts")
        for pat in self.missing:
            lines.append(f"    ABSENT    nothing in the artifact matches /{pat}/ — the topic is not addressed")
        if self.entry.found_by:
            lines.append(f"    first found by: {self.entry.found_by}")
        return "\n".join(lines)


def load(path: Path) -> list[Entry]:
    if tomllib is None:
        raise RuntimeError("recurrence entries need tomllib (Python 3.11+)")
    raw = tomllib.loads(path.read_text())
    out = []
    for e in raw.get("entry", []):
        out.append(Entry(
            id=e["id"], target=e["target"], rev=e["rev"], ground_truth=e["ground_truth"],
            forbid=tuple(e.get("forbid", ())), require=tuple(e.get("require", ())),
            severity=e.get("severity", "moderate"), found_by=e.get("found_by", ""),
            note=e.get("note", ""), kind=e.get("kind", "claim")))
    return out


def artifact_text(arch: Path) -> str:
    """Every document, concatenated. Deliberately not per-file: an entry is about whether the *artifact*
    makes a claim, and which document carries it is the author's choice and changes between runs."""
    parts = []
    for p in sorted(arch.rglob("*.md")):
        if p.name.endswith("_TEMPLATE.md"):
            continue
        parts.append(p.read_text(errors="replace"))
    return "\n".join(parts)


def ambiguous_requires(entry: Entry) -> str:
    """Why this entry's `require` list is likely to mean the opposite of what its author intended.

    **`require` is conjunctive: every pattern must match.** That reads wrongly to anyone writing two
    patterns for two spellings of the same idea, which is the natural thing to do — and it has now produced
    a false alarm on a real artifact. An entry demanded `(ownership...)…(enforc…)` *and*
    `(enforc…)…(ownership...)`, one per word order, meaning "either order will do"; because both had to
    match, an artifact that stated the fact in one order was reported as silent on it. It had its own ADR
    on the subject.

    Two `require` patterns are legitimate when they are genuinely different obligations — say, name the
    mechanism *and* name the consequence. They are a bug when each is an alternative phrasing of one
    obligation, and the tell is that the patterns share their alternatives. Anything sharing a term is
    flagged; the fix is one pattern with an `|` between the spellings.
    """
    if len(entry.require) < 2:
        return ""
    def terms(p: str) -> set[str]:
        return {w.lower() for w in re.findall(r"[a-z][a-z_ -]{3,}", p)}
    for i, a in enumerate(entry.require):
        for b in entry.require[i + 1:]:
            shared = terms(a) & terms(b)
            if shared:
                return (f"two `require` patterns share {sorted(shared)[:3]} — `require` is conjunctive, so "
                        f"both must match. If these are two spellings of one obligation, join them with `|` "
                        f"in a single pattern")
    return ""


def check(entries: list[Entry], arch: Path, target: str | None = None) -> list[Result]:
    text = artifact_text(arch)
    out = []
    for e in entries:
        if target and e.target != target:
            continue
        out.append(Result(
            entry=e,
            restated=[p for p in e.forbid if re.search(p, text, re.IGNORECASE | re.DOTALL)],
            missing=[p for p in e.require if not re.search(p, text, re.IGNORECASE | re.DOTALL)],
        ))
    return out

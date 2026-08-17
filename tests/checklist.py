"""Per-repository checklists (`docs/designs/evaluating-archagent.md` §14).

A checklist is a fixed list of specific claims an artifact should get right about one target, **with the
correct answer written down**, judged `correct` / `wrong` / `absent`.

**The ground truth is the whole point.** Asking a judge *"is the concurrency description correct?"* is a
research task, and it re-runs the very error the checklist exists to catch. Asking *"`Store` uses a
`sync.RWMutex` plus `subMu`, `invalidateMu` and `changeMu` (store.go:313-332) — does the artifact convey
this?"* converts research into comparison: cheaper, reproducible, and ternary rather than 1–5, so the
variance sits far below a five-point judgement.

The reading was done once, by a human, during a calibration round. A checklist is where that afternoon is
banked so it never has to be repeated.

**This is the piece that covers misreading.** The recurrence suite (§13) catches a claim restated and a
topic never addressed. Neither catches a citation that resolves and does not support its claim — the
failure this project has recorded six times across three rounds — because nothing about it is lexical. A
judge holding the answer key catches it, and holding the key is what keeps the judge cheap.

**A checklist is an answer key, and answer keys leak.** Whoever authors a prompt change must not be reading
one while doing so, or the change is fitted to the test. Same blinding rule as §15's exclusion of the
prompting repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:                       # py < 3.11
    tomllib = None

VERDICTS = ("correct", "wrong", "absent")

#: `serious` defects are the ones that would mislead someone changing the system; `minor` ones are wrong
#: sentences. An unweighted score treats a false security claim and a file count identically, and three of
#: the four defects that mattered across rounds 2 and 3 were `serious`.
WEIGHT = {"serious": 3, "moderate": 2, "minor": 1}


@dataclass(frozen=True)
class Item:
    id: str
    target: str
    rev: str
    ground_truth: str                 # the answer key: the fact, with the citation that establishes it
    question: str = ""                # overrides the default "does the artifact convey this?" framing
    severity: str = "moderate"
    source: str = ""                  # which reading produced it — a round, a reviewer, a replicate
    note: str = ""
    conditional: bool = False         # `absent` is a pass, not a miss — see below

    def ask(self) -> str:
        return self.question or "Does the artifact convey this?"

    def passes(self, verdict: str) -> bool:
        """`correct`, or `absent` on a conditional item.

        A conditional item asks *if the artifact states a count, is it right?* — so an artifact that
        declines to state an incidental count is answering correctly by saying nothing, and scoring that
        `absent` as a miss marks it down for good judgement. Found in step 2: three regenerated artifacts
        each lost two items this way, and the design those artifacts were following is the one that says
        incidental counts should not be written at all.
        """
        return verdict == "correct" or (self.conditional and verdict == "absent")


@dataclass
class Answer:
    item_id: str
    verdict: str | None
    quote: str = ""                   # the artifact passage the verdict is about
    why: str = ""
    discarded: str = ""


def load(path: Path) -> list[Item]:
    if tomllib is None:
        raise RuntimeError("checklists need tomllib (Python 3.11+)")
    raw = tomllib.loads(path.read_text())
    return [Item(id=i["id"], target=i["target"], rev=i["rev"], ground_truth=i["ground_truth"],
                 question=i.get("question", ""), severity=i.get("severity", "moderate"),
                 source=i.get("source", ""), note=i.get("note", ""),
                 conditional=bool(i.get("conditional", False)))
            for i in raw.get("item", [])]


def render(items: list[Item], artifact_path: str, target: str, rev: str = "") -> str:
    """The judge's worksheet: fixed questions, fixed order, answer key included.

    Deliberately *not* an invitation to explore. The judge reads the artifact and compares it to what is
    written here; it does not go looking through the codebase, because the looking was already done and
    redoing it is where a judge's own errors enter.
    """
    head = [
        f"# Architecture checklist — {target}" + (f" @ {rev}" if rev else ""),
        "",
        f"Artifact: `{artifact_path}/`",
        "",
        f"{len(items)} claims, each with the correct answer stated. **The answer is given; you are not "
        "being asked to research it.** Read the artifact and decide, for each, whether it conveys what is "
        "stated below.",
        "",
        "| verdict | when |",
        "|---|---|",
        "| `correct` | the artifact states this, or something equivalent to it |",
        "| `wrong` | the artifact states something that contradicts it |",
        "| `absent` | the artifact does not address it either way |",
        "",
        "**`wrong` requires a quote from the artifact** — the passage you are calling wrong, copied. If "
        "you cannot point at a passage, the honest answer is `absent`, and the boundary between those two "
        "is where this instrument is weakest, so do not guess across it.",
        "",
        "`correct` also takes a quote. `absent` takes none, by definition.",
        "",
        "Do not read the repository. If the artifact and the answer key disagree, the answer key is right "
        "for the purposes of this worksheet — it was verified against the code when it was written.",
        "",
        "Answer every item. A skipped item is reported as skipped, not as a pass.",
        "",
        "---",
    ]
    for it in items:
        head += [
            "",
            f"## {it.id}",
            "",
            f"**Ground truth ({it.severity}).** {it.ground_truth.strip()}",
            "",
            it.ask(),
            "",
            "```",
            "verdict:",
            "quote:",
            "why:",
            "```",
            "",
            "---",
        ]
    return "\n".join(head) + "\n"


_FIELDS = ("verdict", "quote", "why")
_KEY = re.compile(rf"^[ \t>*-]*({'|'.join(_FIELDS)})\s*:[ \t]*", re.IGNORECASE | re.MULTILINE)


def _fields(block: str) -> dict[str, str]:
    """Each field runs to the next key, not to the end of its line — a quote is usually several lines, and
    reading one line of it discards the evidence the verdict rests on. Same lesson as `rubric_judged`,
    where a line-scoped read reported the best-evidenced review received as uncited."""
    fence = re.search(r"```[^\n]*\n(.*?)```", block, re.DOTALL)
    body = fence.group(1) if fence else block
    keys = [(m.group(1).lower(), m.end(), m.start()) for m in _KEY.finditer(body)]
    got = {k: "" for k in _FIELDS}
    for i, (name, value_at, _) in enumerate(keys):
        end = keys[i + 1][2] if i + 1 < len(keys) else len(body)
        if not got[name]:
            got[name] = body[value_at:end].strip()
    return got


def parse(text: str, items: list[Item]) -> dict[str, Answer]:
    known = {it.id: it for it in items}
    out: dict[str, Answer] = {}
    for block in re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]:
        item_id = block.split("\n", 1)[0].strip().split()[0].strip("`")
        if item_id not in known:
            continue
        got = _fields(block)
        verdict = next((v for v in VERDICTS if re.search(rf"\b{v}\b", got["verdict"], re.I)), None)
        a = Answer(item_id=item_id, verdict=verdict, quote=got["quote"], why=got["why"])
        if verdict is None:
            a.discarded = f"no verdict read from {got['verdict'][:40]!r}"
            a.verdict = None
        elif verdict == "wrong" and not got["quote"].strip():
            # The rule that holds the wrong/absent boundary. Without it, `wrong` becomes the verdict a
            # judge reaches for whenever the artifact is merely vague, and a vague artifact scores the
            # same as a lying one.
            a.discarded = "verdict `wrong` with no quote from the artifact"
            a.verdict = None
        out[item_id] = a
    return out


@dataclass
class Score:
    target: str
    counts: dict[str, int] = field(default_factory=dict)     # verdict -> n
    weighted: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)         # never answered
    discarded: list[tuple[str, str]] = field(default_factory=list)

    @property
    def answered(self) -> int:
        return sum(self.counts.values())

    passed: int = 0                                          # correct, plus `absent` on a conditional item
    weighted_passed: int = 0

    @property
    def accuracy(self) -> float | None:
        """Share of answered items the artifact got right. `None` rather than 1.0 when nothing was
        answered — an empty worksheet must not read as a perfect one."""
        return self.passed / self.answered if self.answered else None

    @property
    def weighted_accuracy(self) -> float | None:
        total = sum(self.weighted.values())
        return self.weighted_passed / total if total else None


def score(answers: dict[str, Answer], items: list[Item]) -> Score:
    s = Score(target=items[0].target if items else "")
    s.counts = {v: 0 for v in VERDICTS}
    s.weighted = {v: 0 for v in VERDICTS}
    for it in items:
        a = answers.get(it.id)
        if a is None:
            s.skipped.append(it.id)
            continue
        if a.discarded:
            s.discarded.append((it.id, a.discarded))
            continue
        s.counts[a.verdict] += 1
        s.weighted[a.verdict] += WEIGHT.get(it.severity, 1)
        if it.passes(a.verdict):
            s.passed += 1
            s.weighted_passed += WEIGHT.get(it.severity, 1)
    return s

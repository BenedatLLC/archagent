"""Locate tasks — the judged half of completeness (`docs/designs/evaluating-archagent.md` §14).

The `completeness` anchor for a 5 says: *"A newcomer could locate any significant behaviour from the
documents alone."* Nothing measures that. The checklist asks whether the artifact **conveys** a fact and
hands the judge the answer first; `described.py` asks whether a module is **named**. An artifact can score
well on both and still leave a reader unable to find where anything happens.

A locate task states a behaviour and asks where it lives. The judge answers **from the documents only**,
without the answer key, and is scored afterwards on whether it arrived at the right module.

**This is why the worksheet must not contain the answer, and it is the opposite of the checklist rule.**
A checklist gives the judge the ground truth so it compares instead of researching, which is what keeps it
cheap and reproducible. Here the search *is* the measurement: a judge told the module beforehand would
confirm it in the prose and report success from an artifact that could never have led anyone there.

**Why this has headroom when nothing else does.** Every accuracy instrument is saturated — fresh artifacts
score 0.88 to 1.00 on per-item checklists across three targets. Accuracy is not where these documents fail.
They fail by being shallow in places, and shallowness shows up precisely when someone tries to use them to
find something.

Grading is mechanical: the judge's answer either names a module the behaviour actually lives in or it does
not. That keeps the verdict auditable and keeps the instrument's own variance low — the failure mode of a
free-text judgement is that two graders read the same answer differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:                       # py < 3.11
    tomllib = None

VERDICTS = ("located", "partial", "lost")

#: A `located` answer is worth its full weight; a `partial` — right subsystem, wrong or missing module —
#: half. A reader who reaches the right document and then cannot find the mechanism has been helped, but
#: not enough.
CREDIT = {"located": 1.0, "partial": 0.5, "lost": 0.0}
WEIGHT = {"serious": 3, "moderate": 2, "minor": 1}


@dataclass(frozen=True)
class Task:
    id: str
    target: str
    rev: str
    question: str                    # the behaviour, stated without naming where it lives
    expects: tuple[str, ...]         # module paths that actually implement it; naming one is `located`
    subsystem: str = ""              # the document that should carry it; naming it alone is `partial`
    answer: str = ""                 # the key in prose, for whoever reads a failure
    severity: str = "moderate"
    note: str = ""


@dataclass
class Response:
    task_id: str
    where: str = ""                  # the judge's answer: the module or mechanism it arrived at
    document: str = ""               # the document it says leads there
    why: str = ""
    unanswered: bool = False


@dataclass
class Graded:
    task: Task
    response: Response | None
    verdict: str                     # located | partial | lost
    matched: str = ""                # what in the answer earned the verdict

    @property
    def credit(self) -> float:
        return CREDIT.get(self.verdict, 0.0)


def _names(text: str, needle: str) -> str:
    """Does `text` name `needle`, as a path or as a bare module name?

    Word-boundary, not substring: `described.py` learned that the hard way, where a substring test let a
    module named `a.py` match the letter "a" inside "named".
    """
    if not needle:
        return ""
    if needle in text:
        return needle
    stem = Path(needle).stem
    if len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", text):
        return stem
    return ""


def grade(task: Task, response: Response | None) -> Graded:
    """Where the judge arrived, against where the behaviour actually lives.

    Deliberately mechanical. A grader reading two free-text answers is a second judgement with its own
    variance, and the instrument would then be measuring the grader.
    """
    if response is None or response.unanswered:
        return Graded(task, response, "lost")
    said = f"{response.where}\n{response.document}\n{response.why}"
    for path in task.expects:
        hit = _names(said, path)
        if hit:
            return Graded(task, response, "located", hit)
    if task.subsystem and _names(said, task.subsystem):
        return Graded(task, response, "partial", task.subsystem)
    return Graded(task, response, "lost")


def load(path: Path) -> list[Task]:
    if tomllib is None:
        raise RuntimeError("locate tasks need tomllib (Python 3.11+)")
    raw = tomllib.loads(path.read_text())
    return [Task(id=t["id"], target=t["target"], rev=t["rev"], question=t["question"],
                 expects=tuple(t.get("expects", ())), subsystem=t.get("subsystem", ""),
                 answer=t.get("answer", ""), severity=t.get("severity", "moderate"),
                 note=t.get("note", ""))
            for t in raw.get("task", [])]


def render(tasks: list[Task], artifact_path: str, target: str, rev: str = "") -> str:
    """The judge's worksheet. **Contains no answers** — see the module docstring."""
    head = [
        f"# Can you find it? — {target}" + (f" @ {rev}" if rev else ""),
        "",
        f"Artifact: `{artifact_path}/`",
        "",
        f"{len(tasks)} questions about where things happen in this system. **Answer each one using the "
        "architecture documents only.** Do not read the source code, and do not answer from what you "
        "already know about systems like this one — the question is whether *these documents* can lead a "
        "reader to the answer.",
        "",
        "For each question give:",
        "",
        "- **`where`** — the module, file or mechanism that does it. Be as specific as the documents let "
        "you be; a path is better than a package, a package is better than a subsystem name.",
        "- **`document`** — which document you found it in, and roughly where.",
        "- **`why`** — the sentences that got you there, quoted or paraphrased.",
        "",
        "**If the documents do not answer the question, write `where: NOT FOUND` and say what you looked "
        "at.** That is a real and useful result, and guessing is worse than useless — an answer that "
        "happens to be right by inference from the name of a subsystem tells us nothing about whether the "
        "documents work.",
        "",
        "Answer every question.",
        "",
        "---",
    ]
    for t in tasks:
        head += ["", f"## {t.id}", "", t.question.strip(), "",
                 "```", "where:", "document:", "why:", "```", "", "---"]
    return "\n".join(head) + "\n"


_FIELDS = ("where", "document", "why")
_KEY = re.compile(rf"^[ \t>*-]*({'|'.join(_FIELDS)})\s*:[ \t]*", re.IGNORECASE | re.MULTILINE)


def _fields(block: str) -> dict[str, str]:
    fence = re.search(r"```[^\n]*\n(.*?)```", block, re.DOTALL)
    body = fence.group(1) if fence else block
    keys = [(m.group(1).lower(), m.end(), m.start()) for m in _KEY.finditer(body)]
    got = {k: "" for k in _FIELDS}
    for i, (name, at, _) in enumerate(keys):
        end = keys[i + 1][2] if i + 1 < len(keys) else len(body)
        if not got[name]:
            got[name] = body[at:end].strip()
    return got


def parse(text: str, tasks: list[Task]) -> dict[str, Response]:
    known = {t.id for t in tasks}
    out: dict[str, Response] = {}
    for block in re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]:
        tid = block.split("\n", 1)[0].strip().split()[0].strip("`")
        if tid not in known:
            continue
        got = _fields(block)
        out[tid] = Response(task_id=tid, where=got["where"], document=got["document"], why=got["why"],
                            unanswered=bool(re.search(r"\bnot found\b", got["where"], re.IGNORECASE))
                            or not got["where"].strip())
    return out


@dataclass
class Score:
    graded: list[Graded] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def answered(self) -> int:
        return len(self.graded)

    @property
    def findability(self) -> float | None:
        """Credit earned over credit available. `None` when nothing was answered — an empty worksheet
        must not read as a perfect one, the same rule the checklist scorer follows."""
        if not self.graded:
            return None
        return sum(g.credit for g in self.graded) / len(self.graded)

    @property
    def weighted(self) -> float | None:
        total = sum(WEIGHT.get(g.task.severity, 1) for g in self.graded)
        if not total:
            return None
        return sum(g.credit * WEIGHT.get(g.task.severity, 1) for g in self.graded) / total

    def by_verdict(self) -> dict[str, int]:
        out = {v: 0 for v in VERDICTS}
        for g in self.graded:
            out[g.verdict] += 1
        return out


def score(tasks: list[Task], responses: dict[str, Response]) -> Score:
    s = Score()
    for t in tasks:
        r = responses.get(t.id)
        if r is None:
            s.skipped.append(t.id)
            continue
        s.graded.append(grade(t, r))
    return s

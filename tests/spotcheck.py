"""Human spot-check and calibration (`docs/designs/evaluating-archagent.md` §11).

Nothing so far establishes that an automated judgement tracks reality. A model scoring a rubric produces
a number whether or not the number means anything, and the corpus pass showed how easily one interested
labeller drifts. The fix is not more human labelling — nobody will review 78 hotspot findings — but
*enough* to measure how far the automated judge agrees with a person. That agreement rate is what turns a
score into an estimate with an error bar instead of an assertion.

Three design points, each of which decides whether the labels are worth collecting:

**The tool's own claim is withheld.** Severity, confidence and the recommendation live in a side file the
reviewer never opens; the worksheet carries evidence only. Shown up front they anchor the reviewer, and
the exercise then measures agreement with our own prior rather than with reality.

**A worksheet, not a prompt loop.** Thirty items is a week of spare moments. A file can be reviewed in an
editor, committed, and diffed.

**Labels are durable and keyed revision-independently.** They are the expensive input, so a re-run asks
only about items with no label. Changing a verdict requires a note — otherwise labels drift toward
whatever the tool currently claims and the whole exercise becomes circular.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

VERDICTS = ("confirm", "dismiss", "unsure")
SCORE_VERDICTS = ("agree", "too-high", "too-low", "unsure")


# --- identity -------------------------------------------------------------------------------

def finding_key(sign: str, subjects: list[str], values: list[str] | None = None) -> str:
    """A stable id for a finding, independent of the revision it was found at.

    Keyed on what the finding is *about* — its kind, the file that owns it, and the value set — rather
    than on line numbers, churn counts or ordering, all of which move between runs without the finding
    changing. Without this a label is spent once and never reused.
    """
    owner = subjects[0] if subjects else ""
    digest = hashlib.sha1("\x1f".join(sorted(values or [])).encode()).hexdigest()[:8]
    return f"{sign}:{owner}:{digest}"


def values_of(detail: str) -> list[str] | None:
    m = re.search(r"\{([^}]*)\}", detail or "")
    if not m:
        return None
    return sorted(v.strip() for v in m.group(1).split(",") if v.strip() and "more" not in v)


# --- the label store ------------------------------------------------------------------------

@dataclass
class Label:
    key: str
    repo: str
    sign: str
    verdict: str
    why: str
    reviewer: str
    dated: str
    tool_claim: dict = field(default_factory=dict)   # what the tool said *at the time of labelling*
    evidence: str = ""                                # so staleness can be detected later
    history: list[dict] = field(default_factory=list)  # prior verdicts, never discarded

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class LabelStore:
    """`evaluations/labels/<repo>.jsonl` — one record per labelled finding."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, repo: str) -> Path:
        return self.root / f"{repo}.jsonl"

    def load(self, repo: str) -> dict[str, Label]:
        p = self.path(repo)
        if not p.is_file():
            return {}
        out: dict[str, Label] = {}
        for line in p.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["key"]] = Label(**d)
        return out

    def save(self, repo: str, labels: dict[str, Label]) -> None:
        self.path(repo).write_text(
            "".join(json.dumps(l.to_dict(), sort_keys=True) + "\n"
                    for _, l in sorted(labels.items())))

    def record(self, label: Label, note: str = "") -> Label:
        """Write a verdict. **Changing an existing one requires a note**, and the prior verdict is kept.

        Without this, labels drift toward whatever the tool currently claims — a reviewer re-labelling
        after seeing a new run is no longer an independent signal, and the calibration it feeds becomes
        circular.
        """
        labels = self.load(label.repo)
        prior = labels.get(label.key)
        if prior and prior.verdict != label.verdict:
            if not note:
                raise ValueError(
                    f"{label.key} is already labelled '{prior.verdict}' by {prior.reviewer} "
                    f"({prior.dated}). Changing it to '{label.verdict}' requires a note saying why.")
            label.history = prior.history + [
                {"verdict": prior.verdict, "why": prior.why, "reviewer": prior.reviewer,
                 "dated": prior.dated, "changed_because": note}]
        elif prior:
            label.history = prior.history
        labels[label.key] = label
        self.save(label.repo, labels)
        return label

    def stale(self, repo: str, current: dict[str, str]) -> list[str]:
        """Labels whose finding still exists but whose evidence has materially changed. Marked rather
        than silently reused: the verdict was about the evidence as it stood."""
        return [k for k, l in self.load(repo).items()
                if k in current and l.evidence and l.evidence != current[k]]


# --- sampling -------------------------------------------------------------------------------

def stratified_sample(items: list[dict], cap: int = 30, seed: int = 11) -> list[dict]:
    """Spread the sample across signals, confidence tiers and repositories.

    Unstratified, a cheap high-confidence class dominates and the estimate describes that class rather
    than the output. Deterministic given the seed, so a worksheet can be regenerated.
    """
    rng = random.Random(seed)
    strata: dict[tuple, list[dict]] = {}
    for it in items:
        strata.setdefault((it.get("repo", ""), it.get("sign", ""), it.get("confidence", "")), []).append(it)
    for group in strata.values():
        rng.shuffle(group)
    picked: list[dict] = []
    while len(picked) < cap and any(strata.values()):
        for key in sorted(strata, key=str):
            if strata[key] and len(picked) < cap:
                picked.append(strata[key].pop())
    return picked


# --- the worksheet --------------------------------------------------------------------------

_ANSWER = re.compile(r"^\s*verdict\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_WHY = re.compile(r"^\s*why\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_ITEM = re.compile(r"^##\s+item\s+\d+\s+—\s+`([^`]+)`", re.IGNORECASE | re.MULTILINE)


def render_worksheet(items: list[dict], reviewer: str = "") -> tuple[str, dict]:
    """`(markdown, withheld)` — the sheet a person fills in, and the claims kept out of it.

    The withheld half is returned separately rather than hidden in a comment: a claim in the same file is
    a claim the reviewer can read.
    """
    lines = [
        "# archagent spot-check worksheet",
        "",
        f"Reviewer: {reviewer or '(fill in)'}    Date: {date.today().isoformat()}",
        "",
        "For each item below, read the evidence and record a verdict. **The tool's own severity,",
        "confidence and recommendation are deliberately not shown** — they are held back so that this",
        "measures agreement with the code rather than with the tool's prior. They are revealed when the",
        "sheet is ingested.",
        "",
        "Verdicts: `confirm` (a real problem worth acting on) · `dismiss` (not a problem here, say why) ·",
        "`unsure`. A one-line reason matters more than the verdict; it is what makes a disagreement",
        "diagnosable later, and `unsure` is a real answer — it is excluded from the precision denominator",
        "rather than counted as a dismissal.",
        "",
        "The evidence below is a pointer, not a substitute for the code. For a **change-prone file** in",
        "particular the question is whether that file is genuinely absorbing special cases, which only",
        "reading it can answer.",
        "",
        "---",
    ]
    withheld: dict[str, dict] = {}
    for n, it in enumerate(items, 1):
        key = it["key"]
        withheld[key] = it.get("tool_claim", {})
        lines += [
            "",
            f"## item {n} — `{key}`",
            "",
            f"**Repository:** {it.get('repo','')} @ {it.get('rev','')}",
            f"**Kind:** {it.get('sign','')}",
            "",
            "**Evidence**",
            "",
            it.get("evidence", "(none)"),
            "",
            "```",
            "verdict:",
            "why:",
            "```",
            "",
            "---",
        ]
    return "\n".join(lines) + "\n", withheld


def parse_worksheet(text: str) -> dict[str, dict]:
    """Read the filled-in sheet. Deliberately lenient: a reviewer writing `Confirm — intended family`
    should not lose their work to a parser."""
    out: dict[str, dict] = {}
    blocks = re.split(r"^##\s+item\s+", text, flags=re.MULTILINE)[1:]
    for block in blocks:
        m = re.match(r"\d+\s+—\s+`([^`]+)`", block)
        if not m:
            continue
        key = m.group(1)
        verdicts = _ANSWER.findall(block)
        whys = _WHY.findall(block)
        raw = (verdicts[0] if verdicts else "").strip().lower()
        verdict = next((v for v in (*VERDICTS, *SCORE_VERDICTS) if raw.startswith(v)), "")
        if not verdict:
            continue                       # unanswered items are skipped, never guessed at
        out[key] = {"verdict": verdict, "why": (whys[0].strip() if whys else "")}
    return out


# --- statistics -----------------------------------------------------------------------------

def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — behaves sensibly at the small n this exercise produces, where the normal
    approximation would give intervals running past 0 or 1."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def precision_by_sign(labels: list[Label]) -> dict[str, dict]:
    """Per-signal precision from human labels. `unsure` is excluded from the denominator rather than
    counted either way — it is missing data, not a dismissal."""
    out: dict[str, dict] = {}
    for sign in sorted({l.sign for l in labels}):
        rated = [l for l in labels if l.sign == sign and l.verdict in ("confirm", "dismiss")]
        confirmed = sum(1 for l in rated if l.verdict == "confirm")
        lo, hi = wilson(confirmed, len(rated))
        out[sign] = {"n": len(rated), "confirmed": confirmed,
                     "precision": (confirmed / len(rated)) if rated else None,
                     "ci95": [round(lo, 3), round(hi, 3)],
                     "unsure": sum(1 for l in labels if l.sign == sign and l.verdict == "unsure")}
    return out


def agreement(human: dict[str, str], judge: dict[str, str]) -> dict:
    """How far an automated judge agrees with the person, on the items both rated.

    This is the number that licenses quoting an automated score at all — and it is conditional on the
    output distribution it was measured over, so it must be re-sampled whenever that distribution moves
    (a prompt rewrite, a model change, an optimiser).
    """
    shared = sorted(set(human) & set(judge))
    rated = [k for k in shared if human[k] in ("confirm", "dismiss") and judge[k] in ("confirm", "dismiss")]
    agreed = sum(1 for k in rated if human[k] == judge[k])
    lo, hi = wilson(agreed, len(rated))
    return {"n": len(rated), "agreed": agreed,
            "rate": (agreed / len(rated)) if rated else None,
            "ci95": [round(lo, 3), round(hi, 3)],
            "judge_over_confirms": sum(1 for k in rated
                                       if judge[k] == "confirm" and human[k] == "dismiss"),
            "judge_over_dismisses": sum(1 for k in rated
                                        if judge[k] == "dismiss" and human[k] == "confirm")}

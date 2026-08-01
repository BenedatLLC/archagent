"""Blind comparison of the skill layer (`docs/designs/evaluating-archagent.md` §10).

**Question:** is the guidance doing the work, or would any competent reader with the same findings reach
the same report?

Three arms receive byte-identical findings and differ only in their instructions:

- **A** — the shipped `evaluate` skill.
- **B** — a generic prompt: "here are some architecture findings, write a report."
- **C** — the findings alone, with nothing beyond the tool's own recommendation text.

What lives here is everything that can be decided without a model: assembling the identical inputs,
blinding and shuffling the outputs, and the **objective** scoring. Generation and the judged criteria need
an external model and are deliberately not done here — see `scripts/blindcomp.py` for why one session
writing all three arms and then grading them would measure self-preference rather than quality.

The objective half is not a consolation prize. §13.2 requires that anything *gating* a decision be
objective, with judged scores informing proposals and never deciding them, so this is the part that would
carry an acceptance decision even once a judge exists.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ARMS = {
    "A": "shipped evaluate skill",
    "B": "generic prompt (findings + 'write a report')",
    "C": "findings only, no guidance beyond the tool's recommendation text",
}


# --- identical inputs -----------------------------------------------------------------------

def build_input(findings: list[dict], repo: str) -> dict:
    """The payload every arm receives. Identical by construction: one object, hashed, and the hash
    recorded on each arm's brief so a differing input cannot go unnoticed."""
    payload = {"repo": repo, "findings": findings}
    blob = json.dumps(payload, sort_keys=True)
    return {"payload": payload, "digest": hashlib.sha256(blob.encode()).hexdigest()[:12]}


# --- blinding -------------------------------------------------------------------------------

_TELLS = (
    (re.compile(r"\bgroup [A-F]\b", re.I), "group letter"),
    (re.compile(r"\b(scattered-source-of-truth|change-prone-file|enum-value-escape|"
                r"implicit-coupling|god-component|unstable-interface)\b"), "internal sign name"),
    (re.compile(r"\b(low|med|medium|high)\s+confidence\b", re.I), "confidence tier"),
    (re.compile(r"archagent", re.I), "tool name"),
)


def tells(text: str) -> list[str]:
    """Phrases that would reveal which arm wrote a report.

    The shipped guidance already tells writers to keep group letters, sign names and confidence tiers out
    of prose, which helps blinding — but it also means arm A is the one most likely to comply, so a judge
    could identify it by its *absence* of tells. Both directions are reported.
    """
    return sorted({label for rx, label in _TELLS if rx.search(text)})


@dataclass
class Blinded:
    opaque: str
    text: str


def blind(reports: dict[str, str], seed: int = 7) -> tuple[list[Blinded], dict[str, str]]:
    """`(shuffled reports, opaque -> arm)`. The mapping is returned separately so the caller can hand the
    reports to a judge without it."""
    rng = random.Random(seed)
    items = [(arm, text) for arm, text in sorted(reports.items())]
    rng.shuffle(items)
    out, manifest = [], {}
    for n, (arm, text) in enumerate(items, 1):
        opaque = f"report-{n}"
        out.append(Blinded(opaque=opaque, text=text))
        manifest[opaque] = arm
    return out, manifest


# --- ground truth ---------------------------------------------------------------------------

@dataclass
class TruthItem:
    finding_id: str
    repo: str
    subject: str
    expected: str            # "dismiss" | "confirm"
    because: str
    aliases: list[str] = field(default_factory=list)   # other ways a report may name it

    def named_in(self, text: str) -> bool:
        needles = [self.subject, *self.aliases]
        return any(n.lower() in text.lower() for n in needles if n)


def load_truth(path: Path) -> list[TruthItem]:
    data = tomllib.loads(path.read_text())
    return [TruthItem(**item) for item in data["item"]]


_DISMISS = re.compile(
    r"\b(dismiss(?:ed|es)?|not a (?:real )?(?:problem|defect|issue)|by design|intended|deliberate|"
    r"expected here|deliberately|deliberate choice|no action)\b", re.I)


def _mentions(text: str, truth: list[TruthItem]) -> list[tuple[int, str]]:
    low = text.lower()
    out: list[tuple[int, str]] = []
    for item in truth:
        for needle in [item.subject, *item.aliases]:
            if not needle:
                continue
            idx = low.find(needle.lower())
            while idx != -1:
                out.append((idx, item.finding_id))
                idx = low.find(needle.lower(), idx + 1)
    return out


def dismissed_items(text: str, truth: list[TruthItem], window: int = 400) -> set[str]:
    """Which findings the report dismisses, attributing each dismissal to the most recent finding named
    **before** it.

    Two weaker rules were tried first and both misattribute. A plain window credits one dismissal against
    every finding within a few hundred characters, which in a short report is all of them. *Nearest*
    mention fixes that but breaks on "…by design, dismissed. NextFinding.py — …", where the dismissal sits
    closer to the finding that follows it than to the one it is about.

    Preceding-mention is how prose actually reads: you name the thing, then say something about it. A
    dismissal with no finding named before it inside the window belongs to nothing and is dropped.
    """
    mentions = sorted(_mentions(text, truth))
    if not mentions:
        return set()
    out: set[str] = set()
    for m in _DISMISS.finditer(text):
        before = [(pos, fid) for pos, fid in mentions
                  if pos <= m.start() and m.start() - pos <= window]
        if before:
            out.add(max(before)[1])
    return out


def judged_dismissed(text: str, item: TruthItem, truth: list[TruthItem] | None = None,
                     window: int = 400) -> bool:
    """Whether the report dismisses *this* finding. Pass the full truth list so competing mentions can
    claim a dismissal that is nearer to them."""
    return item.finding_id in dismissed_items(text, truth or [item], window)


# --- objective scoring ------------------------------------------------------------------------

@dataclass
class ObjectiveScore:
    arm: str | None
    opaque: str
    ground_truth_correct: int
    ground_truth_total: int
    missed: list[str] = field(default_factory=list)
    cites_evidence: bool = False
    clustered: bool = False
    tells_present: list[str] = field(default_factory=list)

    @property
    def truth_rate(self) -> float | None:
        return (self.ground_truth_correct / self.ground_truth_total) if self.ground_truth_total else None

    def to_dict(self) -> dict:
        return {"arm": self.arm, "opaque": self.opaque,
                "ground_truth": f"{self.ground_truth_correct}/{self.ground_truth_total}",
                "truth_rate": None if self.truth_rate is None else round(self.truth_rate, 3),
                "missed": self.missed, "cites_evidence": self.cites_evidence,
                "clustered": self.clustered, "tells": self.tells_present}


_CITATION = re.compile(r"[\w/.-]+\.(?:py|ts|tsx|js|jsx|go|rb|java|kt|rs)(?::\d+)?")
_ROOT_HEADING = re.compile(r"^#{2,4}\s+\S", re.MULTILINE)


def score_objective(report: Blinded, truth: list[TruthItem], n_findings: int) -> ObjectiveScore:
    """What can be checked without judgement.

    The ground-truth half is the one that matters: the corpus pass labelled certain findings as intended
    families that a good report must **dismiss with a reason**, and others as real. Whether a report gets
    those right is checkable, not a matter of taste — which is what makes it usable as a gate.
    """
    dismissed_ids = dismissed_items(report.text, truth)
    correct, missed = 0, []
    for item in truth:
        if not item.named_in(report.text):
            missed.append(f"{item.subject} (not mentioned)")
            continue
        dismissed = item.finding_id in dismissed_ids
        if (item.expected == "dismiss") == dismissed:
            correct += 1
        else:
            missed.append(f"{item.subject} (expected {item.expected})")
    return ObjectiveScore(
        arm=None, opaque=report.opaque,
        ground_truth_correct=correct, ground_truth_total=len(truth), missed=missed,
        cites_evidence=len(set(_CITATION.findall(report.text))) >= 3,
        # clustering means fewer roots than findings — a report with a heading per finding has not clustered
        clustered=0 < len(_ROOT_HEADING.findall(report.text)) < max(2, n_findings),
        tells_present=tells(report.text),
    )


def unblind(scores: list[ObjectiveScore], manifest: dict[str, str]) -> list[ObjectiveScore]:
    for s in scores:
        s.arm = manifest.get(s.opaque)
    return scores

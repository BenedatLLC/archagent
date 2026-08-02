"""The judged half of the rubric (`docs/designs/evaluating-archagent.md` §9).

The deterministic half asks whether an artifact *conforms*: are the documents there, do the globs resolve,
does it drift. It cannot ask whether the artifact is any **good** — an artifact can score 1.0 while
describing the architecture wrongly, in prose nobody can follow, protected by invariants that catch
nothing. Those questions need a reader.

**Anchored descriptors, not a bare 1–5.** A scale without anchors measures the judge's mood: two runs
disagree, and neither can say why. Each criterion below states what a 1, a 3 and a 5 look like in terms a
reader can check against the artifact in front of them.

**Every score requires a citation.** A score with no `file:line` behind it is discarded rather than
averaged in. This is the same rule the spot-check applies to human labels, and it exists because the
failure mode here is fluent, confident, unfalsifiable prose — the thing a language model produces most
readily.

**These scores are uncalibrated until agreement with a human reviewer is measured** (§11). The findings
half of that calibration has been done and produced a sobering number: 68% agreement between an
independent reviewer and the person who built the checks, with errors in *both* directions. Until the
equivalent exists for these criteria, a judged score is reported with that caveat attached and never
gates anything (§13.2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SCALE = (1, 2, 3, 4, 5)
_CITATION = re.compile(r"[\w/.-]+\.(?:md|py|ts|tsx|js|jsx|go|rb|java|kt|rs)(?::\d+)?")


@dataclass
class Criterion:
    id: str
    label: str
    question: str
    anchors: dict[int, str]          # what 1, 3 and 5 look like
    evidence: str                    # what a citation must point at for this criterion
    second_run_only: bool = False


CRITERIA: list[Criterion] = [
    Criterion(
        id="accuracy",
        label="Accuracy",
        question=("Does the document describe the system that is actually there? Pick the five most "
                  "load-carrying claims and check each against the code."),
        anchors={
            1: "Claims are contradicted by the code, or describe an intended design that was never built.",
            3: ("Broadly right, with drift in the detail: a named component that has since been split, a "
                "flow missing a step that exists, a dependency described in the wrong direction."),
            5: ("Every checked claim holds. Where the code has a wrinkle the document does not cover, the "
                "document says so rather than implying completeness."),
        },
        evidence="the code that confirms or contradicts each claim you checked",
    ),
    Criterion(
        id="completeness",
        label="Completeness",
        question=("Is anything significant missing? Compare the subsystems described against what the "
                  "repository actually contains, and against what a newcomer would need."),
        anchors={
            1: "Major parts of the system are undescribed, or only the easy parts are covered.",
            3: ("The main subsystems are present but the seams between them are thin — you could not tell "
                "from this where a change in one lands in another."),
            5: ("A newcomer could locate any significant behaviour from the documents alone. Deliberate "
                "omissions are named as omissions."),
        },
        evidence="directories or modules with no corresponding description, or the document covering them",
    ),
    Criterion(
        id="prose",
        label="Prose clarity",
        question=("Judge against `writing-style.md`: purpose before mechanism, no undefined jargon, "
                  "self-contained sections, a concrete instance for every named abstraction, and plain "
                  "direct sentences."),
        anchors={
            1: ("Unreadable without already knowing the system: undefined internal names, noun stacks, "
                "sections that only make sense after reading three others."),
            3: ("Followable but effortful. Terms are mostly defined; some sections restate what the code "
                "already says, or name a pattern without grounding it in a real example."),
            5: ("A new engineer could learn a subsystem by reading its document straight through. Every "
                "abstraction is anchored to a concrete instance with a path."),
        },
        evidence="the passages you judged, quoted or cited by path and line",
    ),
    Criterion(
        id="diagrams",
        label="Diagram clarity",
        question=("Do the Mermaid lifecycle and flow diagrams convey something the prose does not, and "
                  "does each caption state what it shows *and* the takeaway?"),
        anchors={
            1: "Absent where they are needed, or present but wrong — states or steps the code does not have.",
            3: ("Correct but decorative: a diagram that restates the prose, or a caption that names the "
                "diagram without saying what to notice."),
            5: ("Each diagram earns its place — a state machine or sequence that would be laborious in "
                "prose — and its caption tells the reader what it is for and what to take away."),
        },
        evidence="the diagram block and the code implementing the states or steps it shows",
    ),
    Criterion(
        id="invariant_strength",
        label="Invariant logical strength",
        question=("Would each invariant actually catch a violation someone might plausibly commit? Or is "
                  "it vacuous — restating what the language, the types, or the framework already "
                  "guarantees?"),
        anchors={
            1: ("Vacuous or unfalsifiable: rules that cannot fail, or prose aspirations written as if "
                "they were checks."),
            3: ("Real rules, but narrow — they forbid one spelling of a mistake while leaving the "
                "obvious alternatives open."),
            5: ("Each rule forbids a class of mistake, is falsifiable, and you can describe the commit it "
                "would reject."),
        },
        evidence="for each invariant judged, the code it constrains and a plausible violation it would catch",
    ),
    Criterion(
        id="invariant_criticality",
        label="Invariant business criticality",
        question=("Do the invariants protect the things that would actually hurt if broken — data "
                  "integrity, security boundaries, money, correctness of the core flow — or do they "
                  "protect trivia?"),
        anchors={
            1: "Style rules and import trivia, while the parts that would cause real harm are unprotected.",
            3: ("A mix: some genuine boundaries protected, some obvious risks — a security boundary, a "
                "money path, a data-ownership rule — left uncovered."),
            5: ("The rules track where the harm is. Anything left unprotected is unprotected for a stated "
                "reason."),
        },
        evidence="the risky code path, and the invariant protecting it or the absence of one",
    ),
    Criterion(
        id="update_quality",
        label="Update quality",
        question=("Comparing the two revisions: are the changes reflected in the artifact, and is stale "
                  "content gone?"),
        anchors={
            1: "The artifact still describes the earlier revision; new subsystems are absent.",
            3: ("New material was added but old material was not removed, so the document now describes "
                "two systems at once."),
            5: "Changes are reflected and superseded content is gone or explicitly marked as historical.",
        },
        evidence="a change between the revisions, and the document text that does or does not reflect it",
        second_run_only=True,
    ),
]

BY_ID = {c.id: c for c in CRITERIA}


# --- the brief a judge works through ---------------------------------------------------------

def render_brief(artifact_path: str, repo: str, second_run: bool = False) -> str:
    crit = [c for c in CRITERIA if second_run or not c.second_run_only]
    lines = [
        f"# Architecture artifact review — {repo}",
        "",
        f"Artifact: `{artifact_path}/` (relative to the repository root)",
        "",
        "Score each criterion 1–5 against the anchors given. **A score with no citation is discarded**,",
        "so name the file and line you judged from — the failure mode here is fluent, confident prose",
        "with nothing behind it.",
        "",
        "Read the code, not only the documents. Several criteria ask whether the documents match the",
        "system, which cannot be answered from the documents alone.",
        "",
        "Where you are unsure, score `0` and say why. An honest gap is more useful than a guessed number,",
        "and `0` is excluded from the average rather than counted as a failure.",
        "",
        "---",
    ]
    for c in crit:
        lines += [
            "",
            f"## {c.id} — {c.label}",
            "",
            c.question,
            "",
            "| score | what it looks like |",
            "|---|---|",
            f"| 1 | {c.anchors[1]} |",
            f"| 3 | {c.anchors[3]} |",
            f"| 5 | {c.anchors[5]} |",
            "",
            f"*Cite:* {c.evidence}",
            "",
            "```",
            "score:",
            "evidence:",
            "why:",
            "```",
            "",
            "---",
        ]
    return "\n".join(lines) + "\n"


_BLOCK = re.compile(r"^##\s+([a-z_]+)\s+—", re.MULTILINE)
_FIELD = {k: re.compile(rf"^\s*{k}\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
          for k in ("score", "evidence", "why")}


def parse_brief(text: str) -> dict[str, dict]:
    """Read a completed review. Lenient about formatting, strict about the citation rule."""
    out: dict[str, dict] = {}
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    for block in blocks:
        m = re.match(r"([a-z_]+)\s+—", block)
        if not m or m.group(1) not in BY_ID:
            continue
        got = {k: (rx.findall(block) or [""])[0].strip() for k, rx in _FIELD.items()}
        raw = re.sub(r"[^0-9]", "", got["score"].split()[0] if got["score"] else "")
        if not raw:
            continue
        score = int(raw[0])
        if score == 0:
            out[m.group(1)] = {"score": None, "evidence": got["evidence"], "why": got["why"],
                               "discarded": "reviewer marked unsure"}
            continue
        if score not in SCALE:
            continue
        if not _CITATION.search(got["evidence"] + " " + got["why"]):
            # the rule that keeps this from measuring fluency
            out[m.group(1)] = {"score": None, "evidence": got["evidence"], "why": got["why"],
                               "discarded": "no file:line citation"}
            continue
        out[m.group(1)] = {"score": score, "evidence": got["evidence"], "why": got["why"]}
    return out


# --- the store ---------------------------------------------------------------------------------

@dataclass
class JudgedReview:
    repo: str
    rev: str
    judged_by: str
    dated: str
    scores: dict[str, dict] = field(default_factory=dict)

    @property
    def mean(self) -> float | None:
        vals = [s["score"] for s in self.scores.values() if s.get("score") is not None]
        return sum(vals) / len(vals) if vals else None

    @property
    def discarded(self) -> dict[str, str]:
        return {k: v["discarded"] for k, v in self.scores.items() if v.get("discarded")}

    def to_dict(self) -> dict:
        return {"repo": self.repo, "rev": self.rev, "judged_by": self.judged_by, "dated": self.dated,
                "mean": None if self.mean is None else round(self.mean, 2),
                "calibrated": False,
                "caveat": ("uncalibrated — no agreement with a human reviewer has been measured for these "
                           "criteria, so this number has unknown meaning and gates nothing"),
                "discarded": self.discarded, "scores": self.scores}


def save(path: Path, review: JudgedReview) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review.to_dict(), indent=2) + "\n")
    return path


def review_from(text: str, repo: str, rev: str, judged_by: str) -> JudgedReview:
    return JudgedReview(repo=repo, rev=rev, judged_by=judged_by or "(unrecorded)",
                        dated=date.today().isoformat(), scores=parse_brief(text))

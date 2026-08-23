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

# "partial" was not anticipated and a reviewer reached for it unprompted on 3 of 19 items, meaning "there
# is something real here, but not the thing the finding claims" — e.g. the escape exists but from a
# different enum than the one named. That is a distinct and useful verdict: counting it as confirm
# overstates precision, counting it as dismiss throws away a real defect, and dropping it (which the
# original parser did, silently) loses the most informative labels in the set.
VERDICTS = ("confirm", "dismiss", "partial", "unsure")
SCORE_VERDICTS = ("agree", "too-high", "too-low", "unsure")

#: The signal groups, so a round can be scoped to the ones with no evidence yet. Rounds so far have
#: covered E (`change-prone-file`, also validated predictively by the defect study) and F
#: (`scattered-source-of-truth`, `enum-value-escape`). B, C, D and A have never been labelled at all.
GROUPS: dict[str, tuple[str, ...]] = {
    "A": ("duplicated-source-of-truth", "shared-persistency", "service-intimacy", "shared-library"),
    "B": ("layer-inversion", "layer-skip", "unstable-dependency", "unstable-interface",
          "implicit-coupling", "extraneous-adjacent-connector"),
    "C": ("god-component", "cycle-subsystem", "cycle-service", "distributed-monolith"),
    "D": ("hardcoded-endpoint", "no-request-tracing", "trace-chain-gap", "permissive-origin",
          "server-side-fetch"),
    "E": ("change-prone-file",),
    "F": ("scattered-source-of-truth", "enum-value-escape"),
}


def signs_in(groups: str) -> tuple[str, ...]:
    """The signs belonging to a comma-separated group list, e.g. `"B,C"`.

    Refuses an unknown group rather than returning an empty tuple, which would silently generate a
    worksheet with nothing on it and read as "no findings left to label".
    """
    out: list[str] = []
    for g in (x.strip().upper() for x in groups.split(",") if x.strip()):
        if g not in GROUPS:
            raise ValueError(f"unknown group {g!r}; known groups are {', '.join(sorted(GROUPS))}")
        out += GROUPS[g]
    return tuple(out)


def evidence_is_usable(evidence: str) -> bool:
    """Is there enough here for a reviewer to reach a verdict without re-deriving the finding?

    **The guard that makes a group B/C round possible at all.** Those findings carry their reasoning in
    `detail` — *"extraction (infra) depends up on drift (domain)"*, *"4 subsystems depend on drift; it
    co-changes frequently with cli, evaluate, extraction"* — while group F carries it in a value set. The
    pinned corpus baselines store neither: they keep only the fields that must not change, so a B/C
    finding read from one is a pair of subsystem names and nothing else.

    A worksheet item like that is not a spot-check. It asks the reviewer to reconstruct the finding from
    scratch and then grade their own reconstruction, and whatever number comes back would describe that
    exercise. Better to refuse the item and say the source cannot supply it.

    The test is **whether anything beyond the subject names survived**, not how much prose there is. A
    first version required six words and rejected `god-component`'s `70/122 files (57%)` — which is the
    entire finding, is immediately judgeable, and is four words. Length was never the question.
    """
    return any(ln.strip().startswith(("- values:", "- measured:")) for ln in evidence.splitlines())


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


#: Per-signal reading instructions, emitted only for the signals actually on the sheet.
#:
#: This used to be one hardcoded paragraph about `change-prone-file`, which was right for the rounds that
#: existed and became actively misleading the moment a group B/C sheet was generated: it told a reviewer
#: to go read a file, when what a `layer-inversion` item needs is the two `**Tier:**` declarations the
#: finding compares.
_GUIDANCE: dict[str, str] = {
    "change-prone-file":
        "**change-prone-file** — the question is whether the file is genuinely absorbing special cases. "
        "Only reading it answers that; churn alone never does.",
    # The sentence that used to end this entry — "a test subsystem depending on the code it tests is what
    # tests are for" — was removed after round 2. The reviewer's `backend-tests` dismissal restated it
    # almost exactly, so that label measured this guidance rather than their reading. Round 3 puts seven
    # more inversions in front of a reviewer, four of them test packages, and the whole point is to find
    # out whether they reach that conclusion unprompted. Guidance may say what to check; it must not say
    # what to conclude.
    "layer-inversion":
        "**layer-inversion / layer-skip** — half of this claim lives in the architecture documents. "
        "`extraction (infra) depends up on drift (domain)` asserts three things: the two `**Tier:**` "
        "declarations in `subsystems/*.md`, and an import between them in the code. Check all three, "
        "and judge what the edge means for this system.",
    "cycle-subsystem":
        "**cycle-subsystem** — read the declared `**Connects:**` edges *and* the imports. A cycle "
        "recorded in an ADR as an accepted cost is still a true finding: `confirm`, with a note.",
    "god-component":
        "**god-component** — a share of files, from `**Covers:**`. The question is whether that "
        "subsystem is doing several unrelated jobs, or is one coherent thing that happens to be large.",
    "unstable-interface":
        "**unstable-interface** — combines a static fan-in with git co-change. Both halves are "
        "checkable: how many subsystems declare a dependency on it, and whether those files really do "
        "change together in the log.",
    "scattered-source-of-truth":
        "**scattered-source-of-truth** — the question is whether the copies can drift apart, and what "
        "breaks when they do. Constants frozen by an external standard cannot drift.",
    "enum-value-escape":
        "**enum-value-escape** — check that the literals really are the named enum's members, and not a "
        "different concept that happens to share strings.",
}
_GUIDANCE["layer-skip"] = _GUIDANCE["layer-inversion"]
_GUIDANCE["cycle-service"] = _GUIDANCE["cycle-subsystem"]


def _guidance(signs: list[str]) -> list[str]:
    """Reading notes for the signals on this sheet, and no others."""
    out: list[str] = []
    for text in dict.fromkeys(_GUIDANCE[s] for s in signs if s in _GUIDANCE):
        out += [f"- {text}", ""]
    return (["**Reading each kind:**", ""] + out) if out else []


#: The sheet names its own side file, so `ingest` can find the withheld claims however the returned file
#: has been renamed. Resolution used to be "swap the extension on whatever path you were given", which
#: quietly required the reviewer to hand back a file with the exact basename it was generated under —
#: and the two most natural things a person does are add their name to it and save it from the kit, where
#: it is called `worksheet.md`. Both broke it, and the error named a missing file rather than the rule.
SHEET_ID = re.compile(r"<!--\s*spotcheck-sheet:\s*([A-Za-z0-9._-]+)\s*-->")


def sheet_id(text: str) -> str:
    m = SHEET_ID.search(text)
    return m.group(1) if m else ""


def render_worksheet(items: list[dict], reviewer: str = "", sheet: str = "") -> tuple[str, dict]:
    """`(markdown, withheld)` — the sheet a person fills in, and the claims kept out of it.

    The withheld half is returned separately rather than hidden in a comment: a claim in the same file is
    a claim the reviewer can read.
    """
    lines = [
        "# archagent spot-check worksheet",
        "",
        f"<!-- spotcheck-sheet: {sheet or 'worksheet-' + date.today().isoformat()} -->",
        "",
        f"Reviewer: {reviewer or '(fill in)'}    Date: {date.today().isoformat()}",
        "",
        "**Rename this file however you like — just keep the comment line above it.** It is how the",
        "results are matched back to the run that produced them.",
        "",
        "For each item below, read the evidence and record a verdict. **The tool's own severity,",
        "confidence and recommendation are deliberately not shown** — they are held back so that this",
        "measures agreement with the code rather than with the tool's prior. They are revealed when the",
        "sheet is ingested.",
        "",
        "Verdicts: `confirm` (a real problem worth acting on) · `dismiss` (not a problem here, say why) ·",
        "`partial` · `unsure`. A one-line reason matters more than the verdict; it is what makes a",
        "disagreement diagnosable later, and `unsure` is a real answer — it is excluded from the precision",
        "denominator rather than counted as a dismissal.",
        "",
        "**`partial` means: something real is here, but not what the finding claims.** The escape exists "
        "but",
        "from a different enum than the one named; the coupling is real but between other modules. It was "
        "not",
        "an anticipated verdict — a reviewer reached for it unprompted on 3 of 10 items in round 1, and it",
        "carried the most information in the set. Counting those as `confirm` overstates precision and as",
        "`dismiss` throws away a real defect, so it is its own answer.",
        "",
        "**Two questions per item, in order.** First: *is the measurement true?* Then, only if it is: *is "
        "it",
        "a real problem worth acting on?* A true measurement can still be a non-finding, and saying which",
        "of the two failed is the difference between a bug in the check and a bug in its threshold.",
        "",
        "A finding that is **real but already accepted** — recorded in an ADR as a known cost — is a",
        "`confirm` with a note saying so. The signal did its job; dismissing it would teach this exercise",
        "that correct findings are wrong.",
        "",
        "The evidence below is a pointer, not a substitute for the code.",
        "",
    ]
    lines += _guidance([it.get("sign", "") for it in items])
    lines += ["---"]
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
        # "partial confirm" must be read before "confirm" or the prefix match would take the wrong one
        verdict = next((v for v in (*VERDICTS, *SCORE_VERDICTS) if raw.startswith(v)), "")
        if not verdict and "partial" in raw:
            verdict = "partial"
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
        mine = [l for l in labels if l.sign == sign]
        rated = [l for l in mine if l.verdict in ("confirm", "dismiss", "partial")]
        confirmed = sum(1 for l in rated if l.verdict == "confirm")
        partial = sum(1 for l in rated if l.verdict == "partial")
        strict_lo, strict_hi = wilson(confirmed, len(rated))
        lenient_lo, lenient_hi = wilson(confirmed + partial, len(rated))
        out[sign] = {
            "n": len(rated), "confirmed": confirmed, "partial": partial,
            "dismissed": sum(1 for l in rated if l.verdict == "dismiss"),
            # strict counts only full confirmations; lenient credits partials, where something real was
            # found but not what the finding claimed. Reporting one number would hide the difference.
            "precision_strict": (confirmed / len(rated)) if rated else None,
            "precision_lenient": ((confirmed + partial) / len(rated)) if rated else None,
            "ci95_strict": [round(strict_lo, 3), round(strict_hi, 3)],
            "ci95_lenient": [round(lenient_lo, 3), round(lenient_hi, 3)],
            "unsure": sum(1 for l in mine if l.verdict == "unsure")}
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

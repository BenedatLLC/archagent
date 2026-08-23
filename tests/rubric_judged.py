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
gates anything (§20.2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SCALE = (1, 2, 3, 4, 5)
#: Longest alternative first, and no word character may follow. Python's `|` is first-match, not
#: longest-match, so `ts|tsx` truncates `LogsTab.tsx` to `LogsTab.ts` and `js|json` truncates
#: `mcp.json` to `mcp.js` — then the file "does not exist" and a true citation is reported as invented.
#: Exactly the wrong direction for a check whose whole purpose is calling out fabrication.
_EXT = ("(?:" + "|".join(sorted(
    ("md", "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "go", "rb", "java", "kt", "rs",
     "toml", "json", "yaml", "yml", "sh", "sql", "tf"), key=len, reverse=True)) + r")(?![\w])")
_CITATION = re.compile(
    rf"[\w/.-]+\.{_EXT}(?:\s*(?::|,?\s+lines?\s+)\s*\d+(?:\s*[-–]\s*\d+)?)?")
_CITE_PARTS = re.compile(rf"([\w/.-]+\.{_EXT})(?:\s*(?::|,?\s+lines?\s+)\s*(\d+))?")


#: Framework names that look like filenames. A bounded, well-known set — §18 warns that pattern lists are
#: where overfitting lives, and the alternative here (guessing from capitalisation) would misfire on real
#: files like `App.jsx`. Reporting "Next.js — no such file" is noise that teaches readers to ignore the
#: check, which costs more than the list does.
_NOT_FILES = {"next.js", "node.js", "vue.js", "nuxt.js", "three.js", "d3.js", "express.js",
              "react.js", "ember.js", "backbone.js", "chart.js", "socket.js", "moment.js"}


def unresolved_citations(text: str, root: Path) -> list[str]:
    """Citations in `text` that do not point at anything: a missing file, or a line past its end.

    **A well-formed citation is not a true one.** The original rule asked only that a `file:line` be
    present, which a fabricated citation satisfies exactly as well as a real one — and fabricated
    citations are the specific failure this rubric exists to catch, since an artifact review is mostly
    unfalsifiable prose. The first review received cited `check.py` at line 1593 in a 248-line file, and
    an ADR under a filename that has never existed. Both read as diligence; both were invented. Checking
    that the path resolves and the line is in range costs a stat and catches this class outright.
    """
    bad = []
    for m in _CITE_PARTS.finditer(text):
        raw, line = m.group(1), m.group(2)
        if raw.lower() in _NOT_FILES:
            continue
        # A path outside the repo is not a claim about the repo. `~/.cursor/mcp.json` in a document about
        # an installer is a real thing at a real location, and resolving it against the checkout would
        # report it as invented. Only repo-relative citations are checkable here.
        if raw.startswith(("/", "~", "./..")) or text[max(0, m.start() - 1):m.start()] in ("~", "/"):
            continue
        p = root / raw
        # A bare basename may match in several places. That is a vague citation, not an invented one, so
        # it resolves if *any* candidate supports it — this check is for fabrication, and calling
        # sloppiness fabrication would train reviewers to distrust it.
        cands = [p] if p.is_file() else [
            h for h in root.rglob(Path(raw).name)
            if h.is_file() and not {".git", ".venv", "node_modules"} & set(h.parts)]
        if not cands:
            bad.append(f"{m.group(0).strip()} — no such file")
            continue
        if not line:
            continue
        lengths = [len(c.read_text(errors="replace").splitlines()) for c in cands]
        if int(line) > max(lengths):
            bad.append(f"{m.group(0).strip()} — file has {max(lengths)} lines")
    return bad


@dataclass
class Criterion:
    id: str
    label: str
    question: str
    anchors: dict[int, str]          # what 1, 3 and 5 look like
    evidence: str                    # what a citation must point at for this criterion
    second_run_only: bool = False
    #: "artifact" — what `describe` wrote. "evaluate" — what `evaluate` reported about it. Kept apart so
    #: the two means are versioned and compared separately; see `EVALUATE_RUBRIC_VERSION`.
    section: str = "artifact"


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

#: Bumped when the artifact criteria change in any way a score depends on. Recorded in the brief and
#: copied into the ledger's `rubric_version`, which was hand-typed until now — a version key entered by
#: hand can disagree with the brief it names, and the disagreement is invisible.
ARTIFACT_RUBRIC_VERSION = "brief-v3"

#: The `evaluate` half, versioned separately **so the artifact series survives**. Folding these criteria
#: into the artifact brief would bump `rubric_version`, and the ledger would then correctly refuse to put
#: any future round in a series with rounds 1 through 5 — right behaviour, expensive outcome. Two
#: sections, two version keys, two means, one brief, one run.
EVALUATE_RUBRIC_VERSION = "eval-v1"


#: How much a finding would matter if it is real, from a nitpick to something that could sink the project.
#:
#: **The middle three are verbatim the `investigate` ratings** (`archagent investigate --record --rating`),
#: so a rating collected here can be written straight into the artifact and compared with one produced by
#: a full investigation. The scale extends at both ends because those three do not cover what a reviewer
#: actually meets: a correct finding not worth anyone's time is not "minor", and a finding that will force
#: a rewrite is not "critical" in the same sense as one that already misbehaves.
#:
#: `0` is not a point on the scale. It is the escape hatch for a finding that describes nothing real, kept
#: separate so that "wrong" never averages in as "unimportant" — they are different failures and the fix
#: for each is different.
IMPACT_SCALE: dict[int, tuple[str, str]] = {
    0: ("not a finding", "The measurement is wrong, or it describes nothing that exists. Say which."),
    1: ("trivial", "Correct, and not worth anyone's time. You would close it without acting."),
    2: ("minor", "Untidy. Nothing depends on it, or it would fail loudly if it broke."),
    3: ("moderate", "A real maintenance hazard: the parts can drift apart and nothing would catch it."),
    4: ("critical", "It already misbehaves, or a plausible edit makes it misbehave *silently*."),
    5: ("project-threatening", "It blocks a change the project must make, or compounds until something "
                               "has to be rewritten."),
}


#: What `evaluate` reported, judged as a **report** rather than as a set of claims.
#:
#: The line these deliberately do not cross is whether a finding is *true*. That question needs the
#: reviewer not to have seen the tool's severity and confidence first — `spotcheck.py`'s entire design is
#: withholding them — and this brief displays every finding with its severity attached. Asking "are these
#: right?" here would produce a number that looks like precision and is agreement with our own prior.
#: Precision stays in the spot-check, where the blinding is handled; these three ask what can be asked in
#: the open.
EVALUATE_CRITERIA: list[Criterion] = [
    Criterion(
        id="finding_actionability",
        label="Finding actionability",
        question=("Take each finding in turn. Could you act on it — change something, or decide not to — "
                  "without redoing the analysis that produced it?"),
        anchors={
            1: ("Findings name a smell and a location and stop. You would have to re-derive the problem "
                "yourself before you could do anything about it."),
            3: ("The recommendation is generic advice that would fit any finding of that kind — 'reduce "
                "coupling', 'introduce an interface' — rather than advice about this code."),
            5: ("Each finding names the specific code, what about it is the problem, and what a fix would "
                "change. Enough to open a pull request, or to decide against one and say why."),
        },
        evidence="a finding, and the code it points at — say whether the two matched",
        section="evaluate",
    ),
    Criterion(
        id="finding_restraint",
        label="Restraint about what was established",
        question=("`evaluate`'s severity is mechanical: it counts files and commits, never consequences. "
                  "Does the report say only what it actually established?"),
        anchors={
            1: ("Findings assert consequences — this causes outages, this is a security hole — on "
                "evidence that is only a count."),
            3: ("Severity is stated without being labelled mechanical, so a reader takes HIGH to mean "
                "serious when it means large."),
            5: ("Mechanical severity is named as mechanical; findings whose consequences are unknown are "
                "marked for investigation rather than rated; and where a guard was found it is reported "
                "beside the risk instead of omitted."),
        },
        evidence="a severity or a claim in the report, and the evidence the report offers for it",
        section="evaluate",
    ),
    Criterion(
        id="finding_coverage_honesty",
        label="Honesty about what was not checked",
        question=("Can you tell from the report which checks did not run? A group that emitted nothing "
                  "for lack of metadata is indistinguishable, from the count alone, from a clean one."),
        anchors={
            1: ("An empty group reads as health. Nothing says which families never ran, or why."),
            3: ("Inactive families are listed, but the finding count could still be read as a complete "
                "inventory — a capped list or a failed history mine goes unmentioned."),
            5: ("Every family that could not run is named with its reason; a capped list says what it was "
                "capped from; and a failed history mine voids its signals loudly rather than quietly."),
        },
        evidence="the coverage or inactive section of the report, and a group whose silence it explains "
                 "or fails to explain",
        section="evaluate",
    ),
]

BY_ID = {c.id: c for c in [*CRITERIA, *EVALUATE_CRITERIA]}


# --- the brief a judge works through ---------------------------------------------------------

def render_brief(artifact_path: str, repo: str, second_run: bool = False,
                 tool: str = "", target_rev: str = "", findings: "object | None" = None) -> str:
    """The brief a reviewer fills in.

    Pass `findings` (a `findings.Capture`) to append the `evaluate` section. It is omitted entirely when
    no capture exists rather than included and left blank: an unanswered section is indistinguishable
    from a section the reviewer skipped, and the whole instrument turns on that distinction elsewhere.
    """
    crit = [c for c in CRITERIA if second_run or not c.second_run_only]
    lines = [
        f"# Architecture artifact review — {repo}",
        "",
        f"Artifact: `{artifact_path}/` (relative to the repository root)",
        f"Rubric: `{ARTIFACT_RUBRIC_VERSION}`"
        + (f" · evaluate section `{EVALUATE_RUBRIC_VERSION}`" if findings is not None else ""),
    ]
    if target_rev:
        lines.append(f"Target revision: `{target_rev}`")
    if tool:
        # Calibration round 4's artifact was generated by the working tree and reviewed against a build
        # from six weeks earlier that was missing four of the commands `describe` tells agents to run. The
        # reviewer correctly reported a command as unavailable and reasonably concluded the artifact was
        # stale. Naming the tool here is what stops that happening again (issue #13).
        lines += [
            f"Reviewed against: **{tool}**",
            "",
            "**Use that build.** This brief asks you to run archagent commands and check citations; a "
            "different build may not have the commands the artifact cites, and a command-not-found then "
            "reads as a stale document rather than as version skew.",
        ]
    lines += [
        "",
        "Score each criterion 1–5 against the anchors given. **A score with no citation is discarded**,",
        "so name the file and line you judged from — the failure mode here is fluent, confident prose",
        "with nothing behind it.",
        "",
        "**Citations are checked, not just counted.** The path must exist and the line must be within the",
        "file. A criterion whose citations all fail to resolve is discarded the same way an uncited one is.",
        "If you are working from memory rather than an open file, say so and score `0` instead.",
        "",
        "Write as much as you need under `why:` — it is read to the next `score:`/`evidence:`/`why:` key,",
        "so indented lists, per-claim breakdowns and multiple citations all survive.",
        "",
        "**Formatting is lenient, and you can check it before you hand this back.** A fenced block, bare",
        "`score:` lines, bold `**score:**` labels, or the score in the heading (`## accuracy — Score: 4`)",
        "all parse. To be certain yours reads, run:",
        "",
        "    python scripts/selfeval.py check-brief <this-file> --project <the-checkout>",
        "",
        "It reports which criteria were read and which citations resolve. It shows you no one else's",
        "review — deliberately, because a filled-in example would anchor the score you give, the kind of",
        "problem you look for, and how long you write.",
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
    if findings is not None:
        lines += _evaluate_section(findings)
    return "\n".join(lines) + "\n"


def _evaluate_section(cap) -> list[str]:
    """The `evaluate` half of the brief: the findings, then three questions about the report.

    The findings are shown **with** their severities, which is exactly why none of the three questions
    asks whether a finding is correct. A reviewer who has read `HIGH` cannot then give an unanchored
    judgement of the same finding's truth, and pretending otherwise would launder our own prior into a
    precision figure. The blinded version of that question lives in the spot-check.
    """
    lines = [
        "",
        f"# `archagent evaluate` — the report on {cap.repo} @ {cap.target_rev}",
        "",
        f"Produced by **{cap.archagent}** on {cap.captured_at}.",
        "",
        "**You are judging the report, not adjudicating the findings.** Whether each finding is *true* is",
        "a separate exercise, run blind — you have been shown the severities, so an opinion formed here",
        "would measure agreement with the tool rather than the tool's accuracy. The three questions below",
        "ask whether a reader could act on this, whether it claims more than it showed, and whether it is",
        "clear about what never ran.",
        "",
        f"## The findings ({len(cap.findings)})",
        "",
        "**Rate each one for impact** in the block beneath it, and say why in a sentence. This is the "
        "judgement",
        "the tool refuses to make: `evaluate`'s own severity counts files and commits, never consequences.",
        "",
        "| | |",
        "|---|---|",
    ] + [f"| **{n} — {label}** | {desc} |" for n, (label, desc) in sorted(IMPACT_SCALE.items())] + [
        "",
        "`0` is not the bottom of the scale, it is a different answer: the finding describes nothing real. "
        "Keeping",
        "it separate matters, because *wrong* and *unimportant* are different failures with different "
        "fixes.",
        "",
        "**A finding can be real and still be a 1.** Saying so is the most useful thing you can do here — "
        "a tool",
        "that reports true trivia trains people to skim, and no amount of accuracy recovers from that.",
        "",
    ]
    if not cap.findings:
        lines += ["_None reported._ That is a result, not a blank: read the coverage list below before "
                  "concluding anything from it.", ""]
    for f in cap.findings:
        subjects = ", ".join(f.get("subjects", [])) or "—"
        lines += [
            f"### `{f['sign']}` — {f.get('title', '')}  ",
            f"**group** {f.get('group', '?')} · **severity** {f.get('severity', '?')} (mechanical) · "
            f"**confidence** {f.get('confidence', '?')} · **id** `{f['id']}`  ",
            f"**subjects:** {subjects}  ",
            "",
            f.get("detail", "") or "_no detail recorded_",
            "",
            f"*Recommended:* {f.get('recommendation', '') or '_none given_'}",
            "",
            "```",
            "impact:",
            "why:",
            "```",
            "",
        ]
    lines += ["## What did not run", ""]
    if cap.inactive:
        for e in cap.inactive:
            # An empty `signs` means degraded rather than absent — the family still emits, on weaker
            # evidence. Printing that under a "covers:" label would read as "covers nothing", which is
            # the opposite of what it means.
            note = (f"covers: {', '.join(e['signs'])}" if e.get("signs")
                    else "still emitting, on weaker evidence")
            lines.append(f"- **{e['family']}** — {e['reason']}  \n  {note}")
    else:
        lines.append("- _Nothing was reported as inactive._")
    if cap.truncated:
        lines += ["", "Capped output:"]
        lines += [f"- {t[0]}: showing {t[1]} of {t[2]}" for t in cap.truncated]
    if cap.mining_failed:
        lines += ["", "**History mining FAILED — every history-based signal above is void.**"]
    for c in cap.cautions:
        lines.append(f"- caution: {c}")
    lines += ["", "---"]
    for c in EVALUATE_CRITERIA:
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
    return lines


_FIELDS = ("score", "evidence", "why")
_KEY = re.compile(rf"^[ \t>*-]*({'|'.join(_FIELDS)})\s*:[ \t]*", re.IGNORECASE | re.MULTILINE)


def _fields(block: str) -> dict[str, str]:
    """Pull `score:`/`evidence:`/`why:` out of one criterion's section.

    **Each field runs until the next field key, not to the end of its line.** Reviewers write the
    reasoning that matters — the claim-by-claim check, the citations backing it — as an indented block
    under `why:`, and a line-scoped read throws all of it away. That is not a cosmetic loss: the citation
    rule below then sees a bare summary sentence, finds no `file:line` in it, and discards a score that
    was in fact cited half a page deep. A whole review can come back "uncited" while being the most
    thoroughly evidenced one received.
    """
    fence = re.search(r"```[^\n]*\n(.*?)```", block, re.DOTALL)
    body = fence.group(1) if fence else block
    keys = [(m.group(1).lower(), m.end(), m.start()) for m in _KEY.finditer(body)]
    got = {k: "" for k in _FIELDS}
    for i, (name, value_at, _) in enumerate(keys):
        end = keys[i + 1][2] if i + 1 < len(keys) else len(body)
        if not got[name]:                      # first occurrence wins
            got[name] = body[value_at:end].strip()
    return got


def parse_brief(text: str, root: Path | None = None) -> dict[str, dict]:
    """Read a completed review. Lenient about formatting, strict about the citation rule.

    Pass `root` to check that citations *resolve* — see `unresolved_citations`. Without it the rule
    only checks that a citation is well formed, which a fabricated one also is.
    """
    out: dict[str, dict] = {}
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    for block in blocks:
        m = re.match(r"([a-z_]+)\s+—", block)
        if not m or m.group(1) not in BY_ID:
            continue
        got = _fields(block)
        raw = re.sub(r"[^0-9]", "", got["score"].split()[0] if got["score"] else "")
        if not raw:
            # The score may live in the heading — `## accuracy — Score: 5` — rather than in a field.
            # Two of the first three reviews received were unreadable for a different formatting reason
            # each time, and in both cases the content was fine. A parser that rejects a well-evidenced
            # review over where a number was typed is measuring the reviewer's guess at our format.
            m_head = re.search(r"score\s*[:=]\s*(\d)", block.split("\n", 1)[0], re.IGNORECASE)
            raw = m_head.group(1) if m_head else ""
        if not raw:
            continue
        score = int(raw[0])
        rec = {"score": score, "evidence": got["evidence"], "why": got["why"]}
        cited = got["evidence"] + " " + got["why"]
        if score == 0:
            out[m.group(1)] = {**rec, "score": None, "discarded": "reviewer marked unsure"}
            continue
        if score not in SCALE:
            continue
        if not _CITATION.search(cited):
            # the rule that keeps this from measuring fluency
            out[m.group(1)] = {**rec, "score": None, "discarded": "no file:line citation"}
            continue
        if root is not None:
            bad = unresolved_citations(cited, root)
            rec["unresolved"] = bad
            if bad and len(bad) == len(set(_CITATION.findall(cited))):
                out[m.group(1)] = {**rec, "score": None,
                                   "discarded": f"no citation resolves ({'; '.join(bad[:3])})"}
                continue
        out[m.group(1)] = rec
    return out


# --- the store ---------------------------------------------------------------------------------

@dataclass
class JudgedReview:
    repo: str
    rev: str
    judged_by: str
    dated: str
    scores: dict[str, dict] = field(default_factory=dict)

    def _mean(self, section: str) -> float | None:
        vals = [s["score"] for cid, s in self.scores.items()
                if s.get("score") is not None and BY_ID[cid].section == section]
        return sum(vals) / len(vals) if vals else None

    @property
    def mean(self) -> float | None:
        """The **artifact** mean, and only the artifact.

        The evaluate criteria are excluded rather than averaged in. Mixing them would silently redefine
        what this number measures while leaving its name and its ledger column unchanged, which is the
        same shape as the three calibration means that formed a rising line across three different
        briefs — the mistake the ledger exists to make impossible.
        """
        return self._mean("artifact")

    @property
    def evaluate_mean(self) -> float | None:
        return self._mean("evaluate")

    def _coverage(self, section: str) -> tuple[int, int]:
        got = {cid: s for cid, s in self.scores.items() if BY_ID[cid].section == section}
        return sum(1 for s in got.values() if s.get("score") is not None), len(got)

    @property
    def discarded(self) -> dict[str, str]:
        return {k: v["discarded"] for k, v in self.scores.items() if v.get("discarded")}

    @property
    def coverage(self) -> tuple[int, int]:
        """(scores kept, criteria answered) for the artifact half — the denominator its mean is over."""
        return self._coverage("artifact")

    @property
    def evaluate_coverage(self) -> tuple[int, int]:
        return self._coverage("evaluate")

    @property
    def unresolved(self) -> dict[str, list[str]]:
        return {k: v["unresolved"] for k, v in self.scores.items() if v.get("unresolved")}

    def to_dict(self) -> dict:
        kept, answered = self.coverage
        caveat = ("uncalibrated — no agreement with a human reviewer has been measured for these "
                  "criteria, so this number has unknown meaning and gates nothing")
        if answered and kept < answered:
            # a mean over a minority of the review is not a score of the artifact, and read without this
            # it looks like one — a low number reads as "judged harshly", not "mostly discarded"
            caveat += (f"; and it averages {kept} of {answered} answered criteria — the rest were "
                       f"discarded, so it is not a score of the whole artifact")
        e_kept, e_answered = self.evaluate_coverage
        out = {"repo": self.repo, "rev": self.rev, "judged_by": self.judged_by, "dated": self.dated,
               "rubric_version": ARTIFACT_RUBRIC_VERSION,
               "mean": None if self.mean is None else round(self.mean, 2),
               "scored": kept, "answered": answered,
               "calibrated": False, "caveat": caveat,
               "unresolved": self.unresolved, "discarded": self.discarded, "scores": self.scores}
        if e_answered:
            # Only present when the evaluate section was actually answered. An `evaluate_mean` of null
            # sitting beside a real one in the record invites averaging the two rounds, and a section
            # nobody was asked about must not look like a section nobody could score.
            out |= {"evaluate_rubric_version": EVALUATE_RUBRIC_VERSION,
                    "evaluate_mean": None if self.evaluate_mean is None
                    else round(self.evaluate_mean, 2),
                    "evaluate_scored": e_kept, "evaluate_answered": e_answered}
        return out


def save(path: Path, review: JudgedReview) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review.to_dict(), indent=2) + "\n")
    return path


def review_from(text: str, repo: str, rev: str, judged_by: str,
                root: Path | None = None) -> JudgedReview:
    return JudgedReview(repo=repo, rev=rev, judged_by=judged_by or "(unrecorded)",
                        dated=date.today().isoformat(), scores=parse_brief(text, root))


# --- per-finding impact ratings ----------------------------------------------------------------

_FINDING_ID = re.compile(r"\*\*id\*\*\s*`([^`]+)`")
_IMPACT = re.compile(r"^[ \t>*-]*impact\s*:[ \t]*(\S+)", re.IGNORECASE | re.MULTILINE)


def parse_impacts(text: str) -> dict[str, dict]:
    """`{finding_id: {"impact": int, "why": str}}` from a completed brief.

    Unanswered findings are absent rather than defaulted. A missing rating is missing data — averaging it
    in as a zero would read every skipped item as "not a finding", which is the strongest verdict on the
    scale and the one least likely to be meant.

    Split by the `###` finding headings rather than parsed as one blob, so a `why:` running to several
    lines cannot swallow the next finding's rating.
    """
    out: dict[str, dict] = {}
    for block in re.split(r"^###\s+", text, flags=re.MULTILINE)[1:]:
        m = _FINDING_ID.search(block)
        if not m:
            continue
        got = _fields(block)                      # reuses the lenient score/evidence/why reader
        raw = _IMPACT.search(block)
        if not raw:
            continue
        digits = re.sub(r"[^0-9]", "", raw.group(1))
        if not digits or int(digits[0]) not in IMPACT_SCALE:
            continue
        out[m.group(1)] = {"impact": int(digits[0]), "why": got["why"].strip()}
    return out


def impact_summary(ratings: dict[str, dict], total: int) -> dict:
    """What a set of impact ratings says, with the denominators that make it readable.

    Reports the **distribution**, not a mean. A mean over a scale whose zero means "not a finding" is
    meaningless — one wrong finding and one project-threatening one do not average to "moderate" — and the
    shape is the thing anyone would act on: a tool reporting mostly 1s has a different problem from one
    reporting mostly 0s.
    """
    counts = {n: 0 for n in IMPACT_SCALE}
    for r in ratings.values():
        counts[r["impact"]] += 1
    rated = len(ratings)
    return {
        "rated": rated,
        "unrated": max(0, total - rated),
        "counts": counts,
        "not_a_finding": counts[0],
        # Everything a reader would act on. The line between 2 and 3 is where "untidy" becomes "this can
        # break something", and it is the number that decides whether the signal earns its place.
        "worth_acting_on": sum(counts[n] for n in (3, 4, 5)),
        "noise": counts[0] + counts[1],
    }

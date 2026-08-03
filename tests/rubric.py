"""The deterministic half of the self-evaluation rubric (`docs/designs/evaluating-archagent.md` §9).

Half the rubric is machine-checkable and half needs judgement. This is the machine half: cheap,
reproducible, and impossible to talk into a good score. It is useful on its own — it needs no agent and no
model — and it is what the judged half will later be calibrated against.

**Every graded criterion is paired with a counter-criterion.** §13.3 requires this, and the two examples
it gives are both live here:

- *Coverage* — the share of files claimed by some subsystem — is maximised by writing `**Covers:** src/**`
  in a single document. Perfect score, no architecture described. So coverage is paired with
  **concentration**: how much of the codebase one subsystem claims.
- *Drift near zero* is maximised by writing documents so vague that nothing can contradict them. So it is
  paired with **specificity**: how many falsifiable claims the artifact actually makes. An artifact that
  cannot drift because it says nothing scores badly, not perfectly.

A criterion without its pair is a target, not a diagnostic.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- the scorecard ------------------------------------------------------------------------

@dataclass
class Check:
    id: str
    label: str
    score: float | None          # 0.0-1.0, or None when the check does not apply here
    detail: str
    gate: bool = False           # a failed gate invalidates the judged half of the rubric

    @property
    def passed(self) -> bool | None:
        return None if self.score is None else self.score >= 0.999


@dataclass
class Scorecard:
    repo: str
    rev: str
    checks: list[Check] = field(default_factory=list)

    def add(self, *checks: Check) -> None:
        self.checks.extend(checks)

    def get(self, check_id: str) -> Check | None:
        return next((c for c in self.checks if c.id == check_id), None)

    @property
    def gates_failed(self) -> list[str]:
        return [c.id for c in self.checks if c.gate and c.score is not None and c.score < 0.999]

    @property
    def deterministic_score(self) -> float | None:
        """Mean of the applicable criteria. `None` when nothing applied — which is not a zero, and the
        distinction matters: an artifact that could not be scored is not an artifact that scored badly."""
        scored = [c.score for c in self.checks if c.score is not None]
        return sum(scored) / len(scored) if scored else None

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "rev": self.rev,
            "deterministic_score": (None if self.deterministic_score is None
                                    else round(self.deterministic_score, 3)),
            "gates_failed": self.gates_failed,
            "checks": [{"id": c.id, "label": c.label, "gate": c.gate,
                        "score": None if c.score is None else round(c.score, 3),
                        "detail": c.detail} for c in self.checks],
        }


# --- ADL conformance ----------------------------------------------------------------------

REQUIRED = ("constitution.md", "invariants.md", "index.md")
_COVERS = re.compile(r"^\s*\*\*\s*Covers\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_TRACEBACK = re.compile(r"Traceback \(most recent call last\)|^\s*File \"", re.MULTILINE)


def _arch(root: Path, arch_dir: str) -> Path:
    return root / arch_dir


def check_required_documents(root: Path, arch_dir: str) -> Check:
    arch = _arch(root, arch_dir)
    if not arch.is_dir():
        return Check("adl.required", "Required ADL documents present", 0.0,
                     f"no {arch_dir}/ directory at all", gate=True)
    missing = [n for n in REQUIRED if not (arch / n).is_file()]
    subs = list((arch / "subsystems").glob("*.md")) if (arch / "subsystems").is_dir() else []
    subs = [s for s in subs if not s.name.endswith("_TEMPLATE.md")]
    if missing or not subs:
        gaps = ([f"missing {', '.join(missing)}"] if missing else []) + \
               ([] if subs else ["no subsystem documents"])
        return Check("adl.required", "Required ADL documents present", 0.0, "; ".join(gaps), gate=True)
    return Check("adl.required", "Required ADL documents present", 1.0,
                 f"{len(REQUIRED)} core documents + {len(subs)} subsystem doc(s)", gate=True)


def check_covers_resolve(root: Path, arch_dir: str, source_files: set[str]) -> Check:
    """Every `**Covers:**` glob must match at least one real file. A glob that matches nothing is a claim
    about code that is not there."""
    globs = _all_covers(root, arch_dir)
    if not globs:
        return Check("adl.covers", "Covers globs resolve", None, "no **Covers:** declared")
    dangling = [g for g in globs if not _matches(root, g)]
    score = 1.0 - len(dangling) / len(globs)
    detail = f"{len(globs) - len(dangling)}/{len(globs)} resolve"
    if dangling:
        detail += f"; dangling: {', '.join(sorted(dangling)[:4])}"
    return Check("adl.covers", "Covers globs resolve", score, detail)


def _all_covers(root: Path, arch_dir: str) -> list[str]:
    out: list[str] = []
    subs = _arch(root, arch_dir) / "subsystems"
    if not subs.is_dir():
        return out
    for doc in sorted(subs.glob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        for m in _COVERS.finditer(doc.read_text(errors="replace")):
            out += [g.strip().strip("`") for g in re.split(r"[,\s]+", m.group(1).strip()) if g.strip()]
    return out


def _matches(root: Path, glob: str) -> bool:
    try:
        return any(root.glob(glob))
    except (OSError, ValueError):
        return False


# --- coverage, paired with concentration --------------------------------------------------

def check_coverage(root: Path, arch_dir: str, source_files: set[str]) -> tuple[Check, Check]:
    """Share of source files claimed, and how evenly the claims are spread.

    A single `**Covers:** src/**` scores 1.0 on share and 0.0 on concentration. Reporting only the first
    would reward exactly the artifact that describes nothing.
    """
    per_sub = _covered_per_subsystem(root, arch_dir)
    claimed: set[str] = set()
    for files in per_sub.values():
        claimed |= files
    claimed &= source_files
    if not source_files:
        return (Check("coverage.share", "Source files covered", None, "no source files found"),
                Check("coverage.concentration", "Coverage is spread across subsystems", None, ""))

    share = len(claimed) / len(source_files)
    share_check = Check("coverage.share", "Source files covered", share,
                        f"{len(claimed)}/{len(source_files)} files claimed by {len(per_sub)} subsystem(s)")

    if not per_sub:
        return share_check, Check("coverage.concentration", "Coverage is spread across subsystems",
                                  None, "nothing claimed")
    biggest = max((len(f & source_files) for f in per_sub.values()), default=0)
    dominance = biggest / len(claimed) if claimed else 1.0
    # one subsystem owning everything is the `Covers: src/**` degenerate case; owning a normal share is fine
    score = 1.0 if len(per_sub) > 1 and dominance <= 0.5 else max(0.0, 1.0 - dominance)
    return share_check, Check(
        "coverage.concentration", "Coverage is spread across subsystems", score,
        f"largest subsystem holds {dominance:.0%} of claimed files across {len(per_sub)} subsystem(s)")


def _covered_per_subsystem(root: Path, arch_dir: str) -> dict[str, set[str]]:
    subs = _arch(root, arch_dir) / "subsystems"
    out: dict[str, set[str]] = {}
    if not subs.is_dir():
        return out
    for doc in sorted(subs.glob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        files: set[str] = set()
        for m in _COVERS.finditer(doc.read_text(errors="replace")):
            for g in re.split(r"[,\s]+", m.group(1).strip()):
                g = g.strip().strip("`")
                if not g:
                    continue
                try:
                    files |= {p.relative_to(root).as_posix() for p in root.glob(g) if p.is_file()}
                except (OSError, ValueError):
                    pass
        out[doc.stem] = files
    return out


# --- self-consistency, paired with specificity --------------------------------------------

def check_drift(root: Path, arch_dir: str) -> Check:
    """A fresh artifact that already disagrees with the code is a describe bug."""
    out = _run([*ARCHAGENT, "drift", "--project", str(root), "--json"])
    if out is None:
        return Check("consistency.drift", "Artifact agrees with the code", 0.0, "drift failed to run")
    data = json.loads(out)
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    total = sum(counts.values())
    score = 1.0 if total == 0 else max(0.0, 1.0 - total / 20)
    worst = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v)
    return Check("consistency.drift", "Artifact agrees with the code", score,
                 f"{total} drift item(s)" + (f" ({worst})" if worst else ""))


MIN_CLAIMS = 8          # even a tiny project should make this many checkable statements
CLAIMS_PER_ROOT_FILE = 2.0
MAX_CLAIMS = 120        # past this the target stops being a floor test and becomes busywork


def expected_claims(n_source_files: int) -> int:
    """How many falsifiable claims an artifact for a codebase this size ought to make.

    Grows with the **square root** of the file count, not linearly: subsystems aggregate, so describing
    ten times the code does not take ten times the claims. A flat constant — which this was — asks the
    same of a 20-file project and a 10,000-file monorepo, so it is either trivial for one or negligible
    for the other.

        20 files ->   8 claims (the floor)
       200 files ->  28
     1,700 files ->  82
    10,000 files -> 120 (the cap)

    The constants are still chosen rather than measured. What has changed is that the *shape* is now
    defensible; the calibration is not, and needs real artifacts of known quality to score.
    """
    if not n_source_files:
        return MIN_CLAIMS
    scaled = round(CLAIMS_PER_ROOT_FILE * math.sqrt(n_source_files))
    return int(min(MAX_CLAIMS, max(MIN_CLAIMS, scaled)))


# One line of metadata is cheap; a `**Covers:**` glob that actually partitions the codebase is not, and
# an invariant is dearer still. Counting raw marker occurrences let six annotated subsystems contribute
# 18 of 27 claims — the score was mostly measuring how many one-line annotations someone had typed. So
# claims are grouped into three kinds and **no kind may satisfy more than half the target**: reaching a
# full score requires at least two of them.
CATEGORY_CAP = 0.5

_TIER_SVC = re.compile(r"\*\*\s*(?:Service|Tier)\s*:?\s*\*\*", re.IGNORECASE)
_CONNECTS = re.compile(r"^\s*\*\*\s*(?:Connects|Depends-on)\s*:?\s*\*\*\s*[:：]?\s*(.+)$",
                       re.IGNORECASE | re.MULTILINE)
_CONFIG = re.compile(r"^\s*\*\*\s*Config\s*:?\s*\*\*\s*[:：]?\s*(.+)$",
                     re.IGNORECASE | re.MULTILINE)


def claim_counts(root: Path, arch_dir: str) -> dict[str, int]:
    """Falsifiable claims by kind, counted at the granularity each is actually checked at.

    A `**Config:** A, B, C` line is three claims, not one — `drift` reports each key separately. A
    `**Connects:** a via sync-call, b via async-event` line is two edges. Counting either as one made the
    granularity depend on how the author happened to punctuate.
    """
    arch = _arch(root, arch_dir)
    if not arch.is_dir():
        return {"covers": 0, "metadata": 0, "invariants": 0}
    text = "\n".join(p.read_text(errors="replace") for p in arch.rglob("*.md"))
    edges = sum(len([x for x in re.split(r"[,\s]*,[,\s]*", m.group(1)) if x.strip()])
                for m in _CONNECTS.finditer(text))
    keys = sum(len([x for x in re.split(r"[,\s]+", m.group(1)) if x.strip()])
               for m in _CONFIG.finditer(text))
    inv = arch / "invariants.md"
    rows = len([ln for ln in inv.read_text(errors="replace").splitlines()
                if ln.strip().startswith("|") and re.search(r"\|\s*(active|proposed)\s*\|", ln, re.I)]) \
        if inv.is_file() else 0
    return {"covers": len(_all_covers(root, arch_dir)),
            "metadata": len(_TIER_SVC.findall(text)) + edges + keys,
            "invariants": rows}


def check_specificity(root: Path, arch_dir: str, n_source_files: int = 0) -> Check:
    """How many *falsifiable* claims the artifact makes, against a target scaled to the codebase.

    The counter-criterion to drift. Documents vague enough to be undisprovable score a perfect zero on
    drift; this is what stops that from looking like success. Counted: Covers globs, typed metadata, and
    invariant rows — every one of which `drift` or `check` can contradict.
    """
    if not _arch(root, arch_dir).is_dir():
        return Check("artifact.specificity", "Artifact makes falsifiable claims", 0.0, "no artifact")
    counts = claim_counts(root, arch_dir)
    target = expected_claims(n_source_files)
    cap = max(1, round(target * CATEGORY_CAP))
    counted = {k: min(v, cap) for k, v in counts.items()}
    claims = sum(counted.values())
    capped = [k for k, v in counts.items() if v > cap]
    detail = (f"{claims} counted claim(s) against a target of {target} for {n_source_files} source "
              f"file(s): " + ", ".join(f"{k} {counts[k]}" for k in ("covers", "metadata", "invariants")))
    if capped:
        detail += f"; capped at {cap} each: {', '.join(capped)}"
    return Check("artifact.specificity", "Artifact makes falsifiable claims",
                 min(1.0, claims / target), detail)


def check_orientation(root: Path, arch_dir: str) -> Check:
    """Can a newcomer enter the artifact at all: a system map, and prose before the catalog.

    Both are already required — `describe` step 8(b) mandates the Mermaid flowchart and ships an
    `index.md` with the markers pre-placed. archagent's own artifact had neither, and every check passed,
    because nothing looked. A mandated step with no verification is a step that silently stops happening.

    The map is the one part scored strictly, since `archagent graph --write` generates it from metadata
    already gathered — there is no excuse for its absence and no judgement involved in seeing it.
    """
    index = _arch(root, arch_dir) / "index.md"
    if not index.is_file():
        return Check("artifact.orientation", "Artifact is enterable", 0.0, "no index.md")
    text = index.read_text(errors="replace")
    body = re.split(r"^\s*\|", text, maxsplit=1, flags=re.MULTILINE)[0]
    # diagram source is not prose: a flowchart above the table would otherwise satisfy both halves at once
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    have = {
        "system map": "```mermaid" in text,
        # a heading, then the table, tells a reader nothing about what they are looking at
        "prose before the catalog": len([ln for ln in body.splitlines()
                                         if ln.strip() and not ln.startswith(("#", "<!--", "-", "*"))]) >= 3,
    }
    missing = [k for k, ok in have.items() if not ok]
    return Check("artifact.orientation", "Artifact is enterable", sum(have.values()) / len(have),
                 "system map and an entry narrative present" if not missing
                 else "missing: " + ", ".join(missing))


# --- the tools themselves ------------------------------------------------------------------

def check_commands_clean(root: Path) -> Check:
    """Every command exits cleanly and prints no traceback. Cheap, and it catches the case where a
    scorecard would otherwise be assembled from broken runs."""
    failures = []
    for cmd in ([*ARCHAGENT, "evaluate", "--project", str(root), "--json"],
                [*ARCHAGENT, "drift", "--project", str(root), "--json"],
                [*ARCHAGENT, "lint-docs", "--project", str(root)]):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        blob = proc.stdout + proc.stderr
        if proc.returncode != 0 or _TRACEBACK.search(blob):
            failures.append(f"{cmd[len(ARCHAGENT)]} (rc={proc.returncode})")
    score = 1.0 - len(failures) / 3
    return Check("tools.clean", "Commands run without error", score,
                 "all clean" if not failures else "failed: " + ", ".join(failures), gate=True)


_IAC = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "Procfile")


def _has_services(root: Path) -> bool:
    """Does this repo deploy as more than one process? Family A has nothing to measure if not."""
    return (any((root / n).is_file() for n in _IAC)
            or any(root.glob("k8s/**/*.y*ml")) or any(root.glob("deploy/**/*.y*ml")))


def check_evaluate_coverage(root: Path) -> Check:
    """How much of `evaluate` actually measured anything here. Inactive families are not findings-free;
    they are unmeasured, and an artifact that leaves most of them inactive is under-specified.

    **Only families the artifact could activate are counted.** The original version counted every inactive
    family, which measured the repository rather than the artifact:

    - Family E is inactive when no bug-fix commit convention could be learned from the history. No edit to
      any document changes that, so charging the artifact for it is a category error — and it penalises a
      young repository permanently.
    - Family A needs `**Service:**` on two or more subsystems. On a single-process tool there are no
      services, and declaring some to satisfy the rubric would be writing a false document to raise a
      score. That is the §13.3 failure mode arriving through the front door.

    Excused families are named in the detail rather than dropped silently, because "not applicable here"
    and "we chose not to measure it" must not look the same to a reader.
    """
    out = _run([*ARCHAGENT, "evaluate", "--project", str(root), "--json"])
    if out is None:
        return Check("evaluate.coverage", "Evaluate signal families active", 0.0, "evaluate failed to run")
    data = json.loads(out)
    counted, excused = [], []
    for fam in data.get("inactive", []):
        name = str(fam.get("family", ""))
        letter = name[:1]
        if letter == "E":
            excused.append(f"{letter} (learned from history, not declarable)")
        elif letter == "A" and not _has_services(root):
            excused.append(f"{letter} (single-process repo, no services to declare)")
        else:
            counted.append(letter or name)
    families = 6      # the families `_coverage` can report on
    score = max(0.0, 1.0 - len(counted) / families)
    detail = f"{len(counted)} family/families inactive for missing metadata"
    if counted:
        detail += f": {', '.join(counted)}"
    if excused:
        detail += f"; not applicable here: {', '.join(excused)}"
    return Check("evaluate.coverage", "Evaluate signal families active", score, detail)


#: Invoke archagent through the interpreter running the rubric, not through `PATH`.
#:
#: A bare `archagent` resolves to whatever is first on `PATH`, which on a machine with a global install
#: is not the checkout being scored. That produced a failed `tools.clean` gate here — an older
#: `~/.local/bin/archagent` with no `lint-docs` command — reported as a defect in the artifact. The
#: version scored has to be the version under evaluation, or the scorecard is about someone else's tool.
_VENV_SCRIPT = Path(sys.executable).with_name("archagent")
ARCHAGENT = [str(_VENV_SCRIPT)] if _VENV_SCRIPT.is_file() else ["archagent"]


def _run(cmd: list[str]) -> str | None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


# --- assembling the card -------------------------------------------------------------------

def score_deterministic(root: Path, source_files: set[str], repo: str = "", rev: str = "",
                        arch_dir: str = "architecture") -> Scorecard:
    card = Scorecard(repo=repo, rev=rev)
    card.add(check_required_documents(root, arch_dir))
    card.add(check_covers_resolve(root, arch_dir, source_files))
    card.add(*check_coverage(root, arch_dir, source_files))
    card.add(check_specificity(root, arch_dir, len(source_files)))
    card.add(check_orientation(root, arch_dir))
    card.add(check_drift(root, arch_dir))
    card.add(check_commands_clean(root))
    card.add(check_evaluate_coverage(root))
    return card


def check_update_captured(root: Path, arch_dir: str, changed: set[str]) -> Check:
    """For the second run: of the files that changed between the two revisions, what share sit in a
    subsystem whose document was also updated? The update path is where an artifact-maintenance tool is
    most likely to fail quietly."""
    if not changed:
        return Check("update.captured", "Changes reflected in the artifact", None, "no files changed")
    per_sub = _covered_per_subsystem(root, arch_dir)
    subs_dir = _arch(root, arch_dir) / "subsystems"
    touched_docs = {d.stem for d in subs_dir.glob("*.md")} if subs_dir.is_dir() else set()
    covered_changed = {f for f in changed
                       for name, files in per_sub.items() if f in files and name in touched_docs}
    score = len(covered_changed) / len(changed)
    return Check("update.captured", "Changes reflected in the artifact", score,
                 f"{len(covered_changed)}/{len(changed)} changed files sit in a documented subsystem")

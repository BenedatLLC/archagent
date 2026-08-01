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
import re
import subprocess
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
    out = _run(["archagent", "drift", "--project", str(root), "--json"])
    if out is None:
        return Check("consistency.drift", "Artifact agrees with the code", 0.0, "drift failed to run")
    data = json.loads(out)
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    total = sum(counts.values())
    score = 1.0 if total == 0 else max(0.0, 1.0 - total / 20)
    worst = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v)
    return Check("consistency.drift", "Artifact agrees with the code", score,
                 f"{total} drift item(s)" + (f" ({worst})" if worst else ""))


def check_specificity(root: Path, arch_dir: str) -> Check:
    """How many *falsifiable* claims the artifact makes.

    The counter-criterion to drift. Documents vague enough to be undisprovable score a perfect zero on
    drift; this is what stops that from looking like success. Counted: Covers globs, typed dependency
    declarations, and invariant rows — every one of which `drift` or `check` can contradict.
    """
    arch = _arch(root, arch_dir)
    if not arch.is_dir():
        return Check("artifact.specificity", "Artifact makes falsifiable claims", 0.0, "no artifact")
    text = "\n".join(p.read_text(errors="replace") for p in arch.rglob("*.md"))
    covers = len(_all_covers(root, arch_dir))
    typed = len(re.findall(r"\*\*\s*(?:Connects|Depends-on|Service|Tier|Config)\s*:?\s*\*\*", text, re.I))
    rows = len([ln for ln in (arch / "invariants.md").read_text(errors="replace").splitlines()
                if ln.strip().startswith("|") and re.search(r"\|\s*(active|proposed)\s*\|", ln, re.I)]) \
        if (arch / "invariants.md").is_file() else 0
    claims = covers + typed + rows
    score = min(1.0, claims / 12)      # a dozen checkable claims is a modest artifact, not a rich one
    return Check("artifact.specificity", "Artifact makes falsifiable claims", score,
                 f"{claims} checkable claim(s): {covers} Covers, {typed} typed metadata, {rows} invariants")


# --- the tools themselves ------------------------------------------------------------------

def check_commands_clean(root: Path) -> Check:
    """Every command exits cleanly and prints no traceback. Cheap, and it catches the case where a
    scorecard would otherwise be assembled from broken runs."""
    failures = []
    for cmd in (["archagent", "evaluate", "--project", str(root), "--json"],
                ["archagent", "drift", "--project", str(root), "--json"],
                ["archagent", "lint-docs", "--project", str(root)]):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        blob = proc.stdout + proc.stderr
        if proc.returncode != 0 or _TRACEBACK.search(blob):
            failures.append(f"{cmd[1]} (rc={proc.returncode})")
    score = 1.0 - len(failures) / 3
    return Check("tools.clean", "Commands run without error", score,
                 "all clean" if not failures else "failed: " + ", ".join(failures), gate=True)


def check_evaluate_coverage(root: Path) -> Check:
    """How much of `evaluate` actually measured anything here. Inactive families are not findings-free;
    they are unmeasured, and an artifact that leaves most of them inactive is under-specified."""
    out = _run(["archagent", "evaluate", "--project", str(root), "--json"])
    if out is None:
        return Check("evaluate.coverage", "Evaluate signal families active", 0.0, "evaluate failed to run")
    data = json.loads(out)
    inactive = len(data.get("inactive", []))
    families = 6      # the families `_coverage` can report on
    score = max(0.0, 1.0 - inactive / families)
    return Check("evaluate.coverage", "Evaluate signal families active", score,
                 f"{inactive} family/families inactive for missing metadata")


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
    card.add(check_specificity(root, arch_dir))
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

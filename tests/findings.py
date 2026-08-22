"""Capturing and checking `archagent evaluate` output as part of a describe evaluation.

**Why this is a capture and not a re-run.** Evaluate output is not reproducible after the fact. The
group B, E and F signals are computed from the git log as it stood, and while `--until` bounds the window
it assumes the tree matches the window — `evaluate` itself warns when it does not. So a run that does not
record its findings at the time cannot get them back, and every describe evaluation so far has thrown
them away. Three signals of roughly twenty have ever been checked against anything outside our own
judgement; the rest have regression baselines, which fail when behaviour *changes* and stay green on a
signal that is confidently wrong.

That is the whole argument for capturing by default even in rounds that never score the findings: it
turns "get precision labels on group B someday" from an expedition into a filter over data already on
disk, keyed to a revision, next to the artifact the same run produced.

**What can be checked with no judge.** Four things, and none of them is a quality score:

- `unresolved_subjects` — a finding naming a file that is not there. Wrong regardless of anyone's
  opinion, and the same defect class the artifact rubric already refuses to average in.
- `nondeterminism` — two runs at one revision disagreeing. Nothing checked this before.
- `inactive_conflicts` — a sign reported among the findings while its family is listed as inactive.
  `test_evaluate.py` asserts this on fixtures; a real repository is where it would actually happen.
- `silences` — families that produced nothing *for lack of metadata*. Not a defect at all. It is
  recorded because unrecorded silence reads as health later, which is the failure this whole project
  keeps rediscovering in new spellings.

**None of this measures whether a finding is true.** That needs a reader, and it needs the reader not to
have seen the tool's severity first — see `spotcheck.py`, whose entire design is about withholding it.
Mixing the two would produce a number that looks like precision and is agreement with our own prior.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Subjects that look like a path get checked against the tree; everything else is a subsystem or service
#: name and is not a claim about the filesystem. Same distinction `drift._file_refs` had to learn: a token
#: that was never a file reference must not be reported as a dangling one.
_PATHISH = ("/", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".kt",
            ".rs", ".toml", ".json", ".yaml", ".yml", ".sql", ".tf", ".md")


def _looks_like_path(subject: str) -> bool:
    s = subject.strip()
    if not s or " " in s:
        return False
    return s.endswith(_PATHISH) or "/" in s


@dataclass
class Capture:
    """One `evaluate` run, with the provenance needed to compare it against another one.

    `archagent` is recorded because for *findings* the tool build is a comparability key. That is the
    reverse of the artifact scores, where `generating_model` dominates and the archagent commit is
    recorded but deliberately does not gate a comparison: an artifact is the model's output, findings are
    the tool's. A threshold change makes two finding sets incomparable with identical models on both
    sides.
    """
    repo: str
    target_rev: str                 # a tag or a sha — never a branch, which would drift under us
    archagent: str                  # the tool stamp from `toolinfo.tool_info().stamp()`
    captured_at: str                # ISO date, passed in by the caller
    findings: list[dict] = field(default_factory=list)
    inactive: list[dict] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    truncated: list[list] = field(default_factory=list)
    history_ran: bool = False
    commits_seen: int = 0
    mining_failed: bool = False
    #: "yes" / "no" / "" for never checked. Three states, and collapsing them loses the one that matters:
    #: an empty field must not read as a pass. Set after `check`, not at capture time, because a single
    #: capture cannot know.
    deterministic: str = ""

    @property
    def ids(self) -> set[str]:
        return {f["id"] for f in self.findings}

    @property
    def signs(self) -> set[str]:
        return {f["sign"] for f in self.findings}


def capture(root: Path, repo: str, archagent: str, captured_at: str,
            until: str | None = None) -> Capture:
    """Run `evaluate` against a checkout and keep everything a later reader would need.

    Deliberately stores the coverage report and the cautions beside the findings rather than the findings
    alone. A findings list read without them says "eight problems" where the run meant "eight problems,
    four families never ran, and the history mining failed".
    """
    from archagent.config import load_config
    from archagent.evaluate import evaluate as run_evaluate

    result = run_evaluate(load_config(root), until=until)
    return Capture(
        repo=repo, target_rev=_rev_or_die(root, until), archagent=archagent, captured_at=captured_at,
        findings=[{**asdict(f), "id": f.id} for f in result.findings],
        inactive=[{"family": i.family, "reason": i.reason, "signs": list(i.signs)}
                  for i in result.inactive],
        cautions=list(result.history_cautions),
        truncated=[list(t) for t in result.truncated],
        history_ran=result.history_ran,
        commits_seen=result.commits_seen,
        mining_failed=result.mining_failed,
    )


def _rev_or_die(root: Path, until: str | None) -> str:
    """The revision this capture is *about*.

    `--until` bounds the history but does not check anything out, so the revision that matters is the
    tree's. A capture that cannot name it is unusable later and must not be written: an unpinned finding
    set can neither be reproduced nor compared, and looks exactly like one that can — the same rule the
    ledger applies to `target_commit`.
    """
    import subprocess
    for args in (["describe", "--tags", "--exact-match"], ["rev-parse", "--short", "HEAD"]):
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    raise ValueError(f"{root} is not a git checkout at a nameable revision — a finding capture that "
                     f"cannot be pinned cannot be reproduced or compared")


def save(path: Path, cap: Capture) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cap), indent=2, sort_keys=True) + "\n")
    return path


def load(path: Path) -> Capture:
    return Capture(**json.loads(path.read_text()))


# --- the checks that need no judge ------------------------------------------------------------------

@dataclass
class Problem:
    kind: str            # unresolved-subject | nondeterminism | inactive-conflict
    detail: str
    finding_id: str = ""


def unresolved_subjects(cap: Capture, root: Path) -> list[Problem]:
    """Findings naming a file that is not in the tree.

    Only path-shaped subjects are checked. A subsystem name is not a claim about the filesystem, and
    reporting one as missing would be the false positive `drift` spent two rounds learning to avoid.
    """
    out = []
    for f in cap.findings:
        for s in f.get("subjects", []):
            if _looks_like_path(s) and not (root / s.strip()).exists():
                out.append(Problem("unresolved-subject", f"{f['sign']} names {s!r}, which is not in "
                                                        f"the tree at {cap.target_rev}", f["id"]))
    return out


def nondeterminism(a: Capture, b: Capture) -> list[Problem]:
    """Two captures of one revision that disagree.

    Compared on finding **ids**, not on the whole record: an id is keyed on what a finding is about, so
    this reports a finding appearing or vanishing and stays quiet about counts that legitimately move.
    A run that is not repeatable cannot be labelled, because the labels would attach to findings the next
    run does not produce.
    """
    if a.target_rev != b.target_rev:
        return [Problem("nondeterminism", f"captures are of different revisions ({a.target_rev} vs "
                                          f"{b.target_rev}) and cannot be compared")]
    out = []
    for missing in sorted(a.ids - b.ids):
        out.append(Problem("nondeterminism", "present in the first run, absent in the second", missing))
    for extra in sorted(b.ids - a.ids):
        out.append(Problem("nondeterminism", "absent in the first run, present in the second", extra))
    return out


def inactive_conflicts(cap: Capture) -> list[Problem]:
    """A sign reported among the findings while its family is listed as inactive.

    The coverage report exists so that "no findings" is not read as "clean". A report that contradicts
    its own findings list defeats that, and it has happened: the git-history entry once named the whole of
    family F while `enum-value-escape` — a pure code scan — produced a finding in the same run.
    """
    reported = cap.signs
    return [Problem("inactive-conflict",
                    f"{sign!r} is reported but {entry['family']!r} is listed as inactive")
            for entry in cap.inactive for sign in entry.get("signs", []) if sign in reported]


def silences(cap: Capture) -> list[str]:
    """Families that produced nothing for lack of metadata — recorded, never counted as a defect.

    Group A on a single-service repository is the ordinary case: data ownership, distributed monolith and
    cross-service tracing genuinely cannot apply, and the run is correct to be quiet. What is not correct
    is for that silence to reach a later reader as health.
    """
    return [f"{e['family']} — {e['reason']}" for e in cap.inactive]


@dataclass
class Report:
    problems: list[Problem]
    silent: list[str]
    findings: int
    checked_determinism: bool

    @property
    def clean(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        bits = [f"{self.findings} finding(s)"]
        bits.append("deterministic" if self.checked_determinism and self.clean
                    else "determinism not checked" if not self.checked_determinism else "")
        return ", ".join(b for b in bits if b)


def check(cap: Capture, root: Path, repeat: Capture | None = None) -> Report:
    """Every judge-free check, in one call.

    `repeat` is optional because a second capture costs a whole `evaluate` run on a large repository, and
    a report that says *determinism not checked* is honest where one that omits the line implies it
    passed.
    """
    problems = unresolved_subjects(cap, root) + inactive_conflicts(cap)
    if repeat is not None:
        problems += nondeterminism(cap, repeat)
    return Report(problems=problems, silent=silences(cap), findings=len(cap.findings),
                  checked_determinism=repeat is not None)

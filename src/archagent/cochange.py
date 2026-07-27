"""Git co-change mining (regime B) — the evolutionary signal `evaluate` crosses with structure.

The highest-value architecture smells only show up in *history*: two parts that keep changing together
are coupled even when nothing in the code says so (Mo/Cai/Kazman's "implicit cross-module dependency" /
Fowler's "shotgun surgery"), and an interface that keeps changing with its dependents is unstable. We
mine `git log --name-only`, map each commit's files to subsystems, and count how often subsystem pairs
co-change and how often each subsystem changes.

The same single pass also yields **per-file churn** — total and bug-fix-labeled — which is the change axis
of the change-prone-file check and the ranking signal for duplicated decisions. Recognizing a bug-fix
commit is per-project and learned, not hard-coded; see `history.py`.

Static only in the sense of "no build/run" — it reads git, nothing else. Bulk commits (mass renames,
vendoring, reformats) are excluded by a file-count cap so they don't manufacture coupling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .drift import _git

_BOUNDARY = "@@@commit@@@"
_SUBJ_SEP = "\x1f"  # unit separator between %H and %s, so subjects can't collide with the boundary
# Conventional Commits: type(optional-scope)!: subject
_CONVENTIONAL = re.compile(
    r"^(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\([^)]*\))?!?:\s",
    re.IGNORECASE,
)


@dataclass
class CoChange:
    sub_commits: dict[str, int] = field(default_factory=dict)              # subsystem -> commits touching it
    pair: dict[frozenset[str], int] = field(default_factory=dict)         # {a, b} -> commits touching both
    commits_analyzed: int = 0     # commits that mapped to >=1 subsystem and drove co-change counts
    commits_seen: int = 0         # non-merge commits in the window (before any filtering)
    bulk_skipped: int = 0         # commits skipped for exceeding max_commit_files (mass renames/reformats)
    conventional: int = 0         # commits_seen whose subject follows Conventional Commits
    # Per-file change counts — the churn axis of the change-prone-file check and the ranking signal for
    # duplicated decisions. Counted for every non-bulk commit, whether or not it maps to a subsystem
    # (a file's churn is a fact about the file; subsystem coverage is a separate concern).
    file_commits: dict[str, int] = field(default_factory=dict)      # file -> commits touching it
    file_fix_commits: dict[str, int] = field(default_factory=dict)  # file -> fix-labeled commits touching it
    fix_commits: int = 0          # non-bulk commits the learned recognizer labels as fixes

    def between(self, a: str, b: str) -> int:
        return self.pair.get(frozenset((a, b)), 0)

    @property
    def conventional_pct(self) -> int:
        return round(100 * self.conventional / self.commits_seen) if self.commits_seen else 0

    @property
    def bulk_pct(self) -> int:
        return round(100 * self.bulk_skipped / self.commits_seen) if self.commits_seen else 0


def mine_cochange(
    root: Path,
    file_subs: dict[str, set[str]],
    since: str | None = None,
    cap: int = 3000,
    max_commit_files: int = 50,
    fix_re: re.Pattern | None = None,
) -> CoChange:
    """Co-change counts at the subsystem level, plus per-file churn.

    `file_subs` maps a repo-relative file to its subsystems. `fix_re` is the project's learned bug-fix
    recognizer (see `history.py`); pass None to skip the fix-weighted counts rather than guessing.
    """
    result = CoChange()
    args = ["log", "--no-merges", "--name-only", f"--pretty=format:{_BOUNDARY}%H{_SUBJ_SEP}%s", "-n", str(cap)]
    if since:
        args.append(f"--since={since}")
    out = _git(root, *args)
    if out is None:
        return result

    for subject, files in _commits(out):
        result.commits_seen += 1
        if _CONVENTIONAL.match(subject):
            result.conventional += 1
        if len(files) > max_commit_files:
            result.bulk_skipped += 1
            continue  # skip bulk commits — they fabricate coupling and inflate churn
        if not files:
            continue

        is_fix = bool(fix_re and fix_re.search(subject))
        if is_fix:
            result.fix_commits += 1
        for f in files:
            result.file_commits[f] = result.file_commits.get(f, 0) + 1
            if is_fix:
                result.file_fix_commits[f] = result.file_fix_commits.get(f, 0) + 1

        subs: set[str] = set()
        for f in files:
            subs |= file_subs.get(f, set())
        if not subs:
            continue
        result.commits_analyzed += 1
        for s in subs:
            result.sub_commits[s] = result.sub_commits.get(s, 0) + 1
        ordered = sorted(subs)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                key = frozenset((ordered[i], ordered[j]))
                result.pair[key] = result.pair.get(key, 0) + 1
    return result


def _commits(log: str):
    """Yield `(subject, files)` per commit from the `@@@commit@@@<hash>\\x1f<subject>` + name-only stream."""
    cur: set[str] | None = None
    subject = ""
    for line in log.splitlines():
        if line.startswith(_BOUNDARY):
            if cur is not None:
                yield subject, cur
            cur = set()
            subject = line[len(_BOUNDARY):].split(_SUBJ_SEP, 1)[1] if _SUBJ_SEP in line else ""
        elif line.strip() and cur is not None:
            cur.add(line.strip())
    if cur is not None:
        yield subject, cur

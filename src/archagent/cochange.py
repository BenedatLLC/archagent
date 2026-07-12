"""Git co-change mining (regime B) — the evolutionary signal `evaluate` crosses with structure.

The highest-value architecture smells only show up in *history*: two parts that keep changing together
are coupled even when nothing in the code says so (Mo/Cai/Kazman's "implicit cross-module dependency" /
Fowler's "shotgun surgery"), and an interface that keeps changing with its dependents is unstable. We
mine `git log --name-only`, map each commit's files to subsystems, and count how often subsystem pairs
co-change and how often each subsystem changes.

Static only in the sense of "no build/run" — it reads git, nothing else. Bulk commits (mass renames,
vendoring, reformats) are excluded by a file-count cap so they don't manufacture coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .drift import _git

_BOUNDARY = "@@@commit@@@"


@dataclass
class CoChange:
    sub_commits: dict[str, int] = field(default_factory=dict)              # subsystem -> commits touching it
    pair: dict[frozenset[str], int] = field(default_factory=dict)         # {a, b} -> commits touching both
    commits_analyzed: int = 0

    def between(self, a: str, b: str) -> int:
        return self.pair.get(frozenset((a, b)), 0)


def mine_cochange(
    root: Path,
    file_subs: dict[str, set[str]],
    since: str | None = None,
    cap: int = 3000,
    max_commit_files: int = 50,
) -> CoChange:
    """Co-change counts at the subsystem level. `file_subs` maps a repo-relative file to its subsystems."""
    result = CoChange()
    args = ["log", "--no-merges", "--name-only", f"--pretty=format:{_BOUNDARY}%H", "-n", str(cap)]
    if since:
        args.append(f"--since={since}")
    out = _git(root, *args)
    if out is None:
        return result

    for files in _commits(out):
        if not files or len(files) > max_commit_files:
            continue  # skip bulk commits — they fabricate coupling
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
    """Yield each commit's set of changed files from the `@@@commit@@@<hash>` + name-only stream."""
    cur: set[str] | None = None
    for line in log.splitlines():
        if line.startswith(_BOUNDARY):
            if cur is not None:
                yield cur
            cur = set()
        elif line.strip() and cur is not None:
            cur.add(line.strip())
    if cur is not None:
        yield cur

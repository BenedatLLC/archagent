"""Held-out defect study — do the flagged parts of a system accumulate more defects afterwards?

The analysis pre-registered in `docs/designs/evaluating-archagent.md` §7.1. Every quality number we have
so far came from one reader labelling findings, tuning thresholds against those labels, and grading the
result; this is the measurement that does not depend on our judgement, and the only one that can retire a
signal.

Compute the signals as of a cutoff T, then ask what the repository's own future says: do the files
archagent flagged attract more defect-fixing commits in (T, now] than comparable files it did not flag?

**The controls are the experiment.** Churn predicts churn, and flagged files are high-churn by
construction, so "flagged files change more later" is true by definition and proves nothing. Every
comparison is stratified by churn decile at T, and the claim under test is narrow: *among files with
comparable change history at T*, do the flagged ones accumulate more defect fixes?

Everything here is pre-registered. Deviations belong in the results with a reason, not in this file.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

# --- outcome measurement ------------------------------------------------------------------

_SEP = "@@@"


@dataclass
class Outcomes:
    defects: dict[str, int] = field(default_factory=dict)   # file (as named at T) -> defect-fix commits
    commits: dict[str, int] = field(default_factory=dict)   # ... and all commits, for context
    deleted: set[str] = field(default_factory=set)          # files that disappeared during the window
    ambiguous: set[str] = field(default_factory=set)        # rename chains we could not follow
    fix_commits: int = 0
    total_commits: int = 0


def parse_name_status(log: str):
    """Yield `(subject, [(status, paths)])` per commit from a `--name-status --reverse` stream."""
    subject: str | None = None
    entries: list[tuple[str, list[str]]] = []
    for line in log.splitlines():
        if line.startswith(_SEP):
            if subject is not None:
                yield subject, entries
            subject, entries = line[len(_SEP):], []
        elif line.strip() and subject is not None:
            parts = line.split("\t")
            if len(parts) >= 2:
                entries.append((parts[0], parts[1:]))
    if subject is not None:
        yield subject, entries


def measure_outcomes(log: str, fix_re: re.Pattern | None) -> Outcomes:
    """Defect-fixing commits per file over the outcome window, attributed to each file's name **at T**.

    Renames are followed. A file flagged at T that later moved would otherwise have its subsequent fixes
    attributed to nothing — which deflates the signal specifically for the churny files the checks flag,
    and so biases toward a null result that looks like an honest one.

    `log` must come from `--name-status -M --reverse`: oldest first, because a rename map can only be
    built forwards.
    """
    out = Outcomes()
    alias: dict[str, str] = {}   # current path -> the name it had at T

    def at_t(path: str) -> str:
        return alias.get(path, path)

    for subject, entries in parse_name_status(log):
        out.total_commits += 1
        is_fix = bool(fix_re and fix_re.search(subject))
        out.fix_commits += int(is_fix)
        for status, paths in entries:
            if status.startswith("R") and len(paths) == 2:
                old, new = paths
                origin = alias.pop(old, old)
                if new in alias and alias[new] != origin:
                    out.ambiguous.add(origin)     # two histories collapsing into one path
                alias[new] = origin
                out.deleted.discard(origin)
                touched = origin
            elif status.startswith("D"):
                touched = at_t(paths[0])
                out.deleted.add(touched)
            else:
                touched = at_t(paths[0])
                out.deleted.discard(touched)      # re-added after a delete
            out.commits[touched] = out.commits.get(touched, 0) + 1
            if is_fix:
                out.defects[touched] = out.defects.get(touched, 0) + 1
    return out


# --- the pre-registered statistic ---------------------------------------------------------

MIN_UNFLAGGED_PER_STRATUM = 5   # §7.1: a stratum thinner than this is excluded and counted
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260801       # fixed, so a reported interval is reproducible


def churn_deciles(churn: dict[str, int]) -> dict[str, int]:
    """Assign each scored file to a decile of the churn distribution at T."""
    if not churn:
        return {}
    ordered = sorted(churn.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(ordered)
    return {name: min(9, (i * 10) // n) for i, (name, _) in enumerate(ordered)}


@dataclass
class Stratum:
    decile: int
    flagged: list[int] = field(default_factory=list)     # defect counts, one per flagged file
    unflagged: list[int] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.flagged) and len(self.unflagged) >= MIN_UNFLAGGED_PER_STRATUM


def build_strata(defects: dict[str, int], deciles: dict[str, int], flagged: set[str]) -> list[Stratum]:
    by_decile: dict[int, Stratum] = {}
    for name, d in deciles.items():
        s = by_decile.setdefault(d, Stratum(decile=d))
        (s.flagged if name in flagged else s.unflagged).append(defects.get(name, 0))
    return [by_decile[d] for d in sorted(by_decile)]


def rate_ratio(strata: list[Stratum]) -> float | None:
    """Mantel-Haenszel pooled rate ratio across churn deciles.

    Pooling this way rather than comparing raw totals is what stops the answer being driven by how many
    flagged files happen to sit in each decile.
    """
    num = den = 0.0
    for s in strata:
        if not s.usable:
            continue
        n1, n0 = len(s.flagged), len(s.unflagged)
        total = n1 + n0
        num += sum(s.flagged) * n0 / total
        den += sum(s.unflagged) * n1 / total
    if not den:
        return None
    return num / den


def bootstrap_interval(strata: list[Stratum], draws: int = BOOTSTRAP_DRAWS,
                       seed: int = BOOTSTRAP_SEED) -> tuple[float, float] | None:
    """95% interval by resampling files within strata.

    Bootstrap rather than a parametric interval because per-file defect counts are overdispersed and we
    would rather not defend a distributional assumption.
    """
    usable = [s for s in strata if s.usable]
    if not usable:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(draws):
        resampled = [
            Stratum(decile=s.decile,
                    flagged=[s.flagged[rng.randrange(len(s.flagged))] for _ in s.flagged],
                    unflagged=[s.unflagged[rng.randrange(len(s.unflagged))] for _ in s.unflagged])
            for s in usable
        ]
        rr = rate_ratio(resampled)
        if rr is not None:
            values.append(rr)
    if len(values) < draws // 2:
        return None
    values.sort()
    return values[int(0.025 * len(values))], values[int(0.975 * len(values))]


@dataclass
class Result:
    label: str
    rate_ratio: float | None
    interval: tuple[float, float] | None
    flagged_n: int
    unflagged_n: int
    strata_used: list[int]
    strata_dropped: list[int]
    excluded_deleted: int = 0

    @property
    def degenerate(self) -> bool:
        """A zero-width interval means resampling found no variation to speak of — every file within a
        stratum carried the same count. That is arithmetic, not evidence, and it would otherwise read as
        an extremely confident result."""
        return bool(self.interval and self.interval[0] == self.interval[1])

    @property
    def predicts(self) -> bool:
        """The pre-registered decision rule: the lower bound must exceed 1, over a real interval."""
        return bool(self.interval and self.interval[0] > 1.0 and not self.degenerate)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "rate_ratio": None if self.rate_ratio is None else round(self.rate_ratio, 3),
            "ci95": None if self.interval is None else [round(self.interval[0], 3),
                                                        round(self.interval[1], 3)],
            "flagged_n": self.flagged_n,
            "unflagged_n": self.unflagged_n,
            "strata_used": self.strata_used,
            "strata_dropped": self.strata_dropped,
            "degenerate": self.degenerate,
            "excluded_deleted": self.excluded_deleted,
            "predicts": self.predicts,
        }


def analyse(label: str, defects: dict[str, int], churn: dict[str, int], flagged: set[str],
            deleted: set[str], include_deleted: bool = False) -> Result:
    """One pre-registered comparison. `deleted` files are excluded from the primary analysis and counted
    (§7.1): deletion is ambiguous — it may be the refactor the finding asked for, or an unrelated
    reorganisation — and either inclusion rule embeds an assumption."""
    scored = {f: c for f, c in churn.items() if include_deleted or f not in deleted}
    excluded = len(churn) - len(scored)
    deciles = churn_deciles(scored)
    strata = build_strata(defects, deciles, flagged)
    used = [s.decile for s in strata if s.usable]
    dropped = [s.decile for s in strata if not s.usable]
    return Result(
        label=label,
        rate_ratio=rate_ratio(strata),
        interval=bootstrap_interval(strata),
        flagged_n=sum(len(s.flagged) for s in strata if s.usable),
        unflagged_n=sum(len(s.unflagged) for s in strata if s.usable),
        strata_used=used, strata_dropped=dropped, excluded_deleted=excluded,
    )


# --- the ordering guard -------------------------------------------------------------------

def write_flagged(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_flagged(path: Path) -> dict:
    """Outcomes may only be computed against a flagged set that already exists on disk.

    §7.1 makes the order of operations mechanical rather than a matter of discipline: signals first,
    committed, and only then the outcome data. Deciding what counts as flagged after seeing which files
    turned out buggy is the failure this prevents, and it is not one anybody commits deliberately.
    """
    if not path.exists():
        raise SystemExit(
            f"no flagged set at {path}. Run the `flag` step first and commit its output — outcomes are "
            f"not computed against a flagged set that does not already exist (design §7.1)."
        )
    return json.loads(path.read_text())


# --- driving it against a repository -------------------------------------------------------
#
# Kept separate from the arithmetic above so the statistics can be tested on synthetic data where the
# answer is known, without a clone in the loop.

def scored_at_cutoff(root: Path, config, churn: dict[str, int]) -> tuple[dict[str, int], set[str]]:
    """`(churn per scored file, flagged files)` — the control pool is every file the hotspot check
    *considered*, not every file in the repository. Comparing against files the check never scores
    (vendored, generated, too small) would answer a different question."""
    from archagent.drift import _source_files
    from archagent.hotspots import MIN_LOC, find_hotspots, indent_complexity, is_excluded, looks_generated

    pool: dict[str, int] = {}
    for rel in _source_files(config):
        if is_excluded(rel) or churn.get(rel, 0) <= 0:
            continue
        try:
            text = (root / rel).read_text(errors="replace")
        except OSError:
            continue
        if looks_generated(text):
            continue
        _, loc = indent_complexity(text)
        if loc >= MIN_LOC:
            pool[rel] = churn[rel]
    flagged = {h.path for h in find_hotspots(root, set(pool), churn)}
    return pool, flagged


def flag_at_cutoff(root: Path, until: str) -> dict:
    """Everything the signals say at T. Written to disk before any outcome is fetched (§7.1)."""
    from archagent.cochange import mine_cochange
    from archagent.config import load_config
    from archagent.evaluate import evaluate
    from archagent.history import history_profile

    config = load_config(root)
    profile = history_profile(root, config.architecture_dir, until=until)
    cc = mine_cochange(root, {}, until=until, fix_re=profile.matcher())
    if cc.mining_failed:
        raise SystemExit("the history walk failed at the cutoff — refusing to record a flagged set")
    pool, flagged = scored_at_cutoff(root, config, cc.file_commits)

    result = evaluate(config, until=until)
    decisions = [
        {"owner": f.subjects[0], "files": f.subjects}
        for f in result.findings if f.sign == "scattered-source-of-truth"
    ]
    return {
        "cutoff": until,
        "churn_at_cutoff": pool,
        "flagged_change_prone": sorted(flagged),
        "flagged_decisions": decisions,
        "profile_style": profile.style,
        "commits_at_cutoff": cc.commits_seen,
    }


def outcome_log(clone: Path, cutoff_rev: str, head: str) -> str:
    """The outcome window as a commit *range*, not a date range.

    `--since=<date>` would leave it ambiguous whether the commit the signals were computed at falls inside
    the outcome window. `cutoff_rev..head` is exact: everything after the state we measured, nothing else.
    """
    from archagent.drift import _git
    return _git(clone, "log", "--no-merges", "--name-status", "-M", "--reverse",
                f"{cutoff_rev}..{head}", f"--pretty=format:{_SEP}%s", timeout=600) or ""


def analyse_repo(flagged: dict, outcomes: Outcomes) -> dict:
    """The pre-registered primary test for Check A, plus the secondary comparisons §7.1 marks exploratory."""
    churn = flagged["churn_at_cutoff"]
    flagged_files = set(flagged["flagged_change_prone"])
    primary = analyse("check-A primary (defect fixes, deleted excluded)",
                      outcomes.defects, churn, flagged_files, outcomes.deleted)
    sensitivity = analyse("secondary: deletions kept as zero-defect",
                          outcomes.defects, churn, flagged_files, outcomes.deleted, include_deleted=True)
    all_commits = analyse("secondary: all commits, not just defect fixes",
                          outcomes.commits, churn, flagged_files, outcomes.deleted)
    return {
        "primary": primary.to_dict(),
        "secondary": [sensitivity.to_dict(), all_commits.to_dict()],
        "window": {
            "commits": outcomes.total_commits,
            "defect_fixing": outcomes.fix_commits,
            "files_deleted": len(outcomes.deleted),
            "rename_chains_ambiguous": len(outcomes.ambiguous),
        },
    }

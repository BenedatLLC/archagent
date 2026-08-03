#!/usr/bin/env python
"""Run the held-out defect study (docs/designs/evaluating-archagent.md §7).

    python scripts/defect_study.py flag     [--only NAME]   # signals as of the cutoff; writes the flagged set
    python scripts/defect_study.py outcome  [--only NAME]   # outcomes in (T, head]; refuses without a flagged set
    python scripts/defect_study.py report                   # print the table

The two steps are separate on purpose. `outcome` will not run against a flagged set that does not already
exist on disk, which makes the pre-registered order of operations mechanical rather than something to
remember.
"""
import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from evalhome import eval_dir   # noqa: E402

import corpus                                              # noqa: E402
from defect_study import (                                 # noqa: E402
    analyse_repo, flag_at_cutoff, measure_outcomes, outcome_log, pool_across_repos, read_flagged,
    write_flagged,
)

MANIFEST = ROOT / "tests" / "heldout_manifest.toml"
RESULTS = eval_dir("defect-study")


def load():
    data = tomllib.loads(MANIFEST.read_text())
    return data["cutoff_months"], data["repo"]


def _run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()


def cutoff_date(clone: Path, head: str, months: int) -> str:
    """`months` before the pinned head's own date — fixed, not relative to today, so two runs a month
    apart produce the same window and therefore the same number."""
    iso = _run("git", "-C", str(clone), "log", "-1", "--format=%cI", head)
    year, month = int(iso[:4]), int(iso[5:7])
    total = year * 12 + (month - 1) - months
    return f"{total // 12:04d}-{total % 12 + 1:02d}-{iso[8:10]}"


def do_flag(entries, months, only):
    for entry in entries:
        if only and entry["name"] != only:
            continue
        clone = corpus.ensure_clone({**entry, "rev": entry["head"]})
        cutoff = cutoff_date(clone, entry["head"], months)
        # the tree has to match the window: check out the newest commit at or before the cutoff, or the
        # complexity measure describes files that did not exist yet
        rev = _run("git", "-C", str(clone), "rev-list", "-1", f"--before={cutoff}", entry["head"])
        corpus.warm_clone(clone, rev)   # the cutoff's trees, not just head's
        work = Path("/tmp") / f"defect-{entry['name']}"
        subprocess.run(["git", "-C", str(clone), "worktree", "add", "--detach", "-f", str(work), rev],
                       capture_output=True, check=True)
        try:
            corpus._write_config(work, entry)
            payload = flag_at_cutoff(work, cutoff)
            payload.update({"repo": entry["name"], "head": entry["head"], "cutoff_rev": rev})
            write_flagged(RESULTS / f"{entry['name']}.flagged.json", payload)
            print(f"{entry['name']:10} cutoff {cutoff} @ {rev[:8]}  "
                  f"{len(payload['flagged_change_prone']):3} flagged of "
                  f"{len(payload['churn_at_cutoff']):4} scored  "
                  f"({payload['commits_at_cutoff']} commits, profile {payload['profile_style']})")
        finally:
            subprocess.run(["git", "-C", str(clone), "worktree", "remove", "--force", str(work)],
                           capture_output=True)


def do_outcome(entries, months, only):
    from archagent.history import history_profile

    for entry in entries:
        if only and entry["name"] != only:
            continue
        flagged = read_flagged(RESULTS / f"{entry['name']}.flagged.json")
        clone = corpus.ensure_clone({**entry, "rev": entry["head"]})
        # the outcome window's own wording. It describes the outcome period and never touches the signal,
        # which was computed and written to disk before this step could run.
        profile = history_profile(clone, since=flagged["cutoff"])
        log = outcome_log(clone, flagged["cutoff_rev"], entry["head"])
        outcomes = measure_outcomes(log, profile.matcher())
        report = analyse_repo(flagged, outcomes)
        report.update({"repo": entry["name"], "cutoff": flagged["cutoff"], "head": entry["head"],
                       "outcome_profile_style": profile.style})
        (RESULTS / f"{entry['name']}.result.json").write_text(json.dumps(report, indent=2) + "\n")
        p, w = report["primary"], report["window"]
        print(f"{entry['name']:10} RR={p['rate_ratio']} CI={p['ci95']} "
              f"flagged={p['flagged_n']} controls={p['unflagged_n']} strata={p['strata_used']} "
              f"predicts={p['predicts']}  [{w['defect_fixing']}/{w['commits']} commits were fixes]")


def do_pool(entries):
    """The exploratory pooled estimate. Recomputes outcomes rather than caching them, so it can never
    drift out of step with the per-repo results."""
    from archagent.history import history_profile

    loaded = []
    for entry in entries:
        path = RESULTS / f"{entry['name']}.flagged.json"
        if not path.exists():
            continue
        flagged = read_flagged(path)
        clone = corpus.ensure_clone({**entry, "rev": entry["head"]})
        profile = history_profile(clone, since=flagged["cutoff"])
        outcomes = measure_outcomes(outcome_log(clone, flagged["cutoff_rev"], entry["head"]),
                                    profile.matcher())
        loaded.append((flagged, outcomes))
    result = pool_across_repos(loaded)
    (RESULTS / "pooled.result.json").write_text(json.dumps(result.to_dict(), indent=2) + "\n")
    print(f"pooled over {len(loaded)} repos: RR={result.to_dict()['rate_ratio']} "
          f"CI={result.to_dict()['ci95']} flagged={result.flagged_n} controls={result.unflagged_n} "
          f"predicts={result.predicts}   (EXPLORATORY — not the pre-registered test)")


def do_report(entries):
    print(f"{'repo':10} {'RR':>6} {'95% CI':>16} {'flagged':>8} {'controls':>9}  predicts")
    for entry in entries:
        path = RESULTS / f"{entry['name']}.result.json"
        if not path.exists():
            print(f"{entry['name']:10} {'—':>6}   (not run)")
            continue
        p = json.loads(path.read_text())["primary"]
        ci = f"[{p['ci95'][0]}, {p['ci95'][1]}]" if p["ci95"] else "—"
        print(f"{entry['name']:10} {str(p['rate_ratio']):>6} {ci:>16} {p['flagged_n']:>8} "
              f"{p['unflagged_n']:>9}  {p['predicts']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["flag", "outcome", "pool", "report"])
    ap.add_argument("--only")
    args = ap.parse_args()
    months, entries = load()
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"flag": lambda: do_flag(entries, months, args.only),
     "outcome": lambda: do_outcome(entries, months, args.only),
     "pool": lambda: do_pool(entries),
     "report": lambda: do_report(entries)}[args.step]()

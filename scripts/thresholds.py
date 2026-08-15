#!/usr/bin/env python
"""Leave-one-out sensitivity for archagent's numeric thresholds (design §18).

    python scripts/thresholds.py                 # all thresholds, on the pinned corpus
    python scripts/thresholds.py --only COHESION

Answers one question per threshold: *would we have chosen this value if one repository had not been in the
room?* See `tests/thresholds.py` for what the two failure signatures mean and why neither is automatically
a defect.

Repositories come from the pinned corpus manifest and are read from the same cache the corpus regression
uses, so this needs no network once that has been run at least once.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from corpus import cache_dir, load_manifest   # noqa: E402
from thresholds import leave_one_out, measure   # noqa: E402


def _tree(entry: dict) -> Path | None:
    """A checkout of the pinned revision, as a worktree of the corpus cache.

    A worktree, not a clone: the cache is a *blobless* partial clone, so `git clone --shared` from it
    produces a repository whose file contents are missing and whose checkout fails. `worktree add` against
    the mirror fetches the blobs it needs, which is what the corpus regression already does.
    """
    import subprocess
    name = entry["name"]
    bare = cache_dir() / f"{name}.git"
    if not bare.is_dir():
        return None
    work = ROOT / ".archagent" / "threshold-trees" / name
    if work.is_dir():
        return work
    work.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(bare), "worktree", "add", "--detach", str(work), entry["rev"]],
                   check=True, capture_output=True)
    return work


def _py_files(root: Path, paths: list[str]) -> set[str]:
    out: set[str] = set()
    for p in paths:
        out |= {f.relative_to(root).as_posix() for f in (root / p).rglob("*.py") if f.is_file()}
    return out


# --- the thresholds, each as (constant, shipped value, grid, counter) ---------------------------

def _decisions_counter(trees, key):
    """Findings from `cluster` at a given value of one tunable — a pure code scan, no git history."""
    from archagent.dupdecide import branch_values, cluster, enum_defs

    cache: dict[str, dict[str, set[str]]] = {}

    def per_file(repo):
        if repo not in cache:
            root, files = trees[repo]
            enums = enum_defs(root, files)
            vals = {}
            for rel in files:
                try:
                    text = (root / rel).read_text(errors="replace")
                except OSError:
                    continue
                v = branch_values(text, enums)
                if v:
                    vals[rel] = v
            cache[repo] = vals
        return cache[repo]

    def count(repo, value):
        kw = {key: int(value) if float(value).is_integer() and key.startswith("min") else value}
        return len(cluster(per_file(repo), **kw))

    return count


def _hotspots_counter(trees, key, entries, mined):
    """Findings from `find_hotspots` at a given threshold value.

    **The history is mined once per repository and reused across every threshold in the run** — `mined`
    is owned by the caller for exactly that reason. Mining is the entire
    cost here — a full `git log --name-only` walk, tens of seconds on a large repository — and it does not
    depend on the threshold being swept. Re-walking per value would make the sweep quadratic in nothing
    useful and would tempt whoever ran it into a grid too coarse to see a plateau.
    """
    from archagent.cochange import mine_cochange, resolve_as_of
    from archagent.history import history_profile
    from archagent.hotspots import find_hotspots

    def churn_of(repo):
        if repo not in mined:
            root, files = trees[repo]
            rev = next(e["rev"] for e in entries if e["name"] == repo)
            # `until` is a *date*, handed straight to `git log --until=`. Passing the tag produced two
            # repositories with plausible-looking churn from a malformed date and one with none at all,
            # and nothing errored. resolve_as_of is what turns a revision into the date it happened on.
            until = resolve_as_of(root, rev)
            print(f"    mining {repo} @ {rev} (until {until}) ...", flush=True)
            profile = history_profile(root, None, use_cache=False, until=until)
            cc = mine_cochange(root, {}, fix_re=profile.matcher(), until=until)
            if cc.mining_failed or not cc.file_commits:
                raise SystemExit(
                    f"{repo}: mining produced no per-file churn (mining_failed={cc.mining_failed}, "
                    f"{cc.commits_seen} commit(s) seen). Every hotspot threshold would then report zero "
                    f"findings at every value, and the sweep would record that as a repository with "
                    f"nothing to say — a silent wrong answer rather than an error. Fix the clone or the "
                    f"window before trusting any number here.")
            mined[repo] = (cc.file_commits, cc.file_fix_commits)
            print(f"      {len(cc.file_commits)} file(s) with churn from "
                  f"{cc.commits_seen} commit(s) seen", flush=True)
        return mined[repo]

    def count(repo, value):
        root, files = trees[repo]
        churn, fix_churn = churn_of(repo)
        kw = {key: int(value) if key == "min_loc" else value}
        return len(find_hotspots(root, files, churn, fix_churn, **kw))

    return count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one threshold name")
    args = ap.parse_args()

    manifest = [e for e in load_manifest() if e.get("paths", {}).get("python")]
    trees = {}
    for e in manifest:
        root = _tree(e)
        if root is None:
            # a manifest entry whose mirror has never been fetched: say so rather than silently
            # shrinking the evidence base, which is the §18 opportunity-denominator rule
            print(f"  {e['name']:12} SKIPPED — no cached mirror (run `pytest -m corpus -k {e['name']}`)")
            continue
        trees[e["name"]] = (root, _py_files(root, e["paths"]["python"]))
        print(f"  {e['name']:12} {len(trees[e['name']][1])} python file(s) @ {e['rev']}")
    repos = sorted(trees)
    print()

    from archagent.dupdecide import COHESION, MIN_CLUSTER_VALUES, MIN_FILES_PER_VALUE, TIGHTNESS

    specs = [
        ("COHESION", COHESION, [round(0.1 * i, 1) for i in range(1, 10)], "cohesion"),
        ("TIGHTNESS", TIGHTNESS, [round(0.1 * i, 1) for i in range(1, 10)], "tightness"),
        ("MIN_FILES_PER_VALUE", float(MIN_FILES_PER_VALUE), [2.0, 3.0, 4.0, 5.0, 6.0], "min_files"),
        ("MIN_CLUSTER_VALUES", float(MIN_CLUSTER_VALUES), [2.0, 3.0, 4.0, 5.0, 6.0], "min_values"),
    ]
    from archagent.hotspots import MIN_LOC, PCTILE_BAR

    specs += [
        ("PCTILE_BAR", PCTILE_BAR, [round(0.05 * i, 2) for i in range(10, 20)], "bar"),
        ("MIN_LOC", float(MIN_LOC), [10.0, 20.0, 30.0, 40.0, 60.0, 80.0, 120.0], "min_loc"),
    ]

    hotspot_names = {"PCTILE_BAR", "MIN_LOC"}
    # one mining pass for the whole run, not one per threshold: it is the entire cost and does not
    # depend on the value being swept
    mined: dict[str, tuple] = {}
    failures = 0
    for name, chosen, grid, kwarg in specs:
        if args.only and args.only != name:
            continue
        counter = (_hotspots_counter(trees, kwarg, manifest, mined) if name in hotspot_names
                   else _decisions_counter(trees, kwarg))
        sweep = measure(name, chosen, grid, counter, repos)
        verdict = leave_one_out(sweep)
        print(verdict.report())
        print("    counts:", {r: sweep.counts[r] for r in repos})
        print()
        failures += 0 if verdict.ok else 1
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

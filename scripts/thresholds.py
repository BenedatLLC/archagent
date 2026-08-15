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
    failures = 0
    for name, chosen, grid, kwarg in specs:
        if args.only and args.only != name:
            continue
        sweep = measure(name, chosen, grid, _decisions_counter(trees, kwarg), repos)
        verdict = leave_one_out(sweep)
        print(verdict.report())
        print("    counts:", {r: sweep.counts[r] for r in repos})
        print()
        failures += 0 if verdict.ok else 1
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

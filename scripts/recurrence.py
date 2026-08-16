#!/usr/bin/env python
"""Check a generated artifact against every defect already confirmed for its target (design §13).

    python scripts/recurrence.py <artifact-dir> --target wardrowbe
    python scripts/recurrence.py <artifact-dir>                 # infer the target from the path
    python scripts/recurrence.py --list                         # what is on record, per target

Three rounds of review have cost a human's afternoon each and produced prose that informs the next round
only through somebody's memory. Entries turn each confirmed defect into an assertion about the *target* —
a fact about a pinned revision, not about a document — so it is re-checked on every artifact generated for
that repository afterwards.

Exit status is 1 if any entry fails, so this can gate a change the way §18 asks: a subjective prompt change
is accepted only if the recurrence suite still passes at 100%.

Entries live in the evaluation data repo (`recurrence/<target>.toml`); see `tests/recurrence.py` for what
`forbid` and `require` do and, more usefully, for what neither of them catches.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `tests` ahead of everything, including this script's own directory: both this file and the module it
# imports are named `recurrence`, and the script directory is on sys.path first by default, so the plain
# ordering makes the script import itself.
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from evalhome import eval_home                          # noqa: E402
from recurrence import check, load                      # noqa: E402

SEVERITY_ORDER = {"serious": 0, "moderate": 1, "minor": 2}


def entries_dir() -> Path:
    return eval_home() / "recurrence"


def load_all(target: str | None) -> list:
    d = entries_dir()
    if not d.is_dir():
        raise SystemExit(f"no recurrence entries at {d} — set ARCHAGENT_EVAL_HOME or check out the data repo")
    files = [d / f"{target}.toml"] if target else sorted(d.glob("*.toml"))
    out = []
    for f in files:
        if not f.is_file():
            raise SystemExit(f"no entries recorded for target {target!r} ({f} does not exist)")
        out.extend(load(f))
    return out


def infer_target(arch: Path) -> str | None:
    """`.../selfeval/wardrowbe/artifact/architecture` -> `wardrowbe`. Only a convenience; when it guesses
    wrong the answer is to pass --target, so a wrong guess must not be silent."""
    known = {p.stem for p in entries_dir().glob("*.toml")} if entries_dir().is_dir() else set()
    for part in reversed(arch.resolve().parts):
        if part in known:
            return part
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", nargs="?", help="the architecture/ directory to check")
    ap.add_argument("--target", help="repository name; inferred from the path when omitted")
    ap.add_argument("--list", action="store_true", help="print what is on record and exit")
    ap.add_argument("--quiet", action="store_true", help="print only failures")
    args = ap.parse_args()

    if args.list:
        for f in sorted(entries_dir().glob("*.toml")):
            es = load(f)
            by_sev = {s: sum(1 for e in es if e.severity == s) for s in SEVERITY_ORDER}
            print(f"{f.stem:20} {len(es):3} entries   "
                  + "  ".join(f"{n} {s}" for s, n in by_sev.items() if n))
        return 0

    if not args.artifact:
        ap.error("an artifact directory is required unless --list is given")
    arch = Path(args.artifact)
    if not arch.is_dir():
        raise SystemExit(f"not a directory: {arch}")

    target = args.target or infer_target(arch)
    if not target:
        raise SystemExit(f"cannot tell which repository {arch} documents — pass --target")

    entries = load_all(target)
    results = check(entries, arch, target)
    if not results:
        raise SystemExit(f"no entries for target {target!r}")

    failed = [r for r in results if not r.ok]
    failed.sort(key=lambda r: SEVERITY_ORDER.get(r.entry.severity, 9))

    print(f"\nrecurrence — {target} ({len(results)} entries on record)\n")
    for r in failed:
        print(r.explain())
        if r.entry.note:
            print(f"    note: {r.entry.note.strip()}")
        print()
    if not args.quiet:
        for r in results:
            if r.ok:
                print(f"  ok    {r.entry.id}")
        print()

    if failed:
        sev = ", ".join(f"{sum(1 for r in failed if r.entry.severity == s)} {s}"
                        for s in SEVERITY_ORDER
                        if any(r.entry.severity == s for r in failed))
        print(f"{len(failed)} of {len(results)} recurred ({sev})")
        return 1
    print(f"all {len(results)} clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())

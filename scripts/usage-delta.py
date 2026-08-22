#!/usr/bin/env python
"""Is a release warranted? — diff the documented usage surface against the last one (issue #14).

    python scripts/usage-delta.py                 # against the newest version tag
    python scripts/usage-delta.py --since 75569f7 # against a specific ref

Exit 1 if the surface changed and a release is warranted, 0 if not. Run it before an evaluation round or
a release, and let it answer *has usage changed significantly* with a list rather than a judgement made
under pressure.

**What counts as the usage surface**: the commands `cli.py` registers, their required arguments, and the
commands the phase prompts tell an agent to run. Prompt *wording* does not — `archagent upgrade` ships
prompt bodies into a repo independently of the package version.

It checks its own baseline first. `0.3.0` was published to PyPI and never tagged, so "the last tag" was
`v0.2.0` and any delta against it silently spanned two releases.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from usagedelta import (at_ref, baseline_problem, commands, compare, declared_version,  # noqa: E402
                        latest_tag, phase_prompts, prompt_references)

CLI = "src/archagent/cli.py"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ref to compare against (default: the newest version tag)")
    ap.add_argument("--quiet", action="store_true", help="print only the verdict")
    args = ap.parse_args()

    # Only meaningful when we picked the baseline ourselves; an explicit --since is the caller's problem.
    problem = "" if args.since else baseline_problem(ROOT)
    if problem:
        print(f"baseline: {problem}\n", file=sys.stderr)

    ref = args.since or latest_tag(ROOT)
    if not ref:
        print("no ref to compare against", file=sys.stderr)
        return 2

    before = commands(at_ref(ROOT, ref, CLI))
    after = commands((ROOT / CLI).read_text())
    if not before:
        print(f"could not read commands at {ref} — is {CLI} present there?", file=sys.stderr)
        return 2
    refs = prompt_references(phase_prompts(ROOT))
    delta = compare(before, after, refs)

    print(f"usage surface: {ref} → HEAD"
          f"   (declared version {declared_version(ROOT) or '?'})\n")
    if not args.quiet:
        print(f"  commands at {ref}: {len(before)}     at HEAD: {len(after)}")

    for name in delta.added:
        print(f"  [+] {after[name].signature()}")
    for name in delta.removed:
        print(f"  [-] {before[name].signature()}")
    for name, was, now in delta.args_changed:
        print(f"  [~] {name}: required args {list(was)} → {list(now)}")
    for cmd, f in delta.prompt_refs_missing:
        print(f"  [!] {f} tells an agent to run `archagent {cmd}`, which {ref} does not have")

    if delta.release_warranted:
        print("\nA release is warranted: the documented usage surface changed.")
        return 1
    print("\nNo release needed on usage grounds — the surface is unchanged.")
    if problem:
        print("(But read the baseline warning above: the comparison may not be against the last release.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

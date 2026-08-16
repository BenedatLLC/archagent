#!/usr/bin/env python
"""Check an artifact's asserted facts against the code (design `computed-claims.md`, step 1 of §8).

    python scripts/claims.py check <claims.md> --root <checkout>
    python scripts/claims.py validate <claims.md>      # static rules only; runs nothing

The recorded value in the claims file is **what the artifact asserts**. So a divergence means the
documents and the code disagree, and running this against an artifact nobody has repaired is the
retrospective measurement step 1 asks for.

`validate` is the half that runs nothing: it applies the safety rules of §5.4 and reports any command that
would be refused. That is what makes an unsafe command visible in review.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from claims import Summary, check, load, validate    # noqa: E402


def cmd_validate(args) -> int:
    claims = load(Path(args.claims))
    bad = [(c, validate(c.command)) for c in claims]
    bad = [(c, why) for c, why in bad if why]
    for c, why in bad:
        print(f"  REFUSED  {c.id}  {c.description}")
        for w in why:
            print(f"           {w}")
    print(f"\n{len(claims) - len(bad)}/{len(claims)} commands pass static validation")
    return 1 if bad else 0


def cmd_check(args) -> int:
    claims = load(Path(args.claims))
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    results = check(claims, root)
    s = Summary.of(results)

    if s.diverged:
        print(f"\nDIVERGED — the artifact and the code disagree ({len(s.diverged)})\n")
        for r in s.diverged:
            print(f"  {r.claim.id}  {r.claim.description}")
            print(f"      artifact says: {r.claim.value}")
            print(f"      code says:     {r.observed}")
            if r.claim.source:
                print(f"      asserted in:   {r.claim.source}")
            print(f"      command:       {r.claim.command}")
            print()

    if s.errored:
        print(f"\nCOMMAND FAILED OR REFUSED ({len(s.errored)})\n")
        for r in s.errored:
            print(f"  {r.claim.id}  {r.claim.description}\n      {r.error}")
            print(f"      command: {r.claim.command}\n")

    if not args.quiet:
        print("AGREED\n")
        for r in results:
            if r.ok:
                print(f"  {r.claim.id}  {r.claim.description} = {r.observed}")
        print()

    print(f"{s.total} claims: {s.agreed} agree, {len(s.diverged)} diverge, {len(s.errored)} could not run")
    return 1 if s.diverged or s.errored else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check")
    p.add_argument("claims")
    p.add_argument("--root", required=True, help="the checkout the claims are about")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("validate", help="static rules only — executes nothing")
    p.add_argument("claims")
    p.set_defaults(fn=cmd_validate)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

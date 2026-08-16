#!/usr/bin/env python
"""The evaluation ledger — one row per evaluation run (design §17).

    python scripts/ledger.py add --run-id 2026-08-16-wardrowbe-checklist-opus ...
    python scripts/ledger.py list [--target wardrowbe] [--kind checklist]
    python scripts/ledger.py show <run-id>
    python scripts/ledger.py trend judged_mean --target wardrowbe

Results have so far accumulated as a pile of files, and each round has informed the next only through
whoever remembered it. This is the table that ends that.

`trend` is the command that matters. It refuses to plot a series across rows that used different judge
models, different generating models or different versions of the rubric, and names the key that differs.
The first two calibration rounds used different review briefs, so their means were never comparable, and
nothing recorded it — a ledger that would happily average them is worse than no ledger, because the number
it produces looks like a finding.

The CSV lives in the evaluation data repository beside the runs it indexes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from evalhome import eval_home                                          # noqa: E402
from ledger import COLUMNS, Row, compare, load, save, validate          # noqa: E402


def ledger_path() -> Path:
    return eval_home() / "ledger.csv"


def _select(rows: list[Row], args) -> list[Row]:
    out = rows
    if getattr(args, "target", None):
        out = [r for r in out if args.target in r.target_url]
    if getattr(args, "kind", None):
        out = [r for r in out if r.run_kind == args.kind]
    if getattr(args, "judge", None):
        out = [r for r in out if r.judge_model == args.judge]
    if getattr(args, "rubric", None):
        out = [r for r in out if r.rubric_version == args.rubric]
    return out


def _filters(p) -> None:
    """`trend` refuses a mixed selection rather than averaging it, so narrowing has to be possible from
    the command line — otherwise the refusal is a dead end instead of an instruction."""
    p.add_argument("--target")
    p.add_argument("--kind")
    p.add_argument("--judge")
    p.add_argument("--rubric")


def cmd_add(args) -> int:
    path = ledger_path()
    rows = load(path)
    row = Row(**{c: getattr(args, c, "") or "" for c in COLUMNS})
    bad = validate(row, rows)
    if bad:
        for b in bad:
            print(f"refusing to add: {b}", file=sys.stderr)
        return 1
    rows.append(row)
    save(path, rows)
    print(f"added {row.run_id} ({len(rows)} rows)")
    if not row.comparable():
        # Not an error — historical runs genuinely did not record this. But saying nothing here is how a
        # row that can never be compared ends up looking like one that can.
        missing = [k for k in ("rubric_version", "judge_model", "generating_model") if row.key(k) is None]
        print(f"  note: not comparable — {', '.join(missing)} not recorded")
    return 0


def cmd_list(args) -> int:
    rows = _select(load(ledger_path()), args)
    if not rows:
        print("no rows")
        return 0
    print(f"\n{'run_id':46}{'kind':13}{'target':24}{'judge':10}{'mean':>6}  cmp")
    for r in rows:
        target = r.target_url.rstrip("/").split("/")[-1][:22]
        print(f"{r.run_id:46}{r.run_kind:13}{target:24}{(r.judge_model or '-'):10}"
              f"{(r.judged_mean or '-'):>6}  {'y' if r.comparable() else 'n'}")
    print(f"\n{len(rows)} row(s), {sum(1 for r in rows if r.comparable())} comparable")
    return 0


def cmd_show(args) -> int:
    for r in load(ledger_path()):
        if r.run_id == args.run_id:
            for c in COLUMNS:
                v = getattr(r, c)
                if v:
                    print(f"{c:22} {v}")
            return 0
    print(f"no such run_id: {args.run_id}", file=sys.stderr)
    return 1


def cmd_trend(args) -> int:
    rows = _select(load(ledger_path()), args)
    cmp = compare(rows, args.metric)

    if cmp.excluded:
        print(f"\nexcluded {len(cmp.excluded)}:")
        for r, why in cmp.excluded:
            print(f"  {r.run_id:46} {why}")

    if not cmp.rows:
        print(f"\nnothing to compare on {args.metric}")
        return 1

    print(f"\n{args.metric} — {len(cmp.rows)} row(s)\n")
    for r in sorted(cmp.rows, key=lambda r: (r.date, r.run_id)):
        print(f"  {r.date:12}{r.run_id:46}{getattr(r, args.metric):>8}"
              f"   {r.judge_model}/{r.rubric_version}")

    if cmp.differs_on:
        print(f"\nNOT A TREND. These rows differ on {', '.join(cmp.differs_on)}, so they are not measuring"
              f"\nthe same thing, and a series across them would be a property of the table rather than of"
              f"\nthe artifacts. Narrow the selection until this is empty.")
        for k in cmp.differs_on:
            vals = sorted(v for v in {r.key(k) for r in cmp.rows} if v)
            print(f"  {k}: {', '.join(vals)}")
        return 1

    vals = [float(getattr(r, args.metric)) for r in cmp.rows]
    print(f"\n  n={len(vals)}  mean {sum(vals)/len(vals):.2f}  range {min(vals):.2f}–{max(vals):.2f}")

    if cmp.unverifiable_on:
        print(f"\n  Caveat: {', '.join(cmp.unverifiable_on)} was never recorded for at least one of these"
              f"\n  runs, so a difference between them cannot be ruled out. The series is shown because it"
              f"\n  is the only history there is, not because it is sound.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="record a run")
    for c in COLUMNS:
        p.add_argument(f"--{c.replace('_', '-')}", dest=c, default="")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("list")
    _filters(p)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show")
    p.add_argument("run_id")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("trend", help="a series on one metric — refuses if the rows are not comparable")
    p.add_argument("metric")
    _filters(p)
    p.set_defaults(fn=cmd_trend)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

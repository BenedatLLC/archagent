#!/usr/bin/env python
"""Run a per-repository checklist against a generated artifact (design §14).

    python scripts/checklist.py render --target obstudio --artifact architecture > worksheet.md
    python scripts/checklist.py score  worksheet-answered.md --target obstudio
    python scripts/checklist.py agree  judge-a.md judge-b.md --target obstudio
    python scripts/checklist.py list

`render` writes the worksheet a judge fills in: fixed claims, fixed order, correct answer stated. `score`
reads it back and reports `correct` / `wrong` / `absent`.

Why the answer is given to the judge: the reading was already done once, by a human, during a calibration
round. Asking a judge to redo it costs a codebase exploration per run and re-introduces exactly the errors
the checklist banks. Comparison is cheap and reproducible; research is neither.

Checklists live in the evaluation data repo (`checklists/<target>.toml`) — they are answer keys, and
whoever is authoring a prompt change must not be reading one while they do it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `tests` first: this file and the module it imports share a name, and the script's own directory is on
# sys.path ahead of everything by default.
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from checklist import WEIGHT, load, parse, render, score          # noqa: E402
from evalhome import eval_home                                    # noqa: E402


def checklist_dir() -> Path:
    return eval_home() / "checklists"


def items_for(target: str) -> list:
    f = checklist_dir() / f"{target}.toml"
    if not f.is_file():
        raise SystemExit(f"no checklist for {target!r} ({f} does not exist)")
    return load(f)


def cmd_list(_: argparse.Namespace) -> int:
    d = checklist_dir()
    if not d.is_dir():
        raise SystemExit(f"no checklists at {d} — set ARCHAGENT_EVAL_HOME or check out the data repo")
    for f in sorted(d.glob("*.toml")):
        items = load(f)
        by_sev = {s: sum(1 for i in items if i.severity == s) for s in WEIGHT}
        print(f"{f.stem:20} {len(items):3} items   "
              + "  ".join(f"{n} {s}" for s, n in by_sev.items() if n))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    items = items_for(args.target)
    text = render(items, args.artifact, args.target, rev=items[0].rev if items else "")
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out} — {len(items)} items", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    items = items_for(args.target)
    answers = parse(Path(args.answers).read_text(), items)
    s = score(answers, items)

    print(f"\nchecklist — {s.target} ({len(items)} items)\n")
    by_id = {i.id: i for i in items}
    for it in items:
        a = answers.get(it.id)
        mark = {"correct": "ok   ", "wrong": "WRONG", "absent": "absent"}.get(
            a.verdict if a and not a.discarded else "", "  -  ")
        print(f"  {mark:7} {it.id:44} [{it.severity}]")
        if a and a.discarded:
            print(f"          discarded: {a.discarded}")

    print()
    for v in ("correct", "wrong", "absent"):
        print(f"  {v:8} {s.counts.get(v, 0):3}   (weighted {s.weighted.get(v, 0)})")
    if s.skipped:
        print(f"  skipped  {len(s.skipped):3}   {', '.join(s.skipped)}")
    if s.discarded:
        print(f"  discarded {len(s.discarded):2}")

    if s.accuracy is None:
        print("\nnothing scored — an unanswered worksheet is not a passing one")
        return 1
    print(f"\n  accuracy {s.accuracy:.2f}   weighted {s.weighted_accuracy:.2f}"
          f"   ({s.counts['correct']} correct of {s.answered} answered)")

    # A checklist is only meaningful next to its own history; a single number says nothing about whether
    # the artifact improved. The ledger (§17) is where the series lives.
    wrong = [by_id[i] for i, a in answers.items()
             if a.verdict == "wrong" and not a.discarded and by_id[i].severity == "serious"]
    if wrong:
        print(f"\n  {len(wrong)} serious claim(s) contradicted:")
        for it in wrong:
            print(f"    {it.id}: {it.ground_truth.strip().splitlines()[0]}")
    return 0


def cmd_agree(args: argparse.Namespace) -> int:
    """How much two judges disagree on the same artifact — the checklist's own noise floor.

    §14 claims a ternary verdict against a stated answer varies far less than a 1–5 judgement, where the
    measured floor spans two points on a single criterion. That is an argument, not a measurement, until
    two judges answer the same worksheet. This is the measurement.

    Disagreements are reported item by item rather than as a single number, because *where* judges differ
    is the useful part: §14 predicts the residual sits on the `wrong`/`absent` boundary, and a disagreement
    that lands somewhere else means something other than the predicted weakness is going on.
    """
    items = items_for(args.target)
    a = parse(Path(args.a).read_text(), items)
    b = parse(Path(args.b).read_text(), items)
    na, nb = Path(args.a).stem, Path(args.b).stem

    agreed, differed, incomparable = [], [], []
    for it in items:
        va = a.get(it.id).verdict if a.get(it.id) and not a[it.id].discarded else None
        vb = b.get(it.id).verdict if b.get(it.id) and not b[it.id].discarded else None
        if va is None or vb is None:
            incomparable.append((it, va, vb))
        elif va == vb:
            agreed.append((it, va))
        else:
            differed.append((it, va, vb))

    print(f"\nagreement — {args.target}: {na} vs {nb}\n")
    for it, va, vb in differed:
        boundary = {va, vb} == {"wrong", "absent"}
        print(f"  DIFFER  {it.id:44} [{it.severity}]  {na}={va}  {nb}={vb}"
              + ("   (the predicted wrong/absent boundary)" if boundary else ""))
    for it, va, vb in incomparable:
        print(f"  ---     {it.id:44} unscored by one judge  ({na}={va}, {nb}={vb})")

    comparable = len(agreed) + len(differed)
    if not comparable:
        print("\nnothing comparable")
        return 1
    print(f"\n  agree {len(agreed)}/{comparable} = {len(agreed)/comparable:.2f}")
    on_boundary = sum(1 for _, va, vb in differed if {va, vb} == {"wrong", "absent"})
    if differed:
        print(f"  of {len(differed)} disagreement(s), {on_boundary} on the wrong/absent boundary")

    sa, sb = score(a, items), score(b, items)
    print(f"\n  {na:24} accuracy {sa.accuracy if sa.accuracy is not None else float('nan'):.2f}"
          f"   weighted {sa.weighted_accuracy if sa.weighted_accuracy is not None else float('nan'):.2f}")
    print(f"  {nb:24} accuracy {sb.accuracy if sb.accuracy is not None else float('nan'):.2f}"
          f"   weighted {sb.weighted_accuracy if sb.weighted_accuracy is not None else float('nan'):.2f}")
    if sa.accuracy is not None and sb.accuracy is not None:
        print(f"  {'spread':24} {abs(sa.accuracy - sb.accuracy):.2f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="what is on record, per target")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("render", help="write the judge's worksheet")
    p.add_argument("--target", required=True)
    p.add_argument("--artifact", default="architecture", help="artifact path as the judge will see it")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("score", help="read a completed worksheet")
    p.add_argument("answers")
    p.add_argument("--target", required=True)
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("agree", help="compare two completed worksheets — the checklist's noise floor")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--target", required=True)
    p.set_defaults(fn=cmd_agree)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

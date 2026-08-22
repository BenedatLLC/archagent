#!/usr/bin/env python
"""Can a reader find things in this artifact? — the judged half of completeness.

    python scripts/locate.py render --target paperless-ngx --artifact architecture --out worksheet.md
    python scripts/locate.py grade  worksheet.md --target paperless-ngx
    python scripts/locate.py list

`render` writes questions and no answers; a judge answers them from the documents alone. `grade` compares
each answer to where the behaviour actually lives.

**The worksheet must never be shown next to the task file.** The task file holds the answers, and this is
the one instrument whose measurement is destroyed by the judge knowing them — see `tests/locate.py`.

Every accuracy instrument this project has is saturated: fresh artifacts score 0.88 to 1.00 on per-item
checklists across three targets. Accuracy is not where these documents fail. They fail by being shallow,
and shallowness only shows when someone tries to use them to find something.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from evalhome import eval_home                                   # noqa: E402
from locate import WEIGHT, load, parse, render, score            # noqa: E402


def tasks_dir() -> Path:
    return eval_home() / "locate"


def tasks_for(target: str) -> list:
    f = tasks_dir() / f"{target}.toml"
    if not f.is_file():
        raise SystemExit(f"no locate tasks for {target!r} ({f} does not exist)")
    return load(f)


def cmd_list(_: argparse.Namespace) -> int:
    d = tasks_dir()
    if not d.is_dir():
        raise SystemExit(f"no locate tasks at {d} — set ARCHAGENT_EVAL_HOME or check out the data repo")
    for f in sorted(d.glob("*.toml")):
        ts = load(f)
        by = {s: sum(1 for t in ts if t.severity == s) for s in WEIGHT}
        print(f"{f.stem:20} {len(ts):3} tasks   " + "  ".join(f"{n} {s}" for s, n in by.items() if n))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    ts = tasks_for(args.target)
    text = render(ts, args.artifact, args.target, rev=ts[0].rev if ts else "")
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out} — {len(ts)} tasks, no answers", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    ts = tasks_for(args.target)
    responses = parse(Path(args.answers).read_text(), ts)
    s = score(ts, responses)

    print(f"\nlocate — {args.target} ({len(ts)} tasks)\n")
    mark = {"located": "found  ", "partial": "partial", "lost": "LOST   "}
    for g in s.graded:
        print(f"  {mark[g.verdict]} {g.task.id:44} [{g.task.severity}]"
              + (f"  → {g.matched}" if g.matched else ""))
        if g.verdict != "located":
            print(f"           lives in: {', '.join(g.task.expects)}")
            if g.response and g.response.where:
                print(f"           answered: {g.response.where.strip()[:90]}")
    if s.skipped:
        print(f"\n  skipped {len(s.skipped)}: {', '.join(s.skipped)}")

    counts = s.by_verdict()
    print(f"\n  located {counts['located']}   partial {counts['partial']}   lost {counts['lost']}")
    if s.findability is None:
        print("\nnothing answered — an empty worksheet is not a findable artifact")
        return 1
    print(f"\n  findability {s.findability:.2f}   weighted {s.weighted:.2f}"
          f"   (partial counts half)")

    lost_serious = [g for g in s.graded if g.verdict == "lost" and g.task.severity == "serious"]
    if lost_serious:
        print(f"\n  {len(lost_serious)} serious behaviour(s) a reader could not locate:")
        for g in lost_serious:
            print(f"    {g.task.id}: {g.task.answer.strip().splitlines()[0] if g.task.answer else ''}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("render", help="the judge's worksheet — questions only, no answers")
    p.add_argument("--target", required=True)
    p.add_argument("--artifact", default="architecture")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("grade", help="score answers against where each behaviour actually lives")
    p.add_argument("answers")
    p.add_argument("--target", required=True)
    p.set_defaults(fn=cmd_grade)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""End-to-end self-evaluation (`docs/designs/evaluating-archagent.md` §8).

    python scripts/selfeval.py score  <path> [--arch-dir architecture]
    python scripts/selfeval.py brief  <path> [--second-run]     # judged criteria, for a reviewing agent
    python scripts/selfeval.py judged <path> --review <file.md> [--by NAME]
    python scripts/selfeval.py run    <repo-url> --from <rev> --to <rev>

`score` works today and needs no agent: it runs the deterministic half of the rubric (§9) against an
artifact that already exists and writes a scorecard.

`run` is the full loop — describe at `rev1`, evaluate, score, advance to `rev2`, re-describe, re-score —
and it is **not complete**, because steps 2 and 5 require invoking a coding agent non-interactively. That
is a different kind of dependency from anything else archagent ships (it would make the tool an agent
*caller* rather than an agent *callee*), and the design leaves three questions open before it is wired up:
which agent, how it is pinned, and how much of the score is agent variance rather than artifact quality.
Until a repeat run on identical inputs establishes that noise floor, comparing two scorecards would be
reading tea leaves. The seam is marked rather than faked.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from rubric import check_update_captured, score_deterministic   # noqa: E402
from rubric_judged import render_brief, review_from, save as save_review   # noqa: E402

RESULTS = ROOT / "evaluations" / "selfeval"


def _source_files(root: Path) -> set[str]:
    from archagent.config import load_config
    from archagent.drift import _source_files as sf
    return sf(load_config(root))


def _arch_dir(root: Path) -> str:
    from archagent.config import load_config
    return load_config(root).arch_dir


def do_score(path: Path, arch_dir: str | None, rev: str = "", changed: set[str] | None = None) -> dict:
    root = path.resolve()
    arch = arch_dir or _arch_dir(root)
    card = score_deterministic(root, _source_files(root), repo=root.name, rev=rev, arch_dir=arch)
    if changed:
        card.add(check_update_captured(root, arch, changed))
    data = card.to_dict()

    print(f"\n{root.name}{(' @ ' + rev) if rev else ''} — deterministic rubric\n")
    for c in data["checks"]:
        mark = "  n/a" if c["score"] is None else f"{c['score']:5.2f}"
        gate = " [gate]" if c["gate"] else ""
        print(f"  {mark}  {c['label']}{gate}\n         {c['detail']}")
    overall = data["deterministic_score"]
    print(f"\n  overall: {'n/a' if overall is None else overall}")
    if data["gates_failed"]:
        print(f"  GATES FAILED: {', '.join(data['gates_failed'])} — the judged half of the rubric would "
              f"not be meaningful on this artifact")
    return data


def _is_completed(path: Path) -> bool:
    """Has someone filled this brief in? A blank template has `score:` with nothing after it."""
    return path.is_file() and bool(re.search(r"^\s*score\s*:\s*\d", path.read_text(errors="replace"),
                                             re.MULTILINE))


def do_brief(path: Path, second_run: bool, force: bool = False) -> None:
    root = path.resolve()
    arch = _arch_dir(root)
    out = RESULTS / root.name / f"review-brief{'-update' if second_run else ''}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    # A completed review is hours of a reviewer's work and the only copy of the primary evidence; this
    # command silently overwrote one, and the loss was invisible because a blank brief looks like a
    # freshly generated brief. Refuse rather than clobber.
    if _is_completed(out) and not force:
        raise SystemExit(
            f"{out} contains a completed review (it has filled-in scores).\n"
            f"Writing a blank brief over it would destroy the only copy.\n\n"
            f"Either archive it first:\n"
            f"    git mv {out.relative_to(ROOT)} "
            f"{out.with_name('review-<date>-completed.md').relative_to(ROOT)}\n"
            f"or pass --force if you are certain it is recoverable from git.")
    # repo-relative, not absolute: the brief is committed and read by someone on another machine
    out.write_text(render_brief(arch, root.name, second_run))
    print(f"wrote {out}")
    print("Hand this to a reviewer or a separate agent session. Every score needs a file:line citation;")
    print("uncited scores are discarded rather than averaged in.")


def do_judged(path: Path, review: Path, by: str) -> None:
    root = path.resolve()
    # root is passed so citations are resolved against the tree, not merely pattern-matched
    r = review_from(review.read_text(), root.name, "", by, root=root)
    dest = save_review(RESULTS / root.name / "judged.json", r)
    kept, answered = r.coverage
    print(f"\n{root.name} — judged rubric ({r.judged_by})\n")
    for cid, s in r.scores.items():
        if s.get("score") is None:
            print(f"   —    {cid:24} discarded: {s['discarded']}")
        else:
            print(f"  {s['score']}/5   {cid:24} {s['why'].splitlines()[0][:70]}")
        for bad in s.get("unresolved", []):
            print(f"         ! {bad}")
    print(f"\n  mean: {'n/a' if r.mean is None else round(r.mean, 2)}  "
          f"(over {kept} of {answered} answered criteria)")
    if answered and kept < answered:
        print(f"  NOT A SCORE OF THE ARTIFACT: {answered - kept} of {answered} criteria were discarded, "
              f"so this mean\n  describes the part that survived, not the artifact")
    print(f"  [uncalibrated] no agreement with a human reviewer has been measured for these criteria,")
    print(f"  so this number has unknown meaning and gates nothing (design §11, §13.2)")
    print(f"\n  written to {dest}")


def do_run(url: str, rev_from: str, rev_to: str) -> None:
    raise SystemExit(
        "`run` is not implemented: steps 2 and 5 (describe at each revision) need a coding agent invoked\n"
        "non-interactively, and the design requires the run-to-run noise floor before two scorecards can\n"
        "be compared at all (§8).\n\n"
        "What works today:\n"
        "  1. check out the revision yourself\n"
        "  2. run your agent's /archagent-describe against it\n"
        "  3. python scripts/selfeval.py score <path>\n"
        "  4. repeat at the later revision and diff the two scorecards\n\n"
        f"(requested: {url} {rev_from}..{rev_to})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score"); s.add_argument("path"); s.add_argument("--arch-dir")
    s.add_argument("--rev", default=""); s.add_argument("--out")
    b = sub.add_parser("brief"); b.add_argument("path"); b.add_argument("--second-run", action="store_true")
    b.add_argument("--force", action="store_true", help="overwrite a completed review")
    j = sub.add_parser("judged"); j.add_argument("path"); j.add_argument("--review", required=True)
    j.add_argument("--by", default="")
    r = sub.add_parser("run"); r.add_argument("url")
    r.add_argument("--from", dest="rev_from", required=True); r.add_argument("--to", dest="rev_to", required=True)
    args = ap.parse_args()

    if args.cmd == "run":
        do_run(args.url, args.rev_from, args.rev_to)
    if args.cmd == "brief":
        do_brief(Path(args.path), args.second_run, args.force); raise SystemExit(0)
    if args.cmd == "judged":
        do_judged(Path(args.path), Path(args.review), args.by); raise SystemExit(0)
    data = do_score(Path(args.path), args.arch_dir, args.rev)
    if args.out:
        out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\n  written to {out}")

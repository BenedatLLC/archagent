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

from evalhome import eval_dir   # noqa: E402

from rubric import check_update_captured, score_deterministic   # noqa: E402
from rubric_judged import (CRITERIA, parse_brief, render_brief, review_from,   # noqa: E402
                           save as save_review)

RESULTS = eval_dir("selfeval")


def _rev(root: Path) -> str:
    """The target revision, as a tag when it has one. A brief that names the tool must name the target
    too, or half the provenance is recorded."""
    for args in (["describe", "--tags", "--exact-match"], ["rev-parse", "--short", "HEAD"]):
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return ""


def _source_files(root: Path) -> set[str]:
    from archagent.config import load_config
    from archagent.drift import _source_files as sf
    return sf(load_config(root))


def _arch_dir(root: Path) -> str:
    from archagent.config import load_config
    return load_config(root).arch_dir


def do_findings(path: Path, repeat: bool = False, until: str | None = None) -> Path | None:
    """Capture `evaluate` output beside the artifact, and run the judge-free checks over it.

    Called from `score` rather than left as an optional extra, because the output is not recoverable
    later: the history signals are computed from the log as it stood, and a run that did not record them
    cannot get them back. Capturing costs one `evaluate` run and is worth it even in a round that never
    scores the findings — it is the difference between having group-B data to label and having to mount
    an expedition to produce some.
    """
    import datetime

    from findings import capture, check, save
    from toolinfo import tool_info
    root = path.resolve()
    try:
        cap = capture(root, repo=root.name, archagent=tool_info().stamp(),
                      captured_at=datetime.date.today().isoformat(), until=until)
    except ValueError as e:                       # not a git checkout at a nameable revision
        print(f"\n  findings NOT captured: {e}")
        return None

    dest = save(RESULTS / root.name / f"findings-{cap.target_rev}.json", cap)
    rpt = check(cap, root, repeat=capture(root, repo=root.name, archagent=tool_info().stamp(),
                                          captured_at=cap.captured_at, until=until) if repeat else None)

    print(f"\n{root.name} @ {cap.target_rev} — evaluate findings\n")
    print(f"  {rpt.summary()}")
    for p in rpt.problems:
        print(f"  [{p.kind}] {p.finding_id or '-'}: {p.detail}")
    if rpt.silent:
        # Not defects. Printed so that a family which could not run is on the record next to the
        # findings, rather than reaching a later reader as health.
        print("\n  produced nothing for lack of metadata (not proof of health):")
        for s in rpt.silent:
            print(f"    {s}")
    if cap.mining_failed:
        print("\n  history mining FAILED — every history-based signal in this capture is void")
    print(f"\n  written to {dest}")
    return dest


def do_score(path: Path, arch_dir: str | None, rev: str = "", changed: set[str] | None = None,
             skip_findings: bool = False, repeat: bool = False) -> dict:
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
    if not skip_findings:
        do_findings(path, repeat=repeat)
    return data


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unrecorded"


def _is_completed(path: Path) -> bool:
    """Has someone filled this brief in? A blank template has `score:` with nothing after it."""
    return path.is_file() and bool(re.search(r"^\s*score\s*:\s*\d", path.read_text(errors="replace"),
                                             re.MULTILINE))


def _latest_capture(root: Path):
    """The capture for the revision under review, or None.

    Matched on the revision rather than on modification time: a brief must show the findings for the tree
    it is about, and picking the newest file would silently pair a review of one revision with findings
    from another — the round-4 skew defect in a new place.
    """
    from findings import load
    p = RESULTS / root.name / f"findings-{_rev(root)}.json"
    return load(p) if p.is_file() else None


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
    from toolinfo import tool_info
    tool = tool_info()
    cap = _latest_capture(root)
    out.write_text(render_brief(arch, root.name, second_run, tool=tool.stamp(),
                                target_rev=_rev(root), findings=cap))
    print(f"wrote {out}")
    if cap is None:
        print("  no evaluate capture found — the brief has no findings section. Run "
              "`selfeval.py findings <path>` first if you want one.")
    else:
        print(f"  includes {len(cap.findings)} evaluate finding(s) captured at {cap.target_rev}")
    print("Hand this to a reviewer or a separate agent session. Every score needs a file:line citation;")
    print("uncited scores are discarded rather than averaged in.")


def do_check_brief(review: Path, project: Path | None) -> None:
    """Tell a reviewer whether their review can be read, without showing them anyone else's.

    Two of the first three real reviews were unreadable — fields read to end-of-line in one, a score in
    the heading in the other — and both were discovered only after submission, by which point the
    reviewer had moved on. A sample review would have prevented that and cost something worse: showing a
    filled-in example anchors the score, the kind of criticism, and the expected length, and round 3
    demonstrated that method decides findings. This gives format certainty with no content at all.
    """
    root = project.resolve() if project else None
    parsed = parse_brief(review.read_text(), root)
    expected = [c.id for c in CRITERIA if not c.second_run_only]
    print(f"\n{review.name}\n")
    for cid in expected:
        got = parsed.get(cid)
        if not got:
            print(f"  [ ] {cid:24} NOT READ — need a `## {cid} — …` heading with a score, or a `score:` line")
        elif got.get("score") is None:
            print(f"  [!] {cid:24} READ but discarded: {got['discarded']}")
        else:
            print(f"  [x] {cid:24} score {got['score']}"
                  + (f"   ! {len(got['unresolved'])} citation(s) do not resolve" if got.get("unresolved") else ""))
            for bad in got.get("unresolved", [])[:3]:
                print(f"         {bad}")
    ok = sum(1 for c in expected if parsed.get(c, {}).get("score") is not None)
    print(f"\n  {ok} of {len(expected)} criteria readable")
    if root is None:
        print("  (citations were not resolved — pass --project <checkout> to check them too)")
    if ok < len(expected):
        print("\n  Formatting is lenient: a fenced block, bare `score:`/`evidence:`/`why:` lines, bold\n"
              "  labels, or the score in the heading all work. `why:` runs to the next key, so indented\n"
              "  lists and per-claim breakdowns survive. What is required is the criterion id in a level-2\n"
              "  heading, a score digit, and at least one citation that resolves.")
        raise SystemExit(1)


def do_judged(path: Path, review: Path, by: str) -> None:
    root = path.resolve()
    # root is passed so citations are resolved against the tree, not merely pattern-matched
    r = review_from(review.read_text(), root.name, "", by, root=root)
    # One file per reviewer. A fixed judged.json silently clobbered the previous reviewer's record —
    # which is fatal here, because the whole point is comparing two independent scorings of the same
    # artifact, so the second parse destroyed the thing it was about to be compared against.
    dest = save_review(RESULTS / root.name / f"judged-{_slug(r.judged_by)}.json", r)
    kept, answered = r.coverage
    print(f"\n{root.name} — judged rubric ({r.judged_by})\n")
    for cid, s in r.scores.items():
        if s.get("score") is None:
            print(f"   —    {cid:24} discarded: {s['discarded']}")
        else:
            print(f"  {s['score']}/5   {cid:24} {s['why'].splitlines()[0][:70]}")
        for bad in s.get("unresolved", []):
            print(f"         ! {bad}")
    print(f"\n  artifact mean: {'n/a' if r.mean is None else round(r.mean, 2)}  "
          f"(over {kept} of {answered} answered criteria)")
    e_kept, e_answered = r.evaluate_coverage
    if e_answered:
        # Printed as a separate number, never folded in. The two are versioned separately and compared
        # under different keys — an artifact score does not depend on the archagent build and a findings
        # score does — so a single combined mean would be uninterpretable in both directions.
        print(f"  evaluate mean: {'n/a' if r.evaluate_mean is None else round(r.evaluate_mean, 2)}  "
              f"(over {e_kept} of {e_answered} answered criteria)")
    if answered and kept < answered:
        print(f"  NOT A SCORE OF THE ARTIFACT: {answered - kept} of {answered} criteria were discarded, "
              f"so this mean\n  describes the part that survived, not the artifact")
    print(f"  [uncalibrated] no agreement with a human reviewer has been measured for these criteria,")
    print(f"  so this number has unknown meaning and gates nothing (design §11, §20.2)")
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
    s.add_argument("--no-findings", action="store_true",
                   help="skip the evaluate capture (it is on by default — the output is not recoverable later)")
    s.add_argument("--repeat", action="store_true",
                   help="capture twice and check the two runs agree (costs a second evaluate run)")
    fi = sub.add_parser("findings", help="capture evaluate output on its own, without scoring")
    fi.add_argument("path"); fi.add_argument("--repeat", action="store_true")
    fi.add_argument("--until", help="bound the history, as evaluate --until")
    b = sub.add_parser("brief"); b.add_argument("path"); b.add_argument("--second-run", action="store_true")
    b.add_argument("--force", action="store_true", help="overwrite a completed review")
    cb = sub.add_parser("check-brief"); cb.add_argument("review")
    cb.add_argument("--project", help="checkout to resolve citations against")
    j = sub.add_parser("judged"); j.add_argument("path"); j.add_argument("--review", required=True)
    j.add_argument("--by", default="")
    r = sub.add_parser("run"); r.add_argument("url")
    r.add_argument("--from", dest="rev_from", required=True); r.add_argument("--to", dest="rev_to", required=True)
    args = ap.parse_args()

    if args.cmd == "run":
        do_run(args.url, args.rev_from, args.rev_to)
    if args.cmd == "brief":
        do_brief(Path(args.path), args.second_run, args.force); raise SystemExit(0)
    if args.cmd == "check-brief":
        do_check_brief(Path(args.review), Path(args.project) if args.project else None)
        raise SystemExit(0)
    if args.cmd == "judged":
        do_judged(Path(args.path), Path(args.review), args.by); raise SystemExit(0)
    if args.cmd == "findings":
        do_findings(Path(args.path), args.repeat, args.until); raise SystemExit(0)
    data = do_score(Path(args.path), args.arch_dir, args.rev,
                    skip_findings=args.no_findings, repeat=args.repeat)
    if args.out:
        out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\n  written to {out}")

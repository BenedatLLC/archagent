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
import os
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


#: Run kinds whose findings are captured twice by default. A calibration round costs hours of a
#: reviewer's time, so a second `evaluate` run is noise against it — and determinism has never once been
#: checked, which makes it exactly the assumption most likely to be wrong.
_REPEAT_BY_DEFAULT = {"calibration", "precision"}


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

    second = capture(root, repo=root.name, archagent=tool_info().stamp(),
                     captured_at=cap.captured_at, until=until) if repeat else None
    rpt = check(cap, root, repeat=second)
    if second is not None:
        # Recorded on the capture itself so the verdict travels with the data rather than living only in
        # this run's terminal output, which is where the last several determinism questions went to die.
        cap.deterministic = "no" if any(p.kind == "nondeterminism" for p in rpt.problems) else "yes"
    dest = save(RESULTS / root.name / f"findings-{cap.target_rev}.json", cap)

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


def _report_impacts(text: str, root: Path, repo: str) -> None:
    """Per-finding impact ratings — the judgement `evaluate` refuses to make (design §23.2).

    Stored beside the criterion scores rather than inside them: they are a different measurement on a
    different scale, and averaging a 0 that means "not a finding" into a 1-5 mean would be meaningless.
    """
    import json as _json

    from rubric_judged import IMPACT_SCALE, impact_summary, parse_impacts
    cap = _latest_capture(root)
    ratings = parse_impacts(text)
    if not ratings:
        return
    total = len(cap.findings) if cap else len(ratings)
    s = impact_summary(ratings, total)
    print(f"\n  finding impact — {s['rated']} rated"
          + (f", {s['unrated']} of {total} not asked about" if s['unrated'] else ""))
    for n in sorted(IMPACT_SCALE):
        if s["counts"][n]:
            label = IMPACT_SCALE[n][0]
            print(f"    {n} {label:22} {'#' * s['counts'][n]} {s['counts'][n]}")
    print(f"\n    worth acting on (3-5): {s['worth_acting_on']}    "
          f"noise (0-1): {s['noise']}    not a finding: {s['not_a_finding']}")
    dest = RESULTS / repo / f"impacts-{_slug(repo)}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_json.dumps({"summary": s, "ratings": ratings}, indent=2) + "\n")
    print(f"    written to {dest}")
    return dest


def _repeat_for(kind: str, explicit: bool | None) -> bool:
    """Whether to capture twice. An explicit `--repeat` / `--no-repeat` always wins over the kind."""
    return explicit if explicit is not None else kind in _REPEAT_BY_DEFAULT


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
    # The repo name comes from the worksheet's own title, not the directory. In a calibration package the
    # repository is checked out at `<package>/repo`, so `root.name` would file every result under "repo"
    # and the findings capture — keyed by the real name — would never be found.
    m = re.search(r"^#\s+.*?—\s*(\S+)\s*$", review.read_text(), re.MULTILINE)
    repo = m.group(1).strip("`") if m else root.name
    # Citations are resolved against this root, so pointing it at the wrong directory discards every
    # score for "no citation resolves" — which reads as a reviewer who cited nothing. The first round-5
    # ingest did exactly that and reported 0 of 6. Fail loudly instead.
    if not (root / _arch_dir(root)).is_dir():
        raise SystemExit(
            f"{root} has no architecture directory, so no citation in the review can resolve and every\n"
            f"score would be discarded as uncited. Pass the *repository* the review is about — in a\n"
            f"calibration package that is `<package>/repo`, not the package root and not the data repo.")
    # root is passed so citations are resolved against the tree, not merely pattern-matched
    r = review_from(review.read_text(), repo, "", by, root=root)
    # One file per reviewer. A fixed judged.json silently clobbered the previous reviewer's record —
    # which is fatal here, because the whole point is comparing two independent scorings of the same
    # artifact, so the second parse destroyed the thing it was about to be compared against.
    dest = save_review(RESULTS / repo / f"judged-{_slug(r.judged_by)}.json", r)
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
    _report_impacts(review.read_text(), root, repo)
    print(f"\n  written to {dest}")


def do_package(path: Path, out: Path | None = None) -> None:
    """Assemble a calibration review package: the repository, its artifact, the `evaluate` report, the
    worksheet and instructions — everything a reviewer needs, and nothing that would anchor them.

    `spotcheck.py kit` does the same job for a *blind* findings round. This one is not blind and cannot
    be: an artifact review means reading the documents, and the documents are the thing being reviewed.
    What that buys is the question a blind sheet cannot ask — how much each finding would actually matter
    — and what it costs is that these impact ratings are agreement-with-context, not blind precision. The
    write-up has to say so.
    """
    import datetime
    import shutil
    import subprocess

    from findings import capture, load, save
    from toolinfo import tool_info
    root = path.resolve()
    rev = _rev(root) or "unknown"
    out = out or Path(f"/tmp/archagent-calibration-{datetime.date.today()}")

    done = [p for p in out.glob("*.md") if _is_completed(p)]
    if done:
        raise SystemExit(f"{out} already holds a completed review ({', '.join(p.name for p in done)}).\n"
                         f"Ingest it first or pass a different --out; rebuilding would destroy it.")

    tool = tool_info()
    cap = _latest_capture(root)
    if cap is None:
        cap = capture(root, repo=root.name, archagent=tool.stamp(),
                      captured_at=datetime.date.today().isoformat())
        save(RESULTS / root.name / f"findings-{cap.target_rev}.json", cap)

    out.mkdir(parents=True, exist_ok=True)
    dest = out / "repo"
    if dest.exists():
        shutil.rmtree(dest)
    print(f"  cloning {root.name} @ {rev} …")
    # A real clone, not a worktree: a worktree's `.git` is a pointer file naming the repository it came
    # from, so every git command fails the moment the package is copied to another machine.
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(root), str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", rev], check=True)

    arch = _arch_dir(root)
    brief = render_brief(arch, root.name, second_run=False, tool=tool.stamp(),
                         target_rev=rev, findings=cap)
    sheet = out / f"worksheet-{root.name}-{rev}.md"
    sheet.write_text(brief)
    (out / "evaluate-report.txt").write_text(_evaluate_report(root))
    (out / "REVIEW.md").write_text(_package_readme(root.name, rev, arch, sheet.name, len(cap.findings)))

    print(f"\npackage at {out}")
    print(f"  repo/ @ {rev} (artifact at {arch}/), evaluate-report.txt, {sheet.name}, REVIEW.md")
    from rubric_judged import _sample_findings
    sampled, total = _sample_findings(cap.findings)
    print(f"  {len(sampled)} of {total} finding(s) to rate for impact"
          if len(sampled) < total else f"  {total} finding(s) to rate for impact")


def _evaluate_report(root: Path) -> str:
    """The rendered `evaluate` output, captured as text.

    Included as well as the findings in the worksheet because the *report* is what a user actually meets:
    the ordering, the coverage section naming what did not run, the caveats. A reviewer judging whether a
    report is usable needs the report, not a reconstruction of it.
    """
    import subprocess
    r = subprocess.run(["uv", "run", "archagent", "evaluate", "--project", str(root)],
                       cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"})
    return r.stdout or "(evaluate produced no output)"


def _package_readme(repo: str, rev: str, arch: str, sheet: str, n_findings: int) -> str:
    return f"""# Reviewing the architecture documentation for `{repo}`

Thank you for doing this. Expect two to three hours. Everything you need is in this directory — nothing
to clone, install or configure.

## What this is

`archagent` reads a codebase and writes architecture documentation for it, then checks that documentation
back against the code and reports where the *design itself* may have problems. You are reviewing both
halves, on a real repository:

| | |
|---|---|
| `repo/` | `{repo}` at `{rev}`, with the generated documentation in `repo/{arch}/` |
| `evaluate-report.txt` | what `archagent evaluate` reported about that architecture |
| `{sheet}` | **the worksheet — open this and work through it** |

## The worksheet has two parts

**Part one — the documentation.** Six criteria about what `describe` wrote: is it accurate, is anything
significant missing, can a person read it, are the diagrams worth their space, do the invariants protect
anything. Score each 1–5 against the anchors given.

**Part two — the findings.** {n_findings} architectural problems the tool believes it found. Three
criteria about the *report* — could you act on it, does it claim more than it showed, is it clear about
what it never checked — and then **an impact rating for each individual finding**, from *trivial* to
*project-threatening*.

That per-finding rating is the judgement the tool deliberately refuses to make. Its own severity counts
files and commits; it says nothing about whether anything would actually break. Only someone reading the
code can say that, which is why you are being asked.

## Two things that make a review usable

**Cite what you judged from.** A score with a `file:line` behind it can be checked and argued with; one
without it cannot be distinguished from a guess. Uncited scores are discarded rather than averaged in —
not as a penalty, but because an artifact review is mostly prose and fluent prose with nothing behind it
is the failure mode this instrument exists to catch.

**Score `0` when you are unsure**, on any criterion, and say why. It is excluded from the average rather
than counted against the tool. A guessed number is worse than an honest gap, because nothing downstream
can tell the two apart.

For a finding, `impact: 0` means something different — *this describes nothing real*. That is deliberately
not the bottom of the impact scale: "wrong" and "unimportant" are different failures and the fix for each
is different.

## Please be harsh

The most useful review this project has received found errors in **both** directions from the person who
built the checks. Findings that look impressive and mean nothing are the specific thing we are trying to
detect, and a polite review cannot detect them. If a finding is real and still not worth anyone's time,
say `1` — a tool that reports true trivia trains people to skim, and accuracy does not recover from that.

## Checking your work parses

The worksheet is lenient about formatting, and you can verify it reads before handing it back:

```bash
python scripts/selfeval.py check-brief <this-worksheet> --project <path-to-repo/>
```

It reports which criteria were read and which citations resolve. It shows you no one else's review —
deliberately, since a filled-in example would anchor your scores, the kind of problem you look for, and
how much you write.

## When you are done

Send back `{sheet}`. Nothing else is needed.
"""


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
    s.add_argument("--kind", default="scoring", choices=sorted({"scoring", "calibration", "precision",
                                                               "noise-floor", "checklist", "recurrence"}),
                   help="the run kind; calibration and precision capture findings twice by default")
    s.add_argument("--repeat", dest="repeat", action="store_true", default=None,
                   help="capture twice and check the two runs agree (costs a second evaluate run)")
    s.add_argument("--no-repeat", dest="repeat", action="store_false",
                   help="capture once even on a calibration run")
    pk = sub.add_parser("package", help="assemble a calibration review package for someone else")
    pk.add_argument("path"); pk.add_argument("--out", default="")
    fi = sub.add_parser("findings", help="capture evaluate output on its own, without scoring")
    fi.add_argument("path")
    fi.add_argument("--kind", default="scoring")
    fi.add_argument("--repeat", dest="repeat", action="store_true", default=None)
    fi.add_argument("--no-repeat", dest="repeat", action="store_false")
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
    if args.cmd == "package":
        do_package(Path(args.path), Path(args.out).expanduser() if args.out else None)
        raise SystemExit(0)
    if args.cmd == "findings":
        do_findings(Path(args.path), _repeat_for(args.kind, args.repeat), args.until)
        raise SystemExit(0)
    data = do_score(Path(args.path), args.arch_dir, args.rev, skip_findings=args.no_findings,
                    repeat=_repeat_for(args.kind, args.repeat))
    if args.out:
        out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\n  written to {out}")

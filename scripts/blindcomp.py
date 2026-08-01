#!/usr/bin/env python
"""Blind comparison of the skill layer (`docs/designs/evaluating-archagent.md` §10).

    python scripts/blindcomp.py prepare [--repo litellm]   # write the three identical briefs
    python scripts/blindcomp.py score   <dir>              # blind, score objectively, then unblind

**Why generation is not automated here.** The three arms have to be written by a model, and this session
is a model. One session writing arm A (its own guidance), arm B and arm C, and then grading all three,
would measure self-preference, not quality — the exact failure §10 warns about when judge and author share
a model family. So `prepare` writes briefs for someone else to run, and `score` accepts whatever comes
back.

**What is scored here is the objective half only** — whether each report reaches the verdicts the corpus
pass established by reading code, plus machine-checkable report hygiene. §13.2 requires that anything
gating a decision be objective, so this is the half that would carry a decision even once a judge exists.
The judged criteria of §9 need a model, and per §11 an uncalibrated judge is a number of unknown meaning.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from blindcomp import ARMS, Blinded, blind, build_input, load_truth, score_objective, unblind  # noqa: E402

CORPUS = ROOT / "tests" / "corpus"
TRUTH = ROOT / "tests" / "blindcomp_truth.toml"
OUT = ROOT / "evaluations" / "blind-comparison"

BRIEFS = {
    "A": ("Follow the archagent `evaluate` skill exactly as shipped "
          "(src/archagent/templates/agent/phases/evaluate.md). Read it first, then produce the report it "
          "describes for the findings in findings.json."),
    "B": ("Here are some architecture findings for a codebase. Write a report on them for the "
          "development team."),
    "C": ("Here are some architecture findings. Each carries the tool's own recommendation text. "
          "Produce a report. No further guidance is given."),
}


def do_prepare(repo: str) -> None:
    path = CORPUS / f"{repo}.json"
    if not path.is_file():
        raise SystemExit(f"no recorded corpus expectation for {repo}; have: "
                         f"{', '.join(p.stem for p in CORPUS.glob('*.json'))}")
    findings = json.loads(path.read_text())["findings"]
    payload = build_input(findings, repo)
    run = OUT / repo
    run.mkdir(parents=True, exist_ok=True)
    (run / "findings.json").write_text(json.dumps(payload["payload"], indent=2) + "\n")
    for arm, brief in BRIEFS.items():
        d = run / f"arm-{arm}"
        d.mkdir(exist_ok=True)
        (d / "BRIEF.md").write_text(
            f"# Arm {arm} — {ARMS[arm]}\n\n"
            f"Input digest: `{payload['digest']}` (identical across all three arms; if yours differs, the\n"
            f"comparison is invalid).\n\n## Instructions\n\n{brief}\n\n"
            f"Write your report to `report.md` in this directory. Do not read the other arms' briefs or\n"
            f"reports, and do not read `../../../tests/blindcomp_truth.toml`.\n")
    print(f"prepared {run} — {len(findings)} findings, digest {payload['digest']}")
    print("each arm/BRIEF.md is for a separate session; collect report.md files, then run `score`")


def do_score(run: Path) -> None:
    truth = load_truth(TRUTH)
    reports = {}
    for arm in ARMS:
        p = run / f"arm-{arm}" / "report.md"
        if p.is_file():
            reports[arm] = p.read_text()
    if len(reports) < 2:
        raise SystemExit(f"need at least two arms' report.md under {run}; found {sorted(reports)}")

    n_findings = len(json.loads((run / "findings.json").read_text())["findings"])
    blinded, manifest = blind(reports)
    scores = [score_objective(b, truth, n_findings) for b in blinded]     # scored without the arm
    scores = unblind(scores, manifest)

    print(f"\n{run.name}: {len(reports)} arm(s), {len(truth)} ground-truth verdicts\n")
    print(f"  {'arm':4} {'ground truth':>13} {'cites':>6} {'clustered':>10}  tells")
    for s in sorted(scores, key=lambda x: x.arm or ""):
        print(f"  {s.arm:4} {s.to_dict()['ground_truth']:>13} {str(s.cites_evidence):>6} "
              f"{str(s.clustered):>10}  {', '.join(s.tells_present) or '-'}")
        for m in s.missed:
            print(f"       missed: {m}")
    (run / "objective-scores.json").write_text(
        json.dumps([s.to_dict() for s in scores], indent=2) + "\n")
    print(f"\n  written to {run / 'objective-scores.json'}")
    print("  objective half only — the judged criteria of §9 need a model, calibrated per §11")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--repo", default="litellm")
    s = sub.add_parser("score"); s.add_argument("dir")
    a = ap.parse_args()
    do_prepare(a.repo) if a.cmd == "prepare" else do_score(Path(a.dir))

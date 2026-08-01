#!/usr/bin/env python
"""Human spot-check and calibration (`docs/designs/evaluating-archagent.md` §11).

    python scripts/spotcheck.py generate [--cap 30] [--reviewer NAME]
    python scripts/spotcheck.py ingest   <worksheet.md> [--reviewer NAME] [--note "..."]
    python scripts/spotcheck.py report

`generate` samples findings across signals, confidence tiers and repositories and writes a worksheet with
the tool's own severity, confidence and recommendation **withheld** — they go to a side file the reviewer
never opens, and are revealed at ingest. Items that already carry a label are not asked about again.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from spotcheck import (                                    # noqa: E402
    Label, LabelStore, finding_key, parse_worksheet, precision_by_sign, render_worksheet,
    stratified_sample, values_of,
)

CORPUS = ROOT / "tests" / "corpus"
LABELS = ROOT / "evaluations" / "labels"
SHEETS = ROOT / "evaluations" / "spotcheck"
JUDGED = ("scattered-source-of-truth", "enum-value-escape", "change-prone-file")


def collect(signs: tuple[str, ...] = JUDGED) -> list[dict]:
    """Findings from every recorded corpus expectation — pinned revisions, so a worksheet is reproducible."""
    items = []
    for path in sorted(CORPUS.glob("*.json")):
        data = json.loads(path.read_text())
        for f in data.get("findings", []):
            if f["sign"] not in signs:
                continue
            vals = f.get("values")
            key = finding_key(f["sign"], f["subjects"], vals)
            others = f["subjects"][1:]
            evidence = [f"- owner: `{f['subjects'][0]}`"]
            if others:
                evidence.append(f"- also: {', '.join('`' + s + '`' for s in others[:6])}"
                                + (f" (+{len(others) - 6} more)" if len(others) > 6 else ""))
            if vals:
                evidence.append(f"- values: {', '.join(vals[:10])}")
            items.append({
                "key": key, "repo": path.stem, "rev": "(pinned)", "sign": f["sign"],
                "confidence": f.get("confidence", ""), "evidence": "\n".join(evidence),
                "tool_claim": {k: f.get(k) for k in ("severity", "confidence", "regime")},
                "evidence_hash": "|".join(f["subjects"]) + "|" + ",".join(vals or []),
            })
    return items


def do_generate(cap: int, reviewer: str, signs: tuple[str, ...]) -> None:
    store = LabelStore(LABELS)
    items = collect(signs)
    already = {k for it in items for k in store.load(it["repo"])}
    fresh = [it for it in items if it["key"] not in already]
    print(f"{len(items)} findings across {len({i['repo'] for i in items})} repos; "
          f"{len(items) - len(fresh)} already labelled")
    picked = stratified_sample(fresh, cap=cap)
    sheet, withheld = render_worksheet(picked, reviewer)
    sheet = sheet.replace("---\n", _checkout_section({i["repo"] for i in picked}) + "\n---\n", 1)
    SHEETS.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    (SHEETS / f"worksheet-{stamp}.md").write_text(sheet)
    (SHEETS / f"worksheet-{stamp}.withheld.json").write_text(
        json.dumps({"items": {i["key"]: i for i in picked}, "withheld": withheld}, indent=2) + "\n")
    print(f"wrote {SHEETS / f'worksheet-{stamp}.md'} ({len(picked)} items)")
    print("the tool's severity/confidence are in the .withheld.json side file — do not read it first")


def _checkout_section(repos: set[str]) -> str:
    """A reviewer cannot judge `litellm/main.py` without `litellm/main.py` at the pinned revision. The
    worksheet carries the commands rather than assuming the reader will work them out."""
    import tomllib
    manifest = {e["name"]: e for e in
                tomllib.loads((ROOT / "tests" / "corpus_manifest.toml").read_text())["repo"]}
    lines = ["", "## Getting the code", "",
             "Each finding is judged against the repository **at the revision it was found at**. These",
             "commands put each one in `/tmp`, reusing the cached clones:", "", "```bash"]
    for name in sorted(repos):
        e = manifest.get(name)
        if not e:
            continue
        lines.append(f"git -C ~/.cache/archagent/corpus/{name}.git worktree add --detach "
                     f"/tmp/review-{name} {e['rev']}")
    lines += ["```", "",
              "When you are done: `git -C ~/.cache/archagent/corpus/<name>.git worktree remove "
              "--force /tmp/review-<name>`", ""]
    return "\n".join(lines)


def do_ingest(path: Path, reviewer: str, note: str) -> None:
    side = path.with_suffix("").with_suffix(".withheld.json")
    if not side.is_file():
        raise SystemExit(f"missing side file {side} — it holds the evidence hashes and the withheld claims")
    meta = json.loads(side.read_text())
    answers = parse_worksheet(path.read_text())
    store = LabelStore(LABELS)
    n = 0
    for key, ans in answers.items():
        it = meta["items"].get(key)
        if not it:
            print(f"  skipping unknown item {key}")
            continue
        store.record(Label(key=key, repo=it["repo"], sign=it["sign"], verdict=ans["verdict"],
                           why=ans["why"], reviewer=reviewer or "(unrecorded)",
                           dated=date.today().isoformat(),
                           tool_claim=meta["withheld"].get(key, {}),
                           evidence=it.get("evidence_hash", "")), note=note)
        n += 1
    print(f"recorded {n} label(s) into {LABELS}")


def do_report() -> None:
    store = LabelStore(LABELS)
    labels = [l for p in sorted(LABELS.glob("*.jsonl")) for l in store.load(p.stem).values()]
    if not labels:
        raise SystemExit("no labels yet — run `generate`, fill the worksheet, then `ingest`")
    print(f"{len(labels)} label(s) by {', '.join(sorted({l.reviewer for l in labels}))}\n")
    print(f"{'signal':28} {'n':>3} {'conf':>5} {'part':>5} {'dism':>5} "
          f"{'strict':>7} {'95% CI':>14} {'lenient':>8} {'95% CI':>14}")
    for sign, s in precision_by_sign(labels).items():
        st = "n/a" if s["precision_strict"] is None else f"{s['precision_strict']:.0%}"
        le = "n/a" if s["precision_lenient"] is None else f"{s['precision_lenient']:.0%}"
        print(f"{sign:28} {s['n']:>3} {s['confirmed']:>5} {s['partial']:>5} {s['dismissed']:>5} "
              f"{st:>7} [{s['ci95_strict'][0]:.2f}, {s['ci95_strict'][1]:.2f}] {le:>8} "
              f"[{s['ci95_lenient'][0]:.2f}, {s['ci95_lenient'][1]:.2f}]")
    print("\nIntervals are Wilson, which stays inside [0,1] at these sample sizes.")
    print("Precision here is by a human reviewer; agreement with a model judge needs judge verdicts too.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--cap", type=int, default=30)
    g.add_argument("--reviewer", default="")
    g.add_argument("--signs", default=",".join(JUDGED),
                   help="comma-separated signs to sample from; defaults to all judged kinds")
    i = sub.add_parser("ingest"); i.add_argument("worksheet"); i.add_argument("--reviewer", default=""); i.add_argument("--note", default="")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "generate":
        do_generate(a.cap, a.reviewer, tuple(s.strip() for s in a.signs.split(",") if s.strip()))
    elif a.cmd == "ingest":
        do_ingest(Path(a.worksheet), a.reviewer, a.note)
    else:
        do_report()

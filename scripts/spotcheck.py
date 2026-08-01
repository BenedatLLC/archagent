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


def collect() -> list[dict]:
    """Findings from every recorded corpus expectation — pinned revisions, so a worksheet is reproducible."""
    items = []
    for path in sorted(CORPUS.glob("*.json")):
        data = json.loads(path.read_text())
        for f in data.get("findings", []):
            if f["sign"] not in JUDGED:
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


def do_generate(cap: int, reviewer: str) -> None:
    store = LabelStore(LABELS)
    items = collect()
    already = {k for it in items for k in store.load(it["repo"])}
    fresh = [it for it in items if it["key"] not in already]
    print(f"{len(items)} findings across {len({i['repo'] for i in items})} repos; "
          f"{len(items) - len(fresh)} already labelled")
    picked = stratified_sample(fresh, cap=cap)
    sheet, withheld = render_worksheet(picked, reviewer)
    SHEETS.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    (SHEETS / f"worksheet-{stamp}.md").write_text(sheet)
    (SHEETS / f"worksheet-{stamp}.withheld.json").write_text(
        json.dumps({"items": {i["key"]: i for i in picked}, "withheld": withheld}, indent=2) + "\n")
    print(f"wrote {SHEETS / f'worksheet-{stamp}.md'} ({len(picked)} items)")
    print("the tool's severity/confidence are in the .withheld.json side file — do not read it first")


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
    print(f"{'signal':30} {'n':>4} {'confirmed':>10} {'precision':>10}  95% CI      unsure")
    for sign, s in precision_by_sign(labels).items():
        p = "n/a" if s["precision"] is None else f"{s['precision']:.0%}"
        print(f"{sign:30} {s['n']:>4} {s['confirmed']:>10} {p:>10}  "
              f"[{s['ci95'][0]:.2f}, {s['ci95'][1]:.2f}]  {s['unsure']}")
    print("\nIntervals are Wilson, which stays inside [0,1] at these sample sizes.")
    print("Precision here is by a human reviewer; agreement with a model judge needs judge verdicts too.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--cap", type=int, default=30); g.add_argument("--reviewer", default="")
    i = sub.add_parser("ingest"); i.add_argument("worksheet"); i.add_argument("--reviewer", default=""); i.add_argument("--note", default="")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "generate":
        do_generate(a.cap, a.reviewer)
    elif a.cmd == "ingest":
        do_ingest(Path(a.worksheet), a.reviewer, a.note)
    else:
        do_report()

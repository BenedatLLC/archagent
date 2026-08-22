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

from evalhome import eval_dir   # noqa: E402

from spotcheck import (                                    # noqa: E402
    GROUPS, Label, LabelStore, evidence_is_usable, finding_key, parse_worksheet, precision_by_sign,
    render_worksheet, signs_in, stratified_sample, values_of,
)

CORPUS = ROOT / "tests" / "corpus"
RESULTS = eval_dir("selfeval")
LABELS = eval_dir("labels")
SHEETS = eval_dir("spotcheck")
JUDGED = ("scattered-source-of-truth", "enum-value-escape", "change-prone-file")


def _item(f: dict, repo: str, rev: str) -> dict:
    """One finding, rendered as worksheet evidence with the tool's claim stripped out.

    `detail` is included and `recommendation` is not, and the split is the whole design. `detail` is the
    measurement — which subsystems, which direction, how many co-changes — and a reviewer needs it.
    `recommendation` is the tool's opinion about what to do, and showing it would anchor the verdict this
    exercise exists to collect independently. Severity and confidence go to the side file for the same
    reason.
    """
    vals = f.get("values") or values_of(f.get("detail", ""))
    key = finding_key(f["sign"], f["subjects"], vals)
    others = f["subjects"][1:]
    evidence = [f"- owner: `{f['subjects'][0]}`"] if f["subjects"] else []
    if others:
        evidence.append(f"- also: {', '.join('`' + s + '`' for s in others[:6])}"
                        + (f" (+{len(others) - 6} more)" if len(others) > 6 else ""))
    if vals:
        evidence.append(f"- values: {', '.join(vals[:10])}")
    if f.get("detail"):
        evidence.append(f"- measured: {f['detail']}")
    return {
        "key": key, "repo": repo, "rev": rev, "sign": f["sign"], "group": f.get("group", ""),
        "confidence": f.get("confidence", ""), "evidence": "\n".join(evidence),
        "tool_claim": {k: f.get(k) for k in ("severity", "confidence", "regime", "recommendation")},
        "evidence_hash": "|".join(f["subjects"]) + "|" + ",".join(vals or []),
    }


def collect(signs: tuple[str, ...] = JUDGED) -> tuple[list[dict], list[dict]]:
    """`(usable, unusable)` — findings from both sources, split on whether a reviewer could judge them.

    **Two sources, because neither covers the signals alone.** The pinned corpus baselines
    (`tests/corpus/*.json`) hold real findings at fixed revisions, but they are regression baselines: they
    store only the fields that must not change, so `detail` and `recommendation` are stripped. That is
    fine for groups E and F, whose evidence is a file or a value set, and useless for B and C, whose
    evidence *is* the detail line.

    The `evaluate` captures written by each describe run (`findings.py`) keep the whole record — and they
    are also the only source where B and C fire at all, since those signals need the `**Tier:**` and
    `**Connects:**` metadata that only a repository with an archagent artifact has. The corpus
    repositories have no artifact, which is why four groups have never been labelled.

    Unusable items are returned rather than dropped, so `generate` can say what it could not ask about.
    """
    usable, unusable = [], []
    for path in sorted(CORPUS.glob("*.json")):
        data = json.loads(path.read_text())
        for f in data.get("findings", []):
            if f["sign"] in signs:
                (usable if evidence_is_usable(_item(f, path.stem, "(pinned)")["evidence"])
                 else unusable).append(_item(f, path.stem, "(pinned)"))
    for path in sorted(RESULTS.glob("*/findings-*.json")):
        cap = json.loads(path.read_text())
        for f in cap.get("findings", []):
            if f["sign"] in signs:
                it = _item(f, cap["repo"], cap["target_rev"])
                (usable if evidence_is_usable(it["evidence"]) else unusable).append(it)
    # A finding can be reached from both sources; the capture wins because it carries more.
    seen: dict[str, dict] = {}
    for it in usable:
        if it["key"] not in seen or len(it["evidence"]) > len(seen[it["key"]]["evidence"]):
            seen[it["key"]] = it
    return list(seen.values()), [u for u in unusable if u["key"] not in seen]


def do_generate(cap: int, reviewer: str, signs: tuple[str, ...]) -> None:
    store = LabelStore(LABELS)
    items, unusable = collect(signs)
    already = {k for it in items for k in store.load(it["repo"])}
    fresh = [it for it in items if it["key"] not in already]
    repos = {i["repo"] for i in items}
    print(f"{len(items)} findings across {len(repos)} repos; "
          f"{len(items) - len(fresh)} already labelled")
    if unusable:
        # Named, never silently dropped. A worksheet that quietly omitted them would report a smaller
        # denominator as if it were the whole population.
        by_sign: dict[str, int] = {}
        for u in unusable:
            by_sign[u["sign"]] = by_sign.get(u["sign"], 0) + 1
        print(f"{len(unusable)} finding(s) SKIPPED for want of evidence a reviewer could judge — "
              f"the pinned corpus stores no `detail`, so these are unaskable from that source:")
        for s, n in sorted(by_sign.items()):
            print(f"    {s}: {n}")
        print("    fix: capture `evaluate` on a repo that has an artifact "
              "(`selfeval.py findings <path>`), which keeps the whole record")
    if not fresh:
        raise SystemExit("nothing left to label for those signs")
    if len(repos) < 2:
        # Round 1's estimate rested on two findings per repository and the threshold run hit the same
        # wall. Saying it here beats discovering it in the write-up.
        print(f"\n  WARNING: every item comes from one repository ({', '.join(repos)}). Precision from a "
              f"single repo\n  describes that repo, not the signal — quote it with the interval and the "
              f"source, or widen first.")
    picked = stratified_sample(fresh, cap=cap)
    sheet, withheld = render_worksheet(picked, reviewer)
    sheet = sheet.replace("---\n", _checkout_section({i["repo"]: i.get("rev", "") for i in picked})
                          + "\n---\n", 1)
    SHEETS.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    (SHEETS / f"worksheet-{stamp}.md").write_text(sheet)
    (SHEETS / f"worksheet-{stamp}.withheld.json").write_text(
        json.dumps({"items": {i["key"]: i for i in picked}, "withheld": withheld}, indent=2) + "\n")
    print(f"wrote {SHEETS / f'worksheet-{stamp}.md'} ({len(picked)} items)")
    print("the tool's severity/confidence are in the .withheld.json side file — do not read it first")


def _checkout_section(repos: dict[str, str]) -> str:
    """A reviewer cannot judge `litellm/main.py` without `litellm/main.py` at the pinned revision. The
    worksheet carries the commands rather than assuming the reader will work them out.

    Takes `{repo: rev}` rather than a set of names, because findings now also come from `evaluate`
    captures on repositories that are not in the corpus manifest — archagent itself, and any target a
    describe round ran against. The earlier version skipped anything it could not find a manifest entry
    for, so those repositories vanished from the instructions while their items stayed on the sheet: the
    reviewer would see commands for one repository and silently have no idea where the others came from.
    """
    import tomllib
    manifest = {e["name"]: e for e in
                tomllib.loads((ROOT / "tests" / "corpus_manifest.toml").read_text())["repo"]}
    lines = ["", "## Getting the code", "",
             "Each finding is judged against the repository **at the revision it was found at** — shown "
             "on every item.", ""]
    cached = {n: r for n, r in repos.items() if n in manifest}
    other = {n: r for n, r in repos.items() if n not in manifest}
    if cached:
        lines += ["These reuse the cached clones:", "", "```bash"]
        for name, rev in sorted(cached.items()):
            lines.append(f"git -C ~/.cache/archagent/corpus/{name}.git worktree add --detach "
                         f"/tmp/review-{name} {rev or manifest[name]['rev']}")
        lines += ["```", "",
                  "When you are done: `git -C ~/.cache/archagent/corpus/<name>.git worktree remove "
                  "--force /tmp/review-<name>`", ""]
    if other:
        lines += ["These are not corpus repositories — check each out yourself at the revision named:", ""]
        lines += [f"- **{n}** at `{r or '(revision unrecorded)'}`" for n, r in sorted(other.items())]
        lines.append("")
    lines += [
        "### The architecture documents are part of the evidence",
        "",
        "Several signals compare what the documents *declare* against what the code *does* — a layering",
        "finding asserts two `**Tier:**` values and an import, and only one of those three is in the code.",
        "So read the artifact alongside the source; it is not the thing under review here, it is half of",
        "each claim.",
        "",
        "A corpus repository has no artifact of its own. The one these findings were produced from lives",
        "in the evaluation data repo, and goes back into the worktree like this:",
        "",
        "```bash",
        "cp -r $ARCHAGENT_EVAL_HOME/selfeval/<name>/artifact /tmp/review-<name>/architecture",
        "cp $ARCHAGENT_EVAL_HOME/selfeval/<name>/archagent.toml /tmp/review-<name>/   # if one is stored",
        "```",
        "",
    ]
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
    g.add_argument("--signs", default="",
                   help="comma-separated signs to sample from; defaults to all judged kinds")
    g.add_argument("--groups", default="",
                   help="comma-separated signal groups (e.g. B,C) — an alternative to --signs")
    i = sub.add_parser("ingest"); i.add_argument("worksheet"); i.add_argument("--reviewer", default=""); i.add_argument("--note", default="")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "generate":
        if a.signs and a.groups:
            raise SystemExit("pass --signs or --groups, not both")
        signs = (signs_in(a.groups) if a.groups
                 else tuple(s.strip() for s in a.signs.split(",") if s.strip()) or JUDGED)
        do_generate(a.cap, a.reviewer, signs)
    elif a.cmd == "ingest":
        do_ingest(Path(a.worksheet), a.reviewer, a.note)
    else:
        do_report()

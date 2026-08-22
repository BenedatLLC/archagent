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
    sheet, withheld = render_worksheet(picked, reviewer, sheet=f"worksheet-{date.today().isoformat()}")
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


def _run(*args, cwd=None) -> None:
    import subprocess
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(args)}\n{r.stderr.strip()}")


def _fill_blobs(src: Path, rev: str) -> None:
    """Make a blobless corpus mirror complete enough to clone from.

    The mirrors are partial clones (`--filter=blob:none`) so that a `git log --name-only` walk is cheap,
    which is all the corpus regression ever needed. File *contents* arrive on demand — through the
    promisor remote, which a plain local clone of the mirror does not inherit. So the clone succeeds, the
    checkout fails on whichever blobs were never materialised, and git reports it as
    `unable to read sha1 file` — a message that reads like a corrupt repository rather than a filter.

    Nothing about the kit works around this. It just fills the mirror once, which needs the network and
    is the reason the failure is worth handling here rather than leaving as a footnote.
    """
    import subprocess
    r = subprocess.run(["git", "-C", str(src), "config", "--get", "remote.origin.promisor"],
                       capture_output=True, text=True)
    if r.stdout.strip() != "true":
        return
    missing = subprocess.run(["git", "-C", str(src), "rev-list", "--objects", "--missing=print", rev],
                             capture_output=True, text=True)
    if not any(ln.startswith("?") for ln in missing.stdout.splitlines()):
        return
    print(f"  {src.name} is a blobless mirror and is missing file contents — refetching "
          f"(needs the network, once) …")
    _run("git", "-C", str(src), "fetch", "--refetch", "--no-filter", "origin")


def do_kit(worksheet: Path, out: Path, source: dict[str, Path]) -> None:
    """Assemble a self-contained review kit: the sheet, plus each repository at the revision it was
    judged at, with the architecture documents in place.

    Written because a review is handed to someone who does not have the corpus mirrors, the evaluation
    data repo, or any reason to know how the two fit together. Round 1's reviewer got a worksheet and a
    set of instructions; two of the first three reviews came back unreadable for setup reasons, and every
    hour spent reconstructing state is an hour not spent reading code.

    Three things this gets right that a hand-assembled directory does not:

    **Real clones, never worktrees.** A `git worktree` puts a *pointer file* at `.git` naming the
    repository it came from. It works perfectly until the directory is copied to another machine, at
    which point every git command fails — and the failure looks like a corrupt kit rather than a wrong
    packaging choice.

    **History included.** `unstable-interface` is half a co-change claim, and the reviewer is asked
    whether those files really do change together. `git archive` would give a smaller, cleaner tree that
    cannot answer five of the fourteen questions.

    **The withheld file is not copied, and that is asserted rather than assumed.** It holds the severity,
    confidence and recommendation this whole exercise depends on the reviewer not having seen.
    """
    side = worksheet.with_suffix("").with_suffix(".withheld.json")
    if not side.is_file():
        raise SystemExit(f"missing side file {side}")
    meta = json.loads(side.read_text())
    revs: dict[str, str] = {}
    for it in meta["items"].values():
        revs.setdefault(it["repo"], it.get("rev", ""))

    out.mkdir(parents=True, exist_ok=True)
    (out / "repos").mkdir(exist_ok=True)
    placed = {}
    for repo, rev in sorted(revs.items()):
        src = source.get(repo)
        if src is None:
            print(f"  ! no source known for {repo} — pass --source {repo}=<path to a clone or mirror>")
            continue
        dest = out / "repos" / repo
        _fill_blobs(src, rev)
        print(f"  cloning {repo} @ {rev} …")
        _run("git", "clone", "--quiet", "--no-hardlinks", str(src), str(dest))
        _run("git", "-C", str(dest), "checkout", "--quiet", "--detach", rev)
        # An artifact the repository does not carry itself. fastapi-template is the case: the findings
        # were produced against a description stored in the evaluation data repo, and without it the
        # layering items name tiers that appear nowhere in the kit.
        stored = RESULTS / repo / "artifact"
        if stored.is_dir() and not (dest / "architecture").exists() \
                and not (dest / "docs" / "architecture").exists():
            import shutil
            shutil.copytree(stored, dest / "architecture")
            toml = RESULTS / repo / "archagent.toml"
            if toml.is_file():
                shutil.copy(toml, dest / "archagent.toml")
            print(f"    + architecture/ (from the evaluation data repo)")
        placed[repo] = rev

    # The sheet's own "Getting the code" section describes work the kit has already done. Left in, it
    # would send the reviewer to clone into /tmp and judge a different checkout than the one beside it.
    text = worksheet.read_text()
    start = text.find("\n## Getting the code")
    end = text.find("\n---", start) if start != -1 else -1
    if start != -1 and end != -1:
        text = text[:start] + text[end:]
    # Named after the run, not `worksheet.md`. The sheet carries its own id so a rename is safe, but a
    # reviewer who strips the header still gets a file that drops straight in beside its side file.
    (out / worksheet.name).write_text(text)

    (out / "REVIEW.md").write_text(_kit_readme(placed, worksheet.name, len(meta["items"])))
    assert not list(out.rglob("*.withheld.json")), "the withheld claims must not ship in a review kit"
    print(f"\nkit at {out}")
    print(f"  {len(placed)} repo(s), {worksheet.name}, REVIEW.md — and no withheld file")


def _kit_readme(placed: dict[str, str], sheet_name: str, n_items: int) -> str:
    rows = "\n".join(f"| `{r}` | `{rev}` | `repos/{r}/` |" for r, rev in sorted(placed.items()))
    return f"""# archagent finding review

Thank you for doing this. It should take an hour or two. Everything you need is in this directory —
nothing to clone, install or configure.

## What you are judging

`archagent` reads a codebase and its architecture documents, and reports **candidate signals**: places
the structure may have a problem. This review asks whether those candidates are any good. We have never
checked these particular kinds of finding against an independent reader, which is the entire reason you
are being asked.

**Open `{sheet_name}` and work through the {n_items} items.** Each gives you a repository, a revision, and the
evidence the tool used. Record a verdict and a one-line reason in the fenced block.

## Two questions per item, in this order

1. **Is the measurement true?** Most items assert several separate facts. `extraction (infra) depends up
   on drift (domain)` claims that `extraction` is *declared* infra, that `drift` is *declared* domain,
   and that one imports the other. The first two are in the architecture documents; the third is in the
   code.
2. **If it is true, is it a real problem worth acting on?** A correct measurement can still be a
   non-finding — a test package depending on the code it tests is what tests are for.

Saying which of the two failed is the most useful thing you can write. It is the difference between a
check that is broken and a check whose threshold is wrong.

## The architecture documents are half the evidence

These signals compare what the documents **declare** against what the code **does**, so read both. The
documents are inside each repository:

| Repository | Revision | Where |
|---|---|---|
{rows}

Look for `architecture/` or `docs/architecture/`. The `**Tier:**`, `**Connects:**` and `**Covers:**`
lines at the top of each `subsystems/*.md` are what the findings are built from.

The git history is present too — some items claim files change together, and `git log` is how you check
that.

## Verdicts

- `confirm` — a real problem worth acting on.
- `dismiss` — not a problem here. Say why.
- `partial` — **something real is here, but not what the finding claims.** The most useful verdict we
  have, and easy to forget you have it.
- `unsure` — a real answer. It is excluded from the scoring rather than counted against the tool.

A finding that is real but **already accepted** — you will find one recorded in an ADR as a known cost —
is a `confirm` with a note. The signal did its job.

## Please do not

- Look for our severity ratings or recommendations. They are deliberately not in this kit: if you see
  what the tool concluded, this measures whether you agree with us rather than whether we are right.
- Worry about being harsh. Round 1 found errors in **both** directions from the person who built the
  checks, which is exactly what made it worth doing.

## When you are done

Send back `{sheet_name}`. Rename it however you like — add your own name to it if that helps — as
long as the `<!-- spotcheck-sheet: ... -->` comment near the top of the file survives. That line is
how the results are matched back to the run. Nothing else is needed.
"""


def _side_file(path: Path) -> Path:
    """The withheld claims belonging to a completed sheet.

    Tried in order: the id the sheet carries in its own header, then a sibling with the matching name.
    The sibling rule alone required the reviewer to return a file with the exact basename it was
    generated under, and the two most natural things a person does — add their name to it, or save it
    out of the review kit, where it is called `worksheet.md` — both broke it. The error then named a
    missing file, which reads as data loss rather than as a rename.
    """
    from spotcheck import sheet_id
    sid = sheet_id(path.read_text(errors="replace"))
    if sid:
        by_id = SHEETS / f"{sid}.withheld.json"
        if by_id.is_file():
            return by_id
    return path.with_suffix("").with_suffix(".withheld.json")


def do_ingest(path: Path, reviewer: str, note: str) -> None:
    side = _side_file(path)
    if not side.is_file():
        raise SystemExit(
            f"cannot find the withheld claims for {path.name}.\n"
            f"Looked for {side}.\n\n"
            f"The sheet should carry a `<!-- spotcheck-sheet: ... -->` line naming its run; if it was "
            f"stripped,\nput the completed sheet next to its `.withheld.json` under {SHEETS} and give it "
            f"the same basename.")
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
    k = sub.add_parser("kit", help="assemble a self-contained review kit for someone else")
    k.add_argument("worksheet")
    k.add_argument("--out", default="", help="output directory (default /tmp/archagent-review-<date>)")
    k.add_argument("--source", action="append", default=[], metavar="REPO=PATH",
                   help="where to clone a repository from; repeatable")
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
    elif a.cmd == "kit":
        src = {}
        for s in a.source:
            name, _, where = s.partition("=")
            src[name] = Path(where).expanduser()
        # Two sources are known without being told: this checkout, and any corpus mirror.
        src.setdefault("archagent", ROOT)
        for m in sorted(Path.home().glob(".cache/archagent/corpus/*.git")):
            src.setdefault(m.stem, m)
        out = Path(a.out).expanduser() if a.out else Path(f"/tmp/archagent-review-{date.today()}")
        do_kit(Path(a.worksheet), out, src)
    else:
        do_report()

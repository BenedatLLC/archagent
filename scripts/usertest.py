#!/usr/bin/env python3
"""Assemble an end-to-end user-test kit — and deliberately withhold the answers.

Every other harness in this project hands the reviewer a finished artifact and asks whether it is any
good. This one asks a different question: **can someone install the tool and get a result at all?** So the
kit ships a repository with no `archagent.toml`, no `architecture/`, and no pre-run output. The tester
reads the published documentation and works it out, and where they get stuck *is* the measurement.

That inverts the usual clobbering risk. `spotcheck.py kit` once rebuilt over a completed review and
destroyed it; the same guard is here, because a returned worksheet is irreplaceable — it records one
person's first contact with the tool, and that can never be re-run on the same person.

Target: httpx. Chosen because it is untouched by every tuning and held-out set (see
`tests/corpus_manifest.toml` and `tests/heldout_manifest.toml` — litellm, django, opencode, OpenHands and
datasette are all disqualified by prior contact), small enough to finish in an evening, and laid out with
its package at the repository root, which is the shape that produced three silent-failure bugs in
calibration round 5.
"""

from __future__ import annotations

import argparse
import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))

#: The pinned target. `rev` is fixed so two testers see the same repository and their scores mean the
#: same thing; bumping it starts a new round rather than continuing this one.
TARGET = {
    "name": "httpx",
    "url": "https://github.com/encode/httpx.git",
    "rev": "b5addb6",
    "why": "no prior contact with archagent; package at the repository root; ~23 source files",
}

def _declared_version() -> str:
    """The version in `pyproject.toml`, read rather than restated.

    Round 1 shipped documentation describing behaviour the published wheel did not have, because PyPI
    held 0.3.0 while the repo had moved on. Keeping a second copy of the version here would reintroduce
    the same class of skew one level down: the kit would tell a tester to install one version and hand
    them another version's documentation, and nothing would say so.
    """
    text = (HERE.parent / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("no version in pyproject.toml — the kit cannot say what it is testing")
    return m.group(1)


#: The archagent release under test. The docs the tester reads must be the tag that matches this wheel —
#: a mismatch measures skew rather than the tool.
VERSION = _declared_version()
TAG = f"v{VERSION}"

RUBRIC_VERSION = "usertest-v1"

#: The documentation bundled into the kit, taken from `TAG` rather than the working tree so it matches
#: the wheel under test. The whole set ships, not a selection: choosing three pages a tester "needs"
#: would replace the question *which page do I need?* — a real part of onboarding — with a curated
#: answer. Round 1 depended on fetching a URL, the fetch failed, and the tester reverse-engineered the
#: tool from `--help` with no documentation at all.
BUNDLE = ("README.md", "docs")

#: Scaffolding that must not ship: its presence would answer the question being asked.
WITHHOLD = ("archagent.toml", "architecture", ".archagent",
            ".claude/skills", ".cursor/skills", ".openhands", ".agents/skills")


def _run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _is_filled_in(p: Path) -> bool:
    """Has someone written answers into this worksheet?

    The same guard `spotcheck.py` grew after `kit` rebuilt over a completed review. A worksheet is filled
    in when any score blank holds something other than the placeholder.
    """
    if not p.is_file():
        return False
    text = p.read_text()
    for line in text.splitlines():
        if line.startswith("- score:") or line.startswith("- answer:"):
            value = line.split(":", 1)[1].strip()
            if value and value not in {"_", "__", "___", "?"}:
                return True
    return False


def do_kit(out: Path, force: bool = False) -> None:
    done = [p for p in out.glob("*.md") if _is_filled_in(p)] if out.is_dir() else []
    if done and not force:
        raise SystemExit(
            f"{out} already holds a filled-in worksheet ({', '.join(p.name for p in done)}).\n"
            f"Move it somewhere safe first — rebuilding would destroy it, and unlike a findings\n"
            f"capture it cannot be regenerated.")

    out.mkdir(parents=True, exist_ok=True)
    repo = out / "repo"
    if repo.exists():
        shutil.rmtree(repo)

    print(f"cloning {TARGET['name']} at {TARGET['rev']} ...")
    _run("git", "clone", "--quiet", TARGET["url"], str(repo))
    _run("git", "checkout", "--quiet", TARGET["rev"], cwd=repo)
    rev_full = _run("git", "rev-parse", "HEAD", cwd=repo)
    subject = _run("git", "log", "-1", "--format=%s", cwd=repo)

    # The tester must reach a clean repository. A stray archagent.toml from a local experiment would hand
    # them the configuration step, which is the step most likely to fail.
    leaked = [w for w in WITHHOLD if (repo / w).exists()]
    if leaked:
        raise SystemExit(f"refusing to ship: the clone already contains {leaked}")

    docs = out / f"docs-{VERSION}"
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir(parents=True)
    _bundle_docs(docs)

    (out / "README.md").write_text(_instructions(rev_full, subject))
    sheet = out / f"worksheet-{TARGET['name']}-{TARGET['rev']}.md"
    sheet.write_text(_worksheet(rev_full))

    n_docs = sum(1 for _ in docs.rglob("*.md"))
    print(f"\nkit ready: {out}")
    print(f"  repo/                       {TARGET['name']} @ {rev_full[:9]} — no archagent scaffolding")
    print(f"  docs-{VERSION}/          {n_docs} markdown files at {TAG} — no network needed")
    print(f"  README.md                   instructions")
    print(f"  {sheet.name}   the worksheet to fill in and return")
    print(f"\nUnder test: archagent {VERSION} (tag {TAG}).")


def _bundle_docs(dest: Path) -> None:
    """Copy the documentation set at `TAG` into the kit, structure preserved.

    `git archive` rather than a working-tree copy: the tester must read the docs that shipped with the
    wheel, and the working tree moves on. Structure is preserved because the README's relative links
    (`docs/CONFIGURATION.md`, `docs/architecture/README.md`) then resolve on disk — a flattened copy
    would give the tester a README full of dead links, which is worse than no README.
    """
    repo = HERE.parent
    try:
        _run("git", "-C", str(repo), "rev-parse", TAG)
    except subprocess.CalledProcessError:
        raise SystemExit(f"tag {TAG} not found in {repo} — the kit must ship the docs that match the "
                         f"wheel under test, so a missing tag is fatal rather than a warning.")
    tar = subprocess.run(["git", "-C", str(repo), "archive", TAG, *BUNDLE],
                         check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)

    # Catch links broken *by the bundling*, not links that were already illustrative. The README's
    # invariants table cites `decisions/0007-hexagonal.md` as an example of what a *user's* ADR link
    # looks like; it resolves nowhere in this repo either, and warning about it would train the reader
    # to ignore the warning. So the test is differential: a link that resolves in the source tree and
    # not in the bundle is a bundling bug, and nothing else is.
    import re
    repo_root = repo
    broken = []
    for md in dest.rglob("*.md"):
        rel = md.relative_to(dest)
        src = repo_root / rel
        if not src.is_file():
            continue
        for link in re.findall(r"\]\((?!http|mailto)([^)#\s]+\.md)", md.read_text()):
            in_bundle = (md.parent / link).resolve().is_file()
            in_repo = (src.parent / link).resolve().is_file()
            if in_repo and not in_bundle:
                broken.append(f"{rel}: {link}")
    if broken:
        raise SystemExit(
            f"refusing to ship: bundling broke {len(broken)} link(s) that resolve in the repo:\n  "
            + "\n  ".join(broken[:8])
            + "\nA README full of dead links is worse than no README — the tester follows one, gets "
              "nothing, and concludes the docs are broken rather than the kit.")


def _instructions(rev: str, subject: str) -> str:
    return f"""# archagent end-to-end user test

Thank you for doing this. It should take **60–90 minutes**.

You are testing whether someone can install this tool and get a useful result from the documentation
alone. **I have deliberately not told you how to run it.** Working that out is the thing being measured,
so please resist asking me — and when you get stuck, write down where, because that is the most valuable
thing you can give me. Getting stuck is a successful outcome for this test, not a failed one.

## What you have

- `repo/` — a clone of [httpx]({TARGET['url']}) pinned at `{rev[:9]}` (*{subject}*).
  A real repository with real history, and **no archagent set up in it**.
- `docs-{VERSION}/` — the project's complete documentation at the version under test. Start at its
  `README.md`. No network needed.
- `{'worksheet-' + TARGET['name'] + '-' + TARGET['rev'] + '.md'}` — fill this in as you go, not at the end.

## What to do

1. **Start the clock** and note the time in the worksheet.
2. Open **`docs-{VERSION}/README.md`** and follow the documentation to install archagent **{VERSION}**
   and set it up inside `repo/`.
   - **Everything you need is in this directory — you should not need the network except to install the
     package.** That folder is the project's complete documentation set at the version under test, and
     its internal links work on disk. Round 1 of this test told the tester to fetch a GitHub URL, the
     fetch failed, and they had no documentation at all; hence the change.
   - The same pages are online at <https://github.com/BenedatLLC/archagent/tree/{TAG}> if you would
     rather read them rendered. Say which you used in the worksheet — it changes what the round measures.
   - Install from PyPI: the version you want is `{VERSION}`. It is a pre-release, which some installers
     skip unless you name the version exactly.
3. Run it through whatever the documentation presents as the normal workflow, end to end.
   - Parts of it are driven by a coding agent (Claude Code or similar) via installed skills. If you do
     not have one, get as far as you can with the command-line tools alone and say so in the worksheet —
     that is a useful result by itself.
4. Fill in the worksheet and send it back.

## Two things worth knowing

**You are judging the tool, not httpx.** Nobody involved wrote httpx, and there is no expected answer.
If the tool's output is wrong, that is the finding.

**Do not trust the output because it is confident.** For the correctness and completeness questions,
spot-check a few claims against the code rather than rating your impression of how authoritative it
sounds. If you only have time to verify two or three, verify two or three and say that in the worksheet —
a rating you actually checked is worth far more to me than one you did not, and knowing which is which
matters more than the number.

## If it goes badly wrong

Record it and stop. A kit that cannot be completed is a result, and a detailed account of where it broke
is more useful than a completed worksheet with low scores.
"""


def _worksheet(rev: str) -> str:
    return f"""# archagent end-to-end user test — worksheet

- rubric: `{RUBRIC_VERSION}`
- archagent under test: `{VERSION}` (tag `{TAG}`)
- target: `{TARGET['name']}` @ `{rev[:9]}`
- your name:
- date:

Leave a score as `_` if you could not get far enough to judge it. **A blank is data**; a guess is not.

---

## Part 1 — the log (fill in as you go)

The most valuable section. Rough notes are fine; verbatim error messages are better than paraphrase.

**Time started:**
**Time you first had the tool installed:**
**Time you first had output you could read:**
**Time finished (or gave up):**

**Every point where you were stuck, unsure, or had to guess.** What you were trying to do, what you
tried, what happened, how you got out of it.

```
```

**Anything you expected a command to do that it did not.**

```
```

**Which documentation did you actually read?** Tick one — this decides what the round measures, so it
is not a formality. (Round 1's tester could not reach the docs at all and reverse-engineered the tool
from `--help`; that round cannot be compared with one where the docs were read.)

- [ ] `bundled` — the `docs-{VERSION}/` folder in this kit
- [ ] `published` — the GitHub pages at `{TAG}`, rendered in a browser
- [ ] `mixed` — some of each
- [ ] `fallback` — I could not reach either, and worked from `--help` / the installed skill files

**Did you have to look at anything outside the documentation** — the source, the issue tracker, me?

```
```

---

## Part 2 — the four ratings

All 1–5. Write one or two sentences of *why* under each; the sentence is worth more than the number.

### Ease of use
Is the tool easy to use, the documentation clear, and the output easy to understand?

`1` could not get it working from the docs · `3` worked it out with friction · `5` obvious throughout

- score: _
- why:

### Correctness
Are the results accurate? Base this on claims you actually checked against the code.

`1` mostly wrong · `3` broadly right with real errors · `5` everything I checked held up

- score: _
- how many claims did you actually verify?
- which ones were wrong?
- why:

### Completeness
Do the results cover the repository — or are there significant parts it missed or said nothing about?

`1` large parts absent · `3` main structure covered, gaps at the edges · `5` nothing significant missing

- score: _
- what was missing?
- why:

### Impact
Are the results meaningful? Did they tell you anything about httpx you would not have got from
skimming the source yourself?

`1` nothing I could not see myself · `3` a few real observations · `5` genuinely new insight

- score: _
- the single most useful thing it told you:
- the most useless thing it told you:
- why:

---

## Part 3 — specific questions

These target places I already suspect are weak. Short answers are fine.

**a. Setup.** `archagent init` prints the settings it chose and flags ones that look wrong. Did it flag
anything? Did you understand what to do about it? Did you change anything it did not flag?

- answer: _

**b. The silent-failure check.** A misconfigured source path makes archagent examine *nothing* and report
that everything is fine. Did you at any point see a coverage or file count that looked implausibly low
(0%, or far fewer files than httpx has)? If so, did the tool tell you, or did you notice yourself?

- answer: _

**c. Findings you dismissed.** Roughly what fraction of the reported findings did you think were not
worth acting on? Rough is fine.

- answer: _

**d. Trust.** Was there a moment you stopped trusting the output? What caused it?

- answer: _

**e. Would you use it?** On a repository you actually work on — yes, no, or under what condition?

- answer: _

---

## Part 4 — anything else

Including things this worksheet failed to ask about.

```
```
"""


# --- ingest -------------------------------------------------------------------------------

def _score_after(text: str, heading: str) -> str:
    """The `- score:` line belonging to one `### heading` section, or "" for a blank.

    Anchored to the section rather than found by order, so reordering the worksheet cannot silently
    reassign a rating to the wrong dimension — a transcription error that would be invisible in the CSV
    and permanent, because the worksheet is not re-runnable.
    """
    i = text.find(f"### {heading}")
    if i < 0:
        return ""
    section = text[i:]
    nxt = section.find("\n### ", 1)
    if nxt > 0:
        section = section[:nxt]
    for line in section.splitlines():
        if line.strip().startswith("- score:"):
            v = line.split(":", 1)[1].strip()
            return "" if v in {"_", "__", "___", "?", ""} else v
    return ""


def _field_after(text: str, marker: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith(marker):
            return line.split(marker, 1)[1].strip()
    return ""


def _answer_to(text: str, question_marker: str) -> str:
    """The `- answer:` belonging to one Part 3 question, anchored to the question rather than to order.

    Same reason `_score_after` is anchored: a mis-assigned answer is invisible once it reaches the CSV,
    and the worksheet cannot be re-run to catch it.
    """
    i = text.find(question_marker)
    if i < 0:
        return ""
    block = text[i:]
    nxt = block.find("\n**", 1)
    if nxt > 0:
        block = block[:nxt]
    out = []
    for line in block.splitlines():
        if line.strip().startswith("- answer:"):
            out.append(line.split(":", 1)[1].strip())
        elif out and line.startswith("  ") and line.strip():
            out.append(line.strip())          # continuation of a wrapped answer
    v = " ".join(out).strip()
    return "" if v in {"_", "__", "?"} else v


def _count_blockers(text: str) -> int:
    """Distinct stuck points in the Part 1 log, counted from its bullet markers."""
    i = text.find("**Every point where you were stuck")
    if i < 0:
        return 0
    block = text[i:]
    end = block.find("**Anything you expected")
    block = block[:end] if end > 0 else block
    # Bullets *or* timestamped entries. Round 2's log was written as "18:00 — ..." paragraphs and
    # counted zero blockers, which read as a frictionless run in the ledger while the prose described
    # several distinct problems. A count that silently reports zero is worse than no count.
    import re
    n = sum(1 for line in block.splitlines() if line.strip().startswith(("* ", "- ")))
    if n:
        return n
    return len(re.findall(r"^\s*\d{1,2}:\d{2}\s*[—-]", block, re.M))


def _ticked_docs_path(text: str) -> str:
    """The `docs_path` the tester ticked, or "" if they ticked none or more than one.

    Never overrides `--docs-path`: it is offered as a cross-check, because the answer that matters most
    for comparability is the one a busy tester is likeliest to skip.
    """
    import re
    hits = [m for m in re.findall(r"- \[[xX]\]\s*`(\w+)`", text)]
    return hits[0] if len(hits) == 1 else ""


def do_ingest(sheet: Path, out: Path, *, docs_path: str, archagent_commit: str,
              tester: str = "", prior: str = "", agent: str = "", dry_run: bool = False) -> None:
    """Parse a returned worksheet into the user-test ledger.

    `docs_path` is not inferred. Whether the tester actually read the published documentation decides
    what the round measured, and guessing it from prose is exactly the kind of quiet inference this
    project keeps finding in its own code.
    """
    from usertest_ledger import UserTestRow, append, scores

    text = sheet.read_text()
    row = UserTestRow(
        # The version and docs path are part of the identity: two rounds on the same day against
        # different releases are different experiments, and a colliding run_id silently makes them look
        # like one row overwritten.
        run_id=f"{datetime.date.today()}-{TARGET['name']}-{VERSION}-{docs_path}",
        date=_field_after(text, "- date:") or str(datetime.date.today()),
        archagent_version=VERSION,
        archagent_commit=archagent_commit,
        target_url=TARGET["url"],
        target_commit=TARGET["rev"],
        rubric_version=RUBRIC_VERSION,
        docs_path=docs_path,
        tester=tester or _field_after(text, "- your name:"),
        prior_exposure=prior,
        had_coding_agent=agent,
        ease_of_use=_score_after(text, "Ease of use"),
        correctness=_score_after(text, "Correctness"),
        completeness=_score_after(text, "Completeness"),
        impact=_score_after(text, "Impact"),
        claims_verified=_field_after(text, "- how many claims did you actually verify?").split("(")[0].strip(),
        minutes_to_installed=_field_after(text, "**Time you first had the tool installed:**"),
        minutes_to_first_output=_field_after(text, "**Time you first had output you could read:**"),
        minutes_total=_field_after(text, "**Time finished (or gave up):**"),
        blockers=str(_count_blockers(text)),
        dismissal_rate=_answer_to(text, "**c. Findings you dismissed.**"),
    )
    ticked = _ticked_docs_path(text)
    if ticked and ticked != docs_path:
        print(f"  !! the worksheet ticks docs_path={ticked!r} but you passed {docs_path!r}.")
        print(f"     Resolve this before recording: it decides what the round measured.")
    print(f"run_id:        {row.run_id}")
    _NOTE = {
        "fallback": "   <- the docs were NOT read; this measures a harder question than the kit asks",
        "mixed": "   <- partly read; weaker than a clean bundled or published round",
        "bundled": "   <- read from the kit, not rendered on GitHub; not comparable with `published`",
    }
    print(f"docs_path:     {row.docs_path}{_NOTE.get(row.docs_path, '')}")
    print(f"blockers:      {row.blockers}")
    print(f"claims verified: {row.claims_verified or '(not stated)'}")
    print("scores (never averaged):")
    for k, v in scores(row).items():
        print(f"    {k:14} {v if v is not None else '- (could not judge)'}")
    if dry_run:
        print("\n(dry run — nothing written)")
        return
    append(out, row)
    print(f"\nappended to {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kit", help="assemble the kit")
    k.add_argument("--out", type=Path,
                   default=Path(f"/tmp/archagent-usertest-{datetime.date.today()}"))
    k.add_argument("--force", action="store_true",
                   help="rebuild even over a filled-in worksheet (destroys it)")

    g = sub.add_parser("ingest", help="parse a returned worksheet into the user-test ledger")
    g.add_argument("sheet", type=Path)
    g.add_argument("--out", type=Path, required=True, help="path to usertest.csv")
    # Derived, not restated. A hardcoded copy went stale the moment `bundled` was added: the ledger
    # accepted it, the worksheet offered it, and `ingest` refused it — which is the scattered-source-of-
    # truth shape this tool's own group F looks for, in its own harness.
    from usertest_ledger import DOCS_PATHS
    g.add_argument("--docs-path", required=True, choices=list(DOCS_PATHS),
                   help="how the tester actually got instructions — decides what the round measured")
    g.add_argument("--archagent-commit", required=True)
    g.add_argument("--tester", default="")
    g.add_argument("--prior", default="", help="prior exposure to archagent")
    g.add_argument("--agent", default="", help="had a coding agent: yes / no / partial")
    g.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    if args.cmd == "kit":
        do_kit(args.out, force=args.force)
    elif args.cmd == "ingest":
        do_ingest(args.sheet, args.out, docs_path=args.docs_path,
                  archagent_commit=args.archagent_commit, tester=args.tester,
                  prior=args.prior, agent=args.agent, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

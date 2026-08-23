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

#: The archagent release under test. The docs the tester reads must be the tag that matches this wheel —
#: a mismatch measures skew rather than the tool.
VERSION = "1.0.0rc1"
TAG = "v1.0.0rc1"

RUBRIC_VERSION = "usertest-v1"

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

    (out / "README.md").write_text(_instructions(rev_full, subject))
    sheet = out / f"worksheet-{TARGET['name']}-{TARGET['rev']}.md"
    sheet.write_text(_worksheet(rev_full))

    print(f"\nkit ready: {out}")
    print(f"  repo/                       {TARGET['name']} @ {rev_full[:9]} — no archagent scaffolding")
    print(f"  README.md                   instructions")
    print(f"  {sheet.name}   the worksheet to fill in and return")
    print(f"\nUnder test: archagent {VERSION} (tag {TAG}).")


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
- `{'worksheet-' + TARGET['name'] + '-' + TARGET['rev'] + '.md'}` — fill this in as you go, not at the end.

## What to do

1. **Start the clock** and note the time in the worksheet.
2. Go to <https://github.com/BenedatLLC/archagent/tree/{TAG}> and follow the documentation to install
   archagent **{VERSION}** and set it up inside `repo/`.
   - That link is pinned to the version under test. The docs on the default branch may have moved on.
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kit", help="assemble the kit")
    k.add_argument("--out", type=Path,
                   default=Path(f"/tmp/archagent-usertest-{datetime.date.today()}"))
    k.add_argument("--force", action="store_true",
                   help="rebuild even over a filled-in worksheet (destroys it)")
    args = ap.parse_args()
    if args.cmd == "kit":
        do_kit(args.out, force=args.force)


if __name__ == "__main__":
    main()

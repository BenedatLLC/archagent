#!/usr/bin/env python3
"""The fresh-target defect ledger — generated from the issue tracker, never typed.

One row per **encounter with a repository archagent had not seen before**, counting the defects that
encounter found. The unit is deliberately not the one either other ledger uses: `ledger.csv` records a
scored artifact or findings run, `usertest.csv` records one person's first contact, and a defect count is
a property of the encounter itself — which is why it aggregates across both kinds. Calibration round 5
contributes a row and so do both user tests.

**Derived, because the alternative already failed.** Of the twelve defects found across the first three
encounters, nine were filed as issues and three existed only as commit prose — and those three were the
ones found by the author during generation, which is the category most at risk of going unrecorded. They
are now filed retroactively (#42-#44). A hand-maintained count would drift in exactly that direction
again.

**The count is never a rate.** `workflow_reached` is ordinal at best, so dividing by it would invent a
denominator. Round 1 found 3 defects and round 2 found 6 on the *same repository*: that is not a
regression, it is a tester who got further. The keys below are what make the numbers readable; without
them "3, 3, 6" reads as a trend.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

LABEL_PREFIX = "found-by:"

#: What must match for two encounters to be read against each other. None of these live in `ledger.csv`
#: or `usertest.csv`, which is the mechanical reason this is a third table rather than a column.
COMPARABILITY_KEYS = ("observer", "workflow_reached", "defect_bar")

#: How far through the workflow the encounter actually got, in order. A defect count means nothing
#: without it: an encounter that stopped at `init` had no chance to find a `drift` defect.
WORKFLOW_STAGES = ("init", "describe", "check", "evaluate", "full")

#: Who was looking. An author finds different defects than a stranger — the three dspy defects were all
#: self-found while generating an artifact, before any reviewer saw anything.
OBSERVERS = ("author", "independent", "agent")

#: What counted as a defect. Kept explicit so a later round cannot quietly lower the bar and report an
#: improvement.
DEFECT_BARS = ("verified-and-filed", "reported-unverified")


@dataclass
class Encounter:
    encounter_id: str          # matches the `found-by:` label suffix
    date: str
    target: str
    target_fresh: str          # "yes" | "no" — a repeat encounter is not a fresh-target observation
    archagent_version: str
    observer: str
    workflow_reached: str
    defect_bar: str
    run_id: str = ""           # the row in ledger.csv or usertest.csv this encounter also produced
    provenance: str = "issues"  # "issues" | "reconstructed-from-commits"
    defects: int = 0
    issues: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        for field_name, allowed in (("workflow_reached", WORKFLOW_STAGES),
                                    ("observer", OBSERVERS),
                                    ("defect_bar", DEFECT_BARS)):
            v = getattr(self, field_name)
            if v not in allowed:
                raise ValueError(f"{field_name} must be one of {allowed}, got {v!r}")


#: The encounters. Everything except `defects` and `issues` is context a label cannot carry; those two
#: are filled from the tracker so the count and the evidence cannot disagree.
ENCOUNTERS = [
    Encounter(
        encounter_id="calibration-5", date="2026-08-23", target="dspy", target_fresh="yes",
        archagent_version="0.3.0+dev", observer="author", workflow_reached="full",
        defect_bar="verified-and-filed", run_id="2026-08-23-dspy-calibration-round5",
        provenance="reconstructed-from-commits",
        notes="All three found by the author while generating the artifact, before any reviewer read "
              "anything. Filed retroactively on 2026-08-29 (#42-#44); the weaker provenance is recorded "
              "rather than smoothed over."),
    Encounter(
        encounter_id="usertest-1", date="2026-08-23", target="httpx", target_fresh="yes",
        archagent_version="1.0.0rc1", observer="author", workflow_reached="evaluate",
        defect_bar="verified-and-filed", run_id="2026-08-23-httpx-usertest",
        notes="docs_path=fallback — the tester could not reach the documentation and worked from --help, "
              "so the encounter exercised less surface than it appears to."),
    Encounter(
        encounter_id="usertest-2", date="2026-08-23", target="httpx", target_fresh="no",
        archagent_version="1.0.0rc2", observer="agent", workflow_reached="full",
        defect_bar="verified-and-filed", run_id="2026-08-23-httpx-1.0.0rc2-bundled",
        notes="Same repository as usertest-1, so target_fresh=no: the higher count reflects a tester who "
              "completed the workflow, not a regression. Every claim reproduced before recording; one "
              "tester claim was checked and found wrong."),
]


def _issues_for(encounter_id: str, repo: str) -> list[int]:
    out = subprocess.run(
        ["gh", "issue", "list", "--repo", repo, "--state", "all",
         "--label", f"{LABEL_PREFIX}{encounter_id}", "--limit", "200", "--json", "number"],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"gh failed for {encounter_id}: {out.stderr.strip()}")
    return sorted(i["number"] for i in json.loads(out.stdout or "[]"))


def build(repo: str) -> list[Encounter]:
    rows = []
    for e in ENCOUNTERS:
        nums = _issues_for(e.encounter_id, repo)
        e.defects = len(nums)
        e.issues = " ".join(f"#{n}" for n in nums)
        rows.append(e)
    return rows


def write(rows: list[Encounter], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def report(rows: list[Encounter]) -> None:
    print(f"{'encounter':16} {'target':8} {'fresh':6} {'observer':12} {'reached':9} {'defects':>7}  issues")
    for r in rows:
        print(f"{r.encounter_id:16} {r.target:8} {r.target_fresh:6} {r.observer:12} "
              f"{r.workflow_reached:9} {r.defects:7}  {r.issues}")
    fresh = [r for r in rows if r.target_fresh == "yes"]
    print(f"\n{len(fresh)} fresh-target encounter(s), {sum(r.defects for r in fresh)} defect(s).")
    print("Not a rate and not yet a trend: n is too small, and the keys "
          f"{COMPARABILITY_KEYS} differ across these rows. See the module docstring.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="BenedatLLC/archagent")
    ap.add_argument("--out", type=Path, help="write the CSV here (default: report only)")
    args = ap.parse_args()
    rows = build(args.repo)
    report(rows)
    if args.out:
        write(rows, args.out)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

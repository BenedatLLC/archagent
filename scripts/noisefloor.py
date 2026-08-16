#!/usr/bin/env python
"""How much a judged score moves when nothing about the artifact changed.

    python scripts/noisefloor.py <checkout> --reviews <dir> [--baseline <judged.json>]

Design §15 makes three acceptance rules turn on the word "significant", and none of them can be evaluated
without this number. It is also what decides how to read the calibration rounds already collected: a
human-judge gap of −1.00 means one thing if replicate judgings of the *same* artifact vary by ±0.1 and
something else entirely if they vary by ±0.5.

**What is held constant.** The artifact, the code, the brief, the prompt — byte-identical across runs.
Only the model varies, and only between the two groups. So the spread within a group is the floor: the
part of a score that is not about the artifact at all.

**What this does not measure.** Generation variance — whether describing the same repository twice
produces artifacts of different quality — is the other half and costs a describe pass per replicate. This
is the cheap half, and the cheap half is enough to say whether a one-point gap is signal.
"""
import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from rubric_judged import CRITERIA, parse_brief   # noqa: E402


def _group(name: str) -> str:
    """Model family from a run key like `opus-r2`. Keys arrive with the `review-` prefix already
    stripped, and matching for it put every run in one bucket — which silently merged the within-model
    and between-model variances this exists to separate."""
    m = re.match(r"([a-z]+)-r\d+$", name)
    return m.group(1) if m else "other"


def _spread(values: list[float]) -> str:
    if len(values) < 2:
        return "n<2"
    return f"sd {st.stdev(values):.2f}  range {min(values):.0f}-{max(values):.0f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("--reviews", required=True)
    ap.add_argument("--baseline", help="an earlier judged-*.json to include in its group")
    ap.add_argument("--human", help="the human judged-*.json, for comparison against the floor")
    args = ap.parse_args()

    root = Path(args.checkout).resolve()
    runs: dict[str, dict[str, dict]] = {}
    for f in sorted(Path(args.reviews).glob("review-*.md")):
        runs[f.stem.replace("review-", "")] = parse_brief(f.read_text(), root)
    if args.baseline:
        d = json.load(open(args.baseline))
        runs["opus-r0"] = {k: v for k, v in d["scores"].items()}

    crit = [c.id for c in CRITERIA if not c.second_run_only]
    groups: dict[str, list[str]] = {}
    for name in runs:
        groups.setdefault(_group(name), []).append(name)

    print(f"\n{len(runs)} run(s) over the same artifact: "
          + ", ".join(f"{g} x{len(v)}" for g, v in sorted(groups.items())) + "\n")

    hdr = f"{'criterion':24}" + "".join(f"{n:>12}" for n in sorted(runs))
    print(hdr)
    for c in crit:
        row = f"{c:24}"
        for n in sorted(runs):
            s = runs[n].get(c, {}).get("score")
            row += f"{('-' if s is None else s):>12}"
        print(row)

    print(f"\n{'':24}" + "".join(f"{n:>12}" for n in sorted(runs)))
    means = {}
    for n in sorted(runs):
        vals = [runs[n][c]["score"] for c in crit
                if runs[n].get(c, {}).get("score") is not None]
        means[n] = sum(vals) / len(vals) if vals else float("nan")
    print(f"{'mean':24}" + "".join(f"{means[n]:>12.2f}" for n in sorted(runs)))

    print("\n--- the floor, within each model group ---")
    for g, names in sorted(groups.items()):
        gm = [means[n] for n in names]
        print(f"  {g:8} mean-of-means {sum(gm)/len(gm):.2f}   {_spread(gm)}")
        for c in crit:
            vals = [runs[n][c]["score"] for n in names if runs[n].get(c, {}).get("score") is not None]
            if len(vals) >= 2:
                print(f"    {c:24} {_spread(vals)}")

    if len(groups) >= 2:
        print("\n--- between models ---")
        for g, names in sorted(groups.items()):
            print(f"  {g:8} {sum(means[n] for n in names)/len(names):.2f}")

    if args.human:
        h = json.load(open(args.human))
        hv = [v["score"] for v in h["scores"].values() if v.get("score") is not None]
        hm = sum(hv) / len(hv)
        allm = list(means.values())
        gap = hm - sum(allm) / len(allm)
        floor = max((st.stdev([means[n] for n in v]) for v in groups.values() if len(v) >= 2), default=0)
        print(f"\n--- reading the calibration gap ---")
        print(f"  human {hm:.2f}   judges {sum(allm)/len(allm):.2f}   gap {gap:+.2f}")
        print(f"  largest within-model sd of the mean: {floor:.2f}")
        if floor:
            print(f"  gap is {abs(gap)/floor:.1f}x the floor"
                  + ("  — larger than the noise" if abs(gap) > 2 * floor
                     else "  — NOT clearly larger than the noise"))


if __name__ == "__main__":
    main()

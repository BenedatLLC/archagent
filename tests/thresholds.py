"""Leave-one-out sensitivity for numeric thresholds (`docs/designs/evaluating-archagent.md` §18).

Thresholds are where overfitting bites hardest. `PCTILE_BAR = 0.75`, `COHESION = 0.6`,
`MIN_FILES_PER_VALUE = 3` — each was chosen by looking at output on a handful of repositories, and nothing
records whether a value is justified by all of them or by one of them.

**The question this answers.** Not "is 0.6 the optimal value" — there is no fitting objective, and
inventing one would be worse than the judgement it replaced. The question is narrower and answerable:
*would we have picked this value if one repository had not been in the room?*

**How.** A filter threshold produces a step function: as it rises, findings drop away. Between steps the
output is unchanged, so any value inside a step is equivalent — a **plateau**. A value is well-supported
when it sits comfortably inside every repository's plateau. It is fitted to one repository when dropping
that repository would have let you choose very differently, which is exactly the leave-one-out question.

Two failure signatures, both reported:

- **Pinned by one repository.** Removing repo R widens the agreed plateau a lot. R is the only thing
  holding the value where it is.
- **On a cliff for one repository.** At the chosen value, R's finding count changes sharply under a small
  perturbation while everyone else's is flat. The value is doing delicate work for R and no work for the
  others — the shape of a number tuned until one repository looked right.

Neither is automatically a defect. A threshold *should* be pinned by the repository that exercises it
hardest if the others do not exercise it at all — which is why the report includes each repository's
**opportunity**, the count at the loosest value. A repository that produces nothing anywhere cannot support
or refute anything, and its silence must not read as agreement (§18).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence


@dataclass(frozen=True)
class Sweep:
    """Finding counts for one threshold, across a value range, per repository."""
    name: str                              # the constant, e.g. "COHESION"
    chosen: float                          # its value in the shipped code
    values: tuple[float, ...]              # swept, ascending
    counts: dict[str, tuple[int, ...]]     # repo -> count at each value

    def at(self, repo: str, value: float) -> int:
        return self.counts[repo][self.values.index(value)]

    @property
    def repos(self) -> list[str]:
        return sorted(self.counts)


def measure(name: str, chosen: float, values: Sequence[float],
            count: Callable[[str, float], int], repos: Sequence[str]) -> Sweep:
    """Build a Sweep by calling `count(repo, value)` over the grid."""
    vals = tuple(sorted(values))
    return Sweep(name=name, chosen=chosen, values=vals,
                 counts={r: tuple(count(r, v) for v in vals) for r in repos})


def plateau(sweep: Sweep, repos: Sequence[str], value: float) -> tuple[float, float]:
    """The widest contiguous value range containing `value` over which **every** named repo's count is
    unchanged. This is the set of values that are, on this evidence, indistinguishable from the one chosen.
    """
    if not repos:
        return (sweep.values[0], sweep.values[-1])
    i = sweep.values.index(value)
    same = lambda j: all(sweep.counts[r][j] == sweep.counts[r][i] for r in repos)
    lo = i
    while lo - 1 >= 0 and same(lo - 1):
        lo -= 1
    hi = i
    while hi + 1 < len(sweep.values) and same(hi + 1):
        hi += 1
    return (sweep.values[lo], sweep.values[hi])


def _width(span: tuple[float, float]) -> float:
    return span[1] - span[0]


@dataclass
class Verdict:
    threshold: str
    chosen: float
    agreed: tuple[float, float]                 # plateau with every repo included
    without: dict[str, tuple[float, float]]     # repo left out -> plateau without it
    opportunity: dict[str, int]                 # repo -> count at the loosest value
    cliff: dict[str, int]                       # repo -> |count change| across one step at `chosen`
    pinned_by: list[str] = field(default_factory=list)
    on_a_cliff_for: list[str] = field(default_factory=list)
    silent: list[str] = field(default_factory=list)
    thin: list[str] = field(default_factory=list)      # too few findings to support any verdict
    unconstrained: bool = False                        # nothing in the corpus responds to this threshold

    @property
    def ok(self) -> bool:
        return not self.pinned_by and not self.on_a_cliff_for

    def report(self) -> str:
        lines = [f"{self.threshold} = {self.chosen}",
                 f"  agreed plateau (all repos): {self.agreed[0]} .. {self.agreed[1]}"]
        if self.unconstrained:
            lines.append("  UNCONSTRAINED — no repository's output changes anywhere in the swept range, "
                         "so this evidence\n                  neither supports nor refutes the value. "
                         "That is not the same as agreement.")
        for repo in sorted(self.without):
            span = self.without[repo]
            tag = ""
            if repo in self.pinned_by:
                tag = "   <- PINNED BY THIS REPO"
            elif repo in self.silent:
                tag = "   (no findings at any value — supports nothing)"
            lines.append(f"  without {repo:14} {span[0]} .. {span[1]}"
                         f"   (opportunity {self.opportunity[repo]}){tag}")
        for repo in self.on_a_cliff_for:
            lines.append(f"  ON A CLIFF for {repo}: count moves by {self.cliff[repo]} across one step "
                         f"while the others are flat")
        if self.thin:
            lines.append(f"  THIN — {', '.join(self.thin)} produce too few findings for a verdict to "
                         f"mean much;\n         read every conclusion here as directional")
        if self.ok and not self.unconstrained:
            lines.append("  -> no repository is doing the work alone")
        return "\n".join(lines)


def leave_one_out(sweep: Sweep, widen_factor: float = 2.0, cliff_min: int = 2,
                  thin_below: int = 3) -> Verdict:
    """Which repositories, if any, are the reason the chosen value is where it is.

    `widen_factor` — dropping a repo counts as "pinned by" it when the agreed plateau grows by at least
    this multiple. A value everyone agrees on does not widen much when one voice leaves.

    `cliff_min` — a repo is "on a cliff" when its count moves by at least this many findings across one
    step at the chosen value while every other repo is flat there.

    `thin_below` — a repo producing fewer than this many findings at its most permissive setting cannot
    support a verdict about anything. Reported rather than excluded: "pinned by django" resting on two
    findings and resting on two hundred are different claims, and only the report can tell them apart.
    """
    repos = sweep.repos
    loosest = min(sweep.values)
    opportunity = {r: max(sweep.counts[r]) for r in repos}
    silent = [r for r in repos if opportunity[r] == 0]
    speaking = [r for r in repos if r not in silent]

    agreed = plateau(sweep, speaking, sweep.chosen)
    without = {r: plateau(sweep, [x for x in speaking if x != r], sweep.chosen) for r in speaking}
    for r in silent:
        without[r] = agreed          # dropping a silent repo changes nothing, by construction

    pinned = []
    base = _width(agreed)
    for r in speaking:
        w = _width(without[r])
        if w > 0 and (base == 0 or w >= base * widen_factor):
            pinned.append(r)

    i = sweep.values.index(sweep.chosen)
    j = min(i + 1, len(sweep.values) - 1)
    cliff = {r: abs(sweep.counts[r][j] - sweep.counts[r][i]) for r in repos}
    on_cliff = [r for r in speaking
                if cliff[r] >= cliff_min and all(cliff[o] == 0 for o in speaking if o != r)]

    thin = [r for r in speaking if opportunity[r] < thin_below]
    unconstrained = all(len(set(sweep.counts[r])) == 1 for r in speaking) if speaking else True

    return Verdict(threshold=sweep.name, chosen=sweep.chosen, agreed=agreed, without=without,
                   opportunity=opportunity, cliff=cliff,
                   pinned_by=pinned, on_a_cliff_for=on_cliff, silent=silent,
                   thin=thin, unconstrained=unconstrained)

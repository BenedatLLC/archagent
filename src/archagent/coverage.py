"""What an extractor could not see.

Issue #46, from `docs/designs/extraction-confidence.md`. The failure this exists to prevent recurred all
the way from 0.3.0 to 1.0.0: **a condition rendering as a plausible clean result.** A wrong source path
made every rule scope to nothing and `check` reported that all invariants held; a generated glob ast-grep
silently ignored made a rule match 0 of 154 sites and report PASS; a timed-out `git log` made every
history check go quiet. None produced an error. Each produced a *smaller true-looking answer*.

The counter-measure is to count twice — candidate sites **seen**, and sites **resolved** — and report the
gap. Seeing candidates is usually cheap (a node type, a regex); resolving them is the hard part; and the
difference is the extractor's blind spot, reportable *without knowing the right answer*.

**A `Coverage` cannot be quietly clean.** `seen == 0` is a distinct state from `seen > 0 and unresolved
== 0`, and `sound` is false for the first. That is not defensive style: the first prototype of the import
counter reported `0 of 0` over an empty file set on its first run — committing the exact error it was
written to detect — and a shared type is the only reason the next one will not.

A leaf module, like `tiers.py`: it imports nothing internal so any extractor can use it without closing a
cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: How many offending sites to carry as examples. Enough to start looking, few enough to print.
MAX_EXAMPLES = 5


@dataclass(frozen=True)
class Coverage:
    """One extractor's account of what it looked at and what it could resolve."""

    #: What was being extracted, phrased for a reader: "relative imports", "generated globs".
    what: str
    #: Candidate sites the extractor saw. Cheap to count and independent of whether resolution worked.
    seen: int
    #: Sites it turned into a fact.
    resolved: int
    #: A few unresolved sites, as `path:line` or whatever locates them.
    examples: tuple[str, ...] = ()
    #: What one site is, for rendering. "relative import", "glob", "environment read".
    unit: str = "site"
    #: Why `seen` could be zero legitimately, when it can. A repository with no relative imports is fine;
    #: a repository where the scanner could not run is not, and the two must not read alike.
    empty_is_normal: bool = False

    @property
    def unresolved(self) -> int:
        return max(0, self.seen - self.resolved)

    @property
    def examined_nothing(self) -> bool:
        """No candidate sites at all — the state that looks like success and is not evidence of it."""
        return self.seen == 0

    @property
    def sound(self) -> bool:
        """Every site the extractor saw became a fact.

        **False when nothing was seen**, unless the caller has said an empty repository is a legitimate
        answer for this extractor. "I resolved all zero of them" is the sentence this property exists to
        refuse.
        """
        if self.examined_nothing:
            return self.empty_is_normal
        return self.unresolved == 0

    @property
    def ratio(self) -> float:
        """Fraction resolved, or 0.0 when nothing was seen — never 1.0, which would read as perfect."""
        return (self.resolved / self.seen) if self.seen else 0.0

    def describe(self) -> str:
        """One line, and the three states must not be confusable.

        Callers render this differently — a colour, a prefix — but the words alone have to carry the
        difference, because a caveat that depends on colour loses to a coloured number.
        """
        if self.examined_nothing:
            if self.empty_is_normal:
                return f"no {self.what} in this repository"
            return (f"examined no {self.what} — nothing was checked, which is not the same as "
                    f"nothing being wrong")
        if self.unresolved == 0:
            return f"all {self.seen} {self.what} resolved"
        pct = round(100 * self.unresolved / self.seen)
        tail = f" (e.g. {', '.join(self.examples[:MAX_EXAMPLES])})" if self.examples else ""
        return f"{self.unresolved} of {self.seen} {self.what} resolved to nothing — {pct}%{tail}"


@dataclass
class Counter:
    """Accumulates a `Coverage` while an extractor runs.

    Separate from the frozen record so the extractor's loop stays readable and the result it hands out
    cannot be edited afterwards.
    """

    what: str
    unit: str = "site"
    empty_is_normal: bool = False
    seen: int = 0
    resolved: int = 0
    examples: list[str] = field(default_factory=list)

    def site(self, ok: bool, where: str = "") -> None:
        self.seen += 1
        if ok:
            self.resolved += 1
        elif where and len(self.examples) < MAX_EXAMPLES:
            self.examples.append(where)

    def finish(self) -> Coverage:
        return Coverage(what=self.what, seen=self.seen, resolved=self.resolved,
                        examples=tuple(self.examples), unit=self.unit,
                        empty_is_normal=self.empty_is_normal)

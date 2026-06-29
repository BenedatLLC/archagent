"""The compact rule DSL used in the ``Rule`` column of invariants.md.

v1 supports two forms, deliberately minimal:

  BOUNDARY  : ``forbid <source>[, <source>...] -> <target>[, <target>...]``
              "these modules must not import those modules" (Python: import-linter)

  STRUCTURAL: ``forbid-pattern <ast-grep pattern>``
              "this code shape must not appear" (any language: ast-grep)

Anything else is reported as unsupported by the generator rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass


class RuleError(ValueError):
    pass


@dataclass
class BoundaryRule:
    sources: list[str]
    targets: list[str]


@dataclass
class PatternRule:
    pattern: str


def parse_boundary(rule: str) -> BoundaryRule:
    if not rule.startswith("forbid "):
        raise RuleError(f"BOUNDARY rule must start with 'forbid ': {rule!r}")
    body = rule[len("forbid "):]
    if "->" not in body:
        raise RuleError(f"BOUNDARY rule needs '->': {rule!r}")
    left, _, right = body.partition("->")
    sources = [s.strip() for s in left.split(",") if s.strip()]
    targets = [t.strip() for t in right.split(",") if t.strip()]
    if not sources or not targets:
        raise RuleError(f"BOUNDARY rule needs sources and targets: {rule!r}")
    return BoundaryRule(sources=sources, targets=targets)


def parse_pattern(rule: str) -> PatternRule:
    prefix = "forbid-pattern "
    if not rule.startswith(prefix):
        raise RuleError(f"STRUCTURAL rule must start with 'forbid-pattern ': {rule!r}")
    pattern = rule[len(prefix):].strip()
    if not pattern:
        raise RuleError(f"STRUCTURAL rule has empty pattern: {rule!r}")
    return PatternRule(pattern=pattern)

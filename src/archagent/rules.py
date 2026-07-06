"""The compact rule DSL used in the ``Rule`` column of invariants.md.

v1 supports two forms, deliberately minimal:

  BOUNDARY  : ``forbid <source>[, <source>...] -> <target>[, <target>...]``
              "these modules must not import those modules" (Python: import-linter)

  STRUCTURAL: ``forbid-pattern <ast-grep pattern> [in|outside <scope>]``
              "this code shape must not appear" (any language: ast-grep)
              - ``in <scope>``      : only flag matches inside <scope>
              - ``outside <scope>`` : flag matches everywhere EXCEPT <scope>
                                      (the "only <scope> may do this" case)
              <scope> is a path/glob (``src/app/domain``) or a dotted module
              (``app.domain.workflow``); omit it to scan all sources.

Anything else is reported as unsupported by the generator rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCOPE_TOKEN = re.compile(r"[A-Za-z_][\w./*-]*")


class RuleError(ValueError):
    pass


@dataclass
class BoundaryRule:
    sources: list[str]
    targets: list[str]


@dataclass
class PatternRule:
    pattern: str
    scope_mode: str = "all"  # all | in | outside
    scope: str | None = None


@dataclass
class PropertyRule:
    target: str  # a pytest node id (path::name) or a path to property tests
    stateful: bool = False  # `property stateful ...` -> Hypothesis RuleBasedStateMachine


def parse_property(rule: str) -> "PropertyRule":
    prefix = "property "
    if not rule.startswith(prefix):
        raise RuleError(f"PBT rule must start with 'property ': {rule!r}")
    rest = rule[len(prefix):].strip()
    stateful = False
    if rest == "stateful" or rest.startswith("stateful "):
        stateful = True
        rest = rest[len("stateful"):].strip()
    if not rest:
        raise RuleError(f"PBT rule has empty target: {rule!r}")
    return PropertyRule(target=rest, stateful=stateful)


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
    body = rule[len(prefix):].strip()
    if not body:
        raise RuleError(f"STRUCTURAL rule has empty pattern: {rule!r}")

    # Find the rightmost ' in '/' outside ' whose right-hand side looks like a scope
    # token (single word, no spaces, not an ast-grep metavar like $Y). This keeps
    # patterns that themselves contain " in " (e.g. `for $X in $Y`) working.
    best: tuple[int, str, str] | None = None
    for keyword, mode in ((" outside ", "outside"), (" in ", "in")):
        idx = body.rfind(keyword)
        if idx == -1:
            continue
        rhs = body[idx + len(keyword):].strip()
        if _SCOPE_TOKEN.fullmatch(rhs) and (best is None or idx > best[0]):
            best = (idx, mode, rhs)

    if best is None:
        return PatternRule(pattern=body)
    idx, mode, scope = best
    pattern = body[:idx].strip()
    if not pattern:
        raise RuleError(f"STRUCTURAL rule has empty pattern before '{mode}': {rule!r}")
    return PatternRule(pattern=pattern, scope_mode=mode, scope=scope)

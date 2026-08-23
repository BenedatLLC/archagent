"""The `**Tier:**` vocabulary — which tokens name a layer, and which say "not a layer at all".

A leaf module on purpose. `evaluate` needs the ranks to find layering violations and `drift` needs them
to notice a subsystem claiming a layer it has no business on (issue #26), and `evaluate` already imports
`drift` — so putting this in either one would make `drift` import `evaluate` and close a second cycle on
top of the one ADR 0003 already records. Pulling shared plumbing into a leaf both can import is the
remedy that ADR names, applied to one small thing.

This module imports nothing internal, which is the property that keeps it usable from anywhere.
"""

from __future__ import annotations

import re

#: The metadata line. Tolerant about the colon and the surrounding whitespace because real artifacts are.
TIER_LINE = re.compile(r"^\s*\*\*\s*Tier\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)

#: Ordered from the top of the stack down. Consumers use the ordering to detect a lower layer depending
#: upward, or a dependency skipping a layer.
TIER_RANK: dict[str, int] = {
    "ui": 4, "presentation": 4, "frontend": 4, "web": 4, "view": 4,
    "api": 3, "app": 3, "application": 3, "interface": 3, "controller": 3, "handler": 3,
    "domain": 2, "service": 2, "core": 2, "business": 2, "logic": 2, "usecase": 2,
    "infra": 1, "infrastructure": 1, "data": 1, "persistence": 1, "storage": 1, "db": 1, "adapter": 1,
}

#: Tokens that say **this subsystem is not on the ladder** — recognised, so the intent is explicit, but
#: carrying no rank, so the layering checks skip it.
#:
#: Calibration rounds 2 and 3 are why (issue #26). Seven `layer-inversion` findings labelled blind across
#: three repositories split perfectly: all three confirmations were production code, all four dismissals
#: were test or migration packages. Every one of those was tiered `infra` — rank 1, the bottom — so
#: everything a test imported read as "upward", and one test subsystem produced an inversion against every
#: production subsystem it exercised. wardrowbe's produced four.
#:
#: Tests are not a layer beneath the code they exercise. They sit outside the stack, as do migrations,
#: build tooling and operational scripts. Until now there was no way to say so: the subsystem template
#: offered `<ui | domain | infra>` and `infra` was the natural pick for test plumbing.
#:
#: **Recognised rather than merely unknown.** An unrecognised token is already skipped, so on its own this
#: changes nothing — what it buys is the difference between *the author said this is not a layer* and
#: *the author typed `domian`*. A checker can tell those apart; a silent skip cannot.
TIER_NONLAYERED: frozenset[str] = frozenset({
    "test", "tests", "testing",
    "migration", "migrations",
    "ops", "operations", "tooling", "build", "scripts",
    "none",
})


def tier_rank(token: str | None) -> int | None:
    """The layer rank of a `**Tier:**` token, or `None` if it does not sit on the ladder."""
    return TIER_RANK.get(_norm(token))


def is_nonlayered(token: str | None) -> bool:
    """Did the author explicitly place this subsystem off the ladder?

    Distinct from `tier_rank(...) is None`, which is also true of a typo and of an absent declaration.
    """
    return _norm(token) in TIER_NONLAYERED


def is_recognized(token: str | None) -> bool:
    """A token this vocabulary knows, whether or not it names a layer."""
    t = _norm(token)
    return t in TIER_RANK or t in TIER_NONLAYERED


def _norm(token: str | None) -> str:
    return (token or "").strip().lower()


def tier_of(text: str) -> str | None:
    """The `**Tier:**` token declared in a subsystem document, or None.

    Lived in three places before this — `evaluate`, `graph` and (nearly) `drift` — which is the duplicated
    decision archagent's own `scattered-source-of-truth` check exists to find. Takes the first token, so
    `**Tier:** domain (see ADR 0004)` reads as `domain`.
    """
    m = TIER_LINE.search(text)
    if not m:
        return None
    return re.split(r"[,\s]+", m.group(1).strip())[0].strip("`").lower() or None

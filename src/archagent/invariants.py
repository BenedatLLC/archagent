"""Parse the single source of invariants: a standardized markdown table.

See design-decisions DD-3. The table lives at ``architecture/invariants.md`` and
has columns: ID | Type | Tier | Applies-to | Rule | Severity | Why | Status.

Only the first markdown table in the file is read; surrounding prose is ignored,
so the file stays human-readable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COLUMNS = ["id", "type", "tier", "applies-to", "rule", "severity", "why", "status"]


@dataclass
class Invariant:
    id: str
    type: str  # BOUNDARY | INTERFACE | DATAFLOW | STRUCTURAL | PURPOSE
    tier: str  # structural | contract | pbt | model-check
    applies_to: str  # e.g. "python", "ts"
    rule: str  # compact DSL string the generator parses
    severity: str = "error"  # error | warn
    why: str = ""
    status: str = "active"  # active | proposed | deprecated
    line: int = 0  # 1-based line in invariants.md, for diagnostics


def parse_invariants(path: Path) -> list[Invariant]:
    if not path.exists():
        raise FileNotFoundError(f"No invariants file at {path}")
    rows = _parse_first_table(path.read_text())
    invariants: list[Invariant] = []
    for cells, lineno in rows:
        get = lambda key, default="": cells.get(key, default).strip()  # noqa: E731
        if not get("id"):
            continue
        invariants.append(
            Invariant(
                id=get("id"),
                type=get("type").upper(),
                tier=get("tier").lower(),
                applies_to=get("applies-to").lower(),
                rule=_strip_code(get("rule")),
                severity=get("severity", "error").lower() or "error",
                why=get("why"),
                status=get("status", "active").lower() or "active",
                line=lineno,
            )
        )
    return invariants


def _strip_code(value: str) -> str:
    """Drop the markdown backticks people wrap the Rule cell in."""
    return value.strip().strip("`").strip()


def _is_separator(cells: list[str]) -> bool:
    return all(set(c) <= set("-: ") and c for c in cells)


def _parse_first_table(text: str) -> list[tuple[dict[str, str], int]]:
    header: list[str] | None = None
    rows: list[tuple[dict[str, str], int]] = []
    started = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line.startswith("|"):
            if started:
                break  # first table ended
            continue
        started = True
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if _is_separator(cells):
            continue
        row = {header[i]: cells[i] for i in range(min(len(header), len(cells)))}
        rows.append((row, lineno))
    return rows

"""Parsing the markdown invariant table."""

from archagent.invariants import parse_invariants

TABLE = """# System Invariants

Some prose before the table.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-1 | BOUNDARY | structural | python | `forbid a -> b` | error | [x](y) | active |
| STR-2 | structural | structural | py | `forbid-pattern eval($$$)` | warn |  | active |

More prose after — not a table row.
"""


def test_parses_rows_and_normalizes(tmp_path):
    p = tmp_path / "invariants.md"
    p.write_text(TABLE)
    invs = parse_invariants(p)

    assert [i.id for i in invs] == ["BND-1", "STR-2"]
    b = invs[0]
    assert b.type == "BOUNDARY"  # upper-cased
    assert b.tier == "structural"
    assert b.applies_to == "python"
    assert b.rule == "forbid a -> b"  # backticks stripped
    assert b.severity == "error" and b.status == "active"
    # second row: type upper-cased, warn severity, empty why tolerated
    assert invs[1].type == "STRUCTURAL"
    assert invs[1].severity == "warn"
    assert invs[1].why == ""


def test_only_first_table_and_empty_ok(tmp_path):
    p = tmp_path / "invariants.md"
    p.write_text("# x\n\n| ID | Type |\n|----|----|\n\nprose\n\n| ID | Type |\n|--|--|\n| Z | X |\n")
    # header + separator only for the first table, then prose ends it → no rows
    assert parse_invariants(p) == []

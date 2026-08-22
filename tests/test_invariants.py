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


# --- Verification and Graduation path (issue #16) ----------------------------------------------------

_TABLE = """# Invariants

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status | Verification | Graduation path |
|----|------|------|-----------|------|----------|-----|--------|--------------|-----------------|
| A-001 | BOUNDARY | structural | python | `forbid a -> b` | error | layering | active | | |
| B-001 | STRUCTURAL | prose | python | only ai_service calls the provider | error | one place | active | `tests/test_ai.py::test_single_caller` | needs an ast-grep pattern for call sites |
| C-001 | STRUCTURAL | prose | python | jobs write a terminal status | warn | no silent ends | active | | |
"""


def _write(tmp_path, text):
    p = tmp_path / "invariants.md"
    p.write_text(text)
    return parse_invariants(p)


def test_verification_and_graduation_are_read(tmp_path):
    by = {i.id: i for i in _write(tmp_path, _TABLE)}
    assert by["B-001"].verification == "`tests/test_ai.py::test_single_caller`"
    assert by["B-001"].graduation.startswith("needs an ast-grep pattern")


def test_a_prose_rule_with_a_verification_is_not_unverified(tmp_path):
    """The distinction the columns exist for: `prose` means this tool cannot generate a checker, not that
    nobody checks it. Round 4 had rules backed by a real test that the row never mentioned."""
    by = {i.id: i for i in _write(tmp_path, _TABLE)}
    assert by["B-001"].is_prose and not by["B-001"].unverified
    assert by["C-001"].unverified


def test_an_enforced_rule_is_never_unverified(tmp_path):
    """A structural rule is checked by `check`; the column is for the rules that are not."""
    by = {i.id: i for i in _write(tmp_path, _TABLE)}
    assert not by["A-001"].is_prose and not by["A-001"].unverified


def test_the_columns_are_optional(tmp_path):
    """Additive and gated, per ADL §1.2 — a table without them stays conformant and every row parses."""
    invs = _write(tmp_path, """# Invariants

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| A-001 | BOUNDARY | prose | python | `forbid a -> b` | error | layering | active |
""")
    assert len(invs) == 1 and invs[0].verification == "" and invs[0].unverified


def test_graduation_is_read_under_either_header(tmp_path):
    """`Graduation path` is the documented spelling; `Graduation` is what people will type."""
    invs = _write(tmp_path, """# Invariants

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status | Graduation |
|----|------|------|-----------|------|----------|-----|--------|------------|
| A-001 | BOUNDARY | prose | python | r | error | w | active | needs Go support |
""")
    assert invs[0].graduation == "needs Go support"

"""`check` must not disprove its own heading (#38).

It printed "asserted in invariants.md, verified by nobody" and then, six lines later, "9 state how they
are verified" with the test names. The wording predates the `Verification` column (#16), whose whole
purpose is to separate *archagent cannot compile a checker* from *nobody checks this* — so asserting the
second for every skipped row discarded the distinction the column exists to draw.

Round 2's user tester read it as the supplied metadata having been ignored, and named it as one of three
instances of the same theme: the terminal language overstating what the extractors established.
"""

import re
from pathlib import Path

from typer.testing import CliRunner

from archagent.cli import app

FIXTURE = """| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
{rows}
"""
ROW = "| {id} | BEHAVIOUR | prose | python | {rule} | error | because | active |{ver}"


def _repo(tmp_path, rows):
    (tmp_path / "architecture" / "subsystems").mkdir(parents=True)
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "architecture" / "subsystems" / "a.md").write_text(
        "# A\n\n**Covers:** `src/pkg/a.py`\n")
    (tmp_path / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nroot_package = "pkg"\nsource_paths = ["src"]\n')
    (tmp_path / "architecture" / "invariants.md").write_text(rows)
    return tmp_path


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _check(root) -> str:
    """The rendered report, with colour stripped and wrapping undone.

    rich colourises numbers and hard-wraps to the terminal width, so a plain substring assertion fails on
    correct output — which is the same reason `check.py` strips ANSI from the checkers' own output before
    matching it.
    """
    res = CliRunner().invoke(app, ["check", "--project", str(root)])
    return " ".join(_ANSI.sub("", res.stdout).split())


def _table(specs) -> str:
    header = ("| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status | Verification |\n"
              "|----|------|------|-----------|------|----------|-----|--------|--------------|\n")
    rows = "".join(
        f"| {i} | BEHAVIOUR | prose | python | must not X | error | because | active | {v} |\n"
        for i, v in specs)
    return "# Invariants\n\n" + header + rows


def test_the_heading_no_longer_says_verified_by_nobody(tmp_path):
    """The literal regression."""
    root = _repo(tmp_path, _table([("INV-001", "`tests/test_a.py::test_x`")]))
    out = _check(root)
    assert "verified by nobody" not in out
    assert "Not checked by archagent" in out


def test_when_every_skipped_rule_names_its_verification_the_heading_says_so(tmp_path):
    root = _repo(tmp_path, _table([("INV-001", "`tests/test_a.py::test_x`"),
                                   ("INV-002", "`tests/test_b.py::test_y`")]))
    out = _check(root)
    assert "every one names how it is verified" in out


def test_when_none_do_the_heading_says_that_instead(tmp_path):
    """The case the old wording was written for is still reported, and still bluntly — this must not
    become a fix that softens a real silence."""
    root = _repo(tmp_path, _table([("INV-001", ""), ("INV-002", "")]))
    out = _check(root)
    assert "none of them says how it is verified" in out


def test_a_mixed_artifact_reports_both_counts(tmp_path):
    """The interesting case, and the one a single global sentence cannot express."""
    root = _repo(tmp_path, _table([("INV-001", "`tests/test_a.py::test_x`"), ("INV-002", "")]))
    out = _check(root)
    assert "1 of 2 name how they are verified, 1 do not" in out


def test_the_two_blocks_never_contradict_each_other(tmp_path):
    """The property behind all of the above: whatever the heading claims about verification, the `Prose
    rules` block below it must not immediately report the opposite."""
    for specs in ([("INV-001", "`tests/test_a.py::test_x`")],
                  [("INV-001", "")],
                  [("INV-001", "`tests/test_a.py::test_x`"), ("INV-002", "")]):
        out = _check(_repo(tmp_path / f"r{len(specs)}{specs[0][1]!r:.3}", _table(specs)))
        says_nobody = "none of them says how it is verified" in out
        lists_a_verification = "state how they are verified" in out and "0 state how" not in out
        assert not (says_nobody and lists_a_verification), out

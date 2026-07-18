"""mdutil — code-fence stripping and empty-value detection (issue #1 guards)."""

from archagent.mdutil import is_empty_value, strip_code_fences


def test_strip_code_fences_removes_blocks():
    text = (
        "before\n"
        "```mermaid\n"
        "Configured --> Ready: FILE_LOCATIONS\n"
        "```\n"
        "middle\n"
        "~~~python\n"
        "**Config:** SECRET\n"
        "~~~\n"
        "after\n"
    )
    out = strip_code_fences(text)
    assert "before" in out and "middle" in out and "after" in out
    assert "Configured" not in out          # mermaid content dropped
    assert "**Config:**" not in out         # fenced code content dropped


def test_strip_code_fences_keeps_unfenced_metadata():
    text = "**Config:** REAL_KEY\n```\ncode\n```\n"
    out = strip_code_fences(text)
    assert "**Config:** REAL_KEY" in out and "code" not in out


def test_is_empty_value():
    assert is_empty_value("") is True
    assert is_empty_value("   ") is True
    assert is_empty_value("_(none — this is the base of the dependency graph)_") is True
    assert is_empty_value("(none)") is True
    assert is_empty_value("none") is True
    assert is_empty_value("N/A") is True
    assert is_empty_value("TBD") is True
    # real values are not empty
    assert is_empty_value("billing via sync-call, ledger") is False
    assert is_empty_value("DATABASE_URL") is False
    assert is_empty_value("src/pkg/**") is False

"""`scan-invariants` must not call a test's failure text a high-confidence invariant (#40).

From user test round 2. The heading read "Explicit markers (22) — high confidence" and the list included
`response`, `123, 456` and `Transfer-Encoding` — assertion messages from httpx's test suite.

Two separate defects, and the second is the one that generalises: the scanner was confident it had found
a *marker*, and the label transferred that confidence to the claim that the marker states an
architectural rule. The tester named this alongside #37 and #38 as one theme — terminal language
overstating what the extractors established.
"""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.invscan import scan_invariants


def _cfg(tmp):
    (tmp / "architecture").mkdir(parents=True)
    (tmp / "src" / "pkg").mkdir(parents=True)
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="pkg", source_paths=["src"]),
                  ts=TSConfig(source_paths=["src"]))


def _src(cfg, rel, text):
    p = cfg.project_root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_a_tests_assertion_message_is_not_a_stated_invariant(tmp_path):
    """The reported case. In a test, the message after the comma is the *test's* failure text."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/tests/test_headers.py",
         'def test_h():\n    assert h == v, "123, 456"\n    assert r.text, "response"\n')
    got = [c.text for c in scan_invariants(cfg)]
    assert "response" not in got
    assert "123, 456" not in got


def test_an_explicit_marker_in_a_test_is_still_an_invariant(tmp_path):
    """Not a blanket skip of test files, for the same reason `hardcoded-endpoint` re-reads them instead
    of dropping them: `# INVARIANT:` means what it says wherever someone wrote it."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/tests/test_x.py",
         '# INVARIANT: the fixture set is always sorted\ndef test_x():\n    assert True\n')
    found = [c for c in scan_invariants(cfg) if "always sorted" in c.text]
    assert found and found[0].confidence == "high"


def test_an_assertion_message_in_production_code_is_kept_but_demoted(tmp_path):
    """It does sometimes state intent — httpx's `Cannot mix named and unnamed arguments` does — so it is
    worth showing. It is not a labelled invariant, so it is not shown as one."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/urls.py",
         'def f(*a, **k):\n    assert not (a and k), "Cannot mix named and unnamed arguments."\n')
    found = [c for c in scan_invariants(cfg) if "Cannot mix" in c.text]
    assert found, "a production assertion message is still a candidate"
    assert found[0].kind == "assertion" and found[0].confidence == "low"


def test_a_labelled_invariant_and_an_assertion_are_not_the_same_kind(tmp_path):
    """The distinction the fix rests on — one is a declaration, the other is failure text."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py",
         '# INVARIANT: queries are always sorted\n'
         'def f(x):\n    assert x, "x was falsy"\n')
    kinds = {c.kind for c in scan_invariants(cfg)}
    assert kinds == {"marker", "assertion"}


def test_the_heading_no_longer_claims_high_confidence(tmp_path):
    """The confidence was about marker detection; the sentence read as being about the rule."""
    from typer.testing import CliRunner
    from archagent.cli import app
    import re
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", '# INVARIANT: queries are always sorted\nx = 1\n')
    out = re.sub(r"\x1b\[[0-9;]*m", "", CliRunner().invoke(
        app, ["scan-invariants", "--project", str(tmp_path)]).stdout)
    out = " ".join(out.split())
    assert "high confidence" not in out
    assert "still yours to judge" in out

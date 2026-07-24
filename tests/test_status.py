"""archagent status — per-package coverage snapshot."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.status import _package_of, status


def _cfg(tmp):
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="base", source_paths=["base"]), ts=TSConfig())


def _mk(tmp, rel, text="x = 1\n"):
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_package_of():
    prefixes = ["base/"]
    assert _package_of("base/svc_a/mod.py", prefixes) == "svc_a"
    assert _package_of("base/top.py", prefixes) == "(root)"
    assert _package_of("other/x.py", prefixes) == "other"


def test_no_covers_reports_zero_coverage(tmp_path):
    _mk(tmp_path, "base/svc_a/m.py")
    _mk(tmp_path, "base/svc_b/m.py")
    _mk(tmp_path, "base/svc_a/__init__.py", "")
    (tmp_path / "architecture").mkdir()
    r = status(_cfg(tmp_path))
    assert r.covers_declared is False
    assert r.covered == 0                      # __init__ not credited until coverage is declared
    assert {p.name for p in r.packages} == {"svc_a", "svc_b"}
    assert r.total == 3


def test_declared_covers_counts_package(tmp_path):
    _mk(tmp_path, "base/svc_a/m.py")
    _mk(tmp_path, "base/svc_a/n.py")
    _mk(tmp_path, "base/svc_b/m.py")
    sub = tmp_path / "architecture" / "subsystems"
    sub.mkdir(parents=True)
    (sub / "svc_a.md").write_text("# A\n\n**Covers:** `base/svc_a/**`\n")
    r = status(_cfg(tmp_path))
    assert r.covers_declared is True
    assert r.subsystem_docs == 1
    by = {p.name: p for p in r.packages}
    assert by["svc_a"].covered == 2 and by["svc_a"].pct == 100
    assert by["svc_b"].covered == 0
    assert r.documented_packages == 1


def test_init_py_credited_once_covers_declared(tmp_path):
    _mk(tmp_path, "base/svc_a/__init__.py", "")
    _mk(tmp_path, "base/svc_a/m.py")
    _mk(tmp_path, "base/svc_b/__init__.py", "")  # a package with only __init__, uncovered by any glob
    sub = tmp_path / "architecture" / "subsystems"
    sub.mkdir(parents=True)
    (sub / "svc_a.md").write_text("# A\n\n**Covers:** `base/svc_a/m.py`\n")
    r = status(_cfg(tmp_path))
    by = {p.name: p for p in r.packages}
    assert by["svc_a"].covered == 2          # m.py (glob) + __init__.py (credited)
    assert by["svc_b"].covered == 1          # __init__.py credited now that coverage is declared

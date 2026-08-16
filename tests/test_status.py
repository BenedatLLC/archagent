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


# --- depth: is the description usable, not just present ---------------------------------------------

def _artifact(tmp, docs: dict[str, str], src: dict[str, str]):
    for rel, text in {**src}.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subs = tmp / "architecture/subsystems"
    subs.mkdir(parents=True)
    for name, text in docs.items():
        (subs / f"{name}.md").write_text(text)
    (tmp / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nsource_paths = ["src"]\n')
    return tmp


MODELS = "\n\n".join(f"class T{i}:\n    __tablename__ = 't{i}'" for i in range(8))


def test_a_document_far_thinner_than_its_siblings_is_flagged(tmp_path):
    """Coverage reported 100% on an artifact whose reader found three documents too thin to trace a
    change through. Presence and usability come apart, and only the first was measured."""
    from archagent.config import load_config
    from archagent.status import status
    root = _artifact(tmp_path, {
        "thin": "# thin\n\n**Covers:** `src/a.py`, `src/b.py`, `src/c.py`\n\nIt does things.\n",
        "full": "# full\n\n**Covers:** `src/d.py`\n\n" + ("Real prose about the design. " * 30),
        "also": "# also\n\n**Covers:** `src/e.py`\n\n" + ("More real prose here. " * 30),
    }, {f"src/{n}.py": "x = 1\n" for n in "abcde"})
    r = status(load_config(root))
    assert [d.name for d in r.thin] == ["thin"]


def test_a_terse_but_even_artifact_flags_nothing(tmp_path):
    """The bar is relative on purpose: a terse house style is a style, and an absolute words-per-file
    threshold would punish it everywhere."""
    from archagent.config import load_config
    from archagent.status import status
    root = _artifact(tmp_path, {
        n: f"# {n}\n\n**Covers:** `src/{n}.py`\n\nShort but even.\n" for n in "abc"
    }, {f"src/{n}.py": "x = 1\n" for n in "abc"})
    assert status(load_config(root)).thin == []


def test_many_types_and_no_diagram_is_flagged(tmp_path):
    """A document covering eight table declarations is describing how they relate."""
    from archagent.config import load_config
    from archagent.status import status
    root = _artifact(tmp_path, {"models": "# models\n\n**Covers:** `src/models.py`\n\n" + ("Prose. " * 40)},
                     {"src/models.py": MODELS})
    d = status(load_config(root)).depth[0]
    assert d.types >= 8 and d.wants_a_diagram


def test_a_document_with_a_diagram_is_not_flagged(tmp_path):
    from archagent.config import load_config
    from archagent.status import status
    root = _artifact(tmp_path, {"models": "# models\n\n**Covers:** `src/models.py`\n\n" + ("Prose. " * 40)
                                + "\n```mermaid\nerDiagram\n  A ||--o{ B : has\n```\n"},
                     {"src/models.py": MODELS})
    assert not status(load_config(root)).depth[0].wants_a_diagram


def test_a_subsystem_with_few_types_does_not_need_one(tmp_path):
    """Not "every document needs a diagram" — a CLI with no states was right that one would be
    decoration."""
    from archagent.config import load_config
    from archagent.status import status
    root = _artifact(tmp_path, {"cli": "# cli\n\n**Covers:** `src/cli.py`\n\n" + ("Prose. " * 40)},
                     {"src/cli.py": "def main():\n    pass\n"})
    assert not status(load_config(root)).depth[0].wants_a_diagram


def test_tables_and_metadata_do_not_count_as_prose(tmp_path):
    """A document could otherwise look substantial by listing its own Covers globs and a twenty-row
    table, which is the shape the thin documents already had."""
    from archagent.config import load_config
    from archagent.status import status
    doc = ("# x\n\n**Covers:** `src/a.py`\n**Tier:** domain\n\n"
           "| a | b |\n|---|---|\n" + "".join(f"| r{i} | v{i} |\n" for i in range(20))
           + "\n```python\nlots = of + code\n```\n\nOne real sentence.\n")
    root = _artifact(tmp_path, {"x": doc}, {"src/a.py": "x = 1\n"})
    assert status(load_config(root)).depth[0].words == 3

"""Relative imports in a package initialiser resolve against the package itself (#41).

From user test round 2. `httpx/__init__.py` is entirely `from ._api import *`, `from ._auth import *`,
and the import graph gave it **no edges at all** — so a correctly declared `interfaces -> auth` edge was
reported stale, and the tester declined to "fix" it:

> Changing the artifact to make this report green would make the documentation less accurate.

That is the worst shape a drift tool can take: penalising an accurate artifact and rewarding an
inaccurate one.

The star import is where it was noticed, not the cause. `level` counts from the *containing package*,
and for `__init__.py` the file **is** that package rather than a module inside it — so one component too
many was stripped from every relative import in every package initialiser, star or not.
"""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import _imports_of, _import_graph, _source_files, find_drift


def _cfg(tmp):
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="pkg", source_paths=["src"]),
                  ts=TSConfig(source_paths=["src"]))


def _src(cfg, rel, text):
    p = cfg.project_root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _sub(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / f"{name}.md").write_text(text)


def test_a_star_reexport_is_an_edge(tmp_path):
    """The reported case."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/__init__.py", "from ._api import *\n")
    _src(cfg, "pkg/_api.py", "x = 1\n")
    g = _import_graph(tmp_path, cfg, _source_files(cfg))
    assert g["src/pkg/__init__.py"] == {"src/pkg/_api.py"}


def test_every_relative_form_in_an_initialiser_resolves(tmp_path):
    """Not just the star. `from . import x`, `from .m import Name` and `from .m import *` were all
    misresolved by the same off-by-one, which is why the fix is about `__init__.py` rather than about
    wildcard imports."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/__init__.py",
         "from ._api import *\n"
         "from . import _auth\n"
         "from ._client import Client\n")
    for m in ("_api", "_auth", "_client"):
        _src(cfg, f"pkg/{m}.py", "x = 1\n")
    g = _import_graph(tmp_path, cfg, _source_files(cfg))
    assert g["src/pkg/__init__.py"] == {
        "src/pkg/_api.py", "src/pkg/_auth.py", "src/pkg/_client.py"}


def test_a_regular_module_is_unaffected(tmp_path):
    """The other half of the off-by-one: a module inside a package must keep resolving `level=1` against
    its parent. Fixing the initialiser by shifting everything would just move the bug."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/__init__.py", "")
    _src(cfg, "pkg/a.py", "from . import b\nfrom .c import thing\n")
    _src(cfg, "pkg/b.py", "x = 1\n")
    _src(cfg, "pkg/c.py", "thing = 1\n")
    g = _import_graph(tmp_path, cfg, _source_files(cfg))
    assert g["src/pkg/a.py"] == {"src/pkg/b.py", "src/pkg/c.py"}


def test_a_nested_initialiser_resolves_its_parent_too(tmp_path):
    """`level=2` from `pkg/sub/__init__.py` means `pkg`, not `pkg`'s parent."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/__init__.py", "")
    _src(cfg, "pkg/top.py", "x = 1\n")
    _src(cfg, "pkg/sub/__init__.py", "from .inner import *\nfrom ..top import thing\n")
    _src(cfg, "pkg/sub/inner.py", "y = 1\n")
    g = _import_graph(tmp_path, cfg, _source_files(cfg))
    assert g["src/pkg/sub/__init__.py"] == {"src/pkg/sub/inner.py", "src/pkg/top.py"}


def test_a_declared_edge_through_a_reexport_is_no_longer_stale(tmp_path):
    """The consequence that made this worth fixing rather than documenting."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/__init__.py", "from ._auth import *\n")
    _src(cfg, "pkg/_auth.py", "x = 1\n")
    _sub(cfg, "interfaces", "# I\n\n**Covers:** `src/pkg/__init__.py`\n**Connects:** auth via import\n")
    _sub(cfg, "auth", "# A\n\n**Covers:** `src/pkg/_auth.py`\n")
    assert ("interfaces", "auth") not in find_drift(cfg).stale_deps


def test_the_star_name_is_not_emitted_as_a_module(tmp_path):
    """`from ._api import *` must not also produce a candidate named `pkg._api.*`."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("from ._api import *\n")
    assert not any(m.endswith(".*") for m in _imports_of(tmp_path, "pkg/__init__.py", "pkg"))

"""archagent modules — Python file → import-module resolution, collision-aware (drift.module_map)."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import module_map


def _cfg(tmp, source_paths):
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(source_paths=source_paths), ts=TSConfig())


def _mk(tmp, rel, text="x = 1\n"):
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_basic_resolution(tmp_path):
    _mk(tmp_path, "src/pkg/__init__.py", "")
    _mk(tmp_path, "src/pkg/mod.py")
    m = module_map(_cfg(tmp_path, ["src"]))
    assert m["pkg"] == ["src/pkg/__init__.py"]
    assert m["pkg.mod"] == ["src/pkg/mod.py"]


def test_detects_top_level_name_collision(tmp_path):
    # two packages under different source roots that both install as top-level `shared`
    _mk(tmp_path, "a/shared/__init__.py", "")
    _mk(tmp_path, "b/shared/__init__.py", "")
    m = module_map(_cfg(tmp_path, ["a", "b"]))
    collisions = {mod: files for mod, files in m.items() if len(files) > 1}
    assert "shared" in collisions
    assert sorted(collisions["shared"]) == ["a/shared/__init__.py", "b/shared/__init__.py"]


def test_ignores_non_python(tmp_path):
    _mk(tmp_path, "src/pkg/mod.py")
    _mk(tmp_path, "src/pkg/data.ts", "export const x = 1;\n")
    m = module_map(_cfg(tmp_path, ["src"]))
    assert all(f.endswith(".py") for files in m.values() for f in files)


# --- a package at the repository root (the other standard Python layout) ------------------------------

def test_a_source_path_of_dot_resolves_modules():
    """`source_paths = ["."]` means the repository root, which is where `dspy/`, `requests/` and `flask/`
    keep their package. The prefix was built as `"." + "/"`, so no path ever started with it and such a
    repository resolved **no modules at all** — an empty import graph, BOUNDARY contracts scoped to
    nothing, every structural signal silent, and `check` reporting that all invariants hold.

    Every target archagent had been run against happened to use the other layout (`src/`, `backend/`),
    which is why this survived until a flat-layout repository was tried."""
    from archagent.drift import _module_of
    assert _module_of("dspy/adapters/base.py", ["."]) == "dspy.adapters.base"
    assert _module_of("dspy/__init__.py", ["."]) == "dspy"


def test_an_empty_source_path_means_the_root_too():
    from archagent.drift import _module_of
    assert _module_of("pkg/a.py", [""]) == "pkg.a"


def test_a_trailing_slash_or_leading_dot_slash_is_tolerated():
    from archagent.drift import _module_of
    assert _module_of("src/pkg/a.py", ["src/"]) == "pkg.a"
    assert _module_of("src/pkg/a.py", ["./src"]) == "pkg.a"


def test_a_nested_source_path_still_strips_only_its_own_prefix():
    """The rule the fastapi-template corpus entry documents: `backend`, not `backend/app`, because the
    module name is derived by stripping the source path — and `backend/app` would make
    `app/api/deps.py` resolve as `api.deps` while the code imports `app.api.deps`."""
    from archagent.drift import _module_of
    assert _module_of("backend/app/api/deps.py", ["backend"]) == "app.api.deps"

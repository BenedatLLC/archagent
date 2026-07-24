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

"""archagent drift — the reflexion-diff between architecture/ docs and code."""

import json
import os
import shutil
import subprocess

import pytest

from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import find_drift


def _repo(tmp):
    (tmp / "src" / "pkg").mkdir(parents=True)
    (tmp / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp / "src" / "pkg" / "b.py").write_text("y = 2\n")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _doc(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / name).write_text(text)


def test_dangling_reference_flags_missing_only(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nUses `src/pkg/a.py` and `src/pkg/gone.py`.\n")
    r = find_drift(cfg)
    missing = [ref for _, ref in r.dangling]
    assert "src/pkg/gone.py" in missing
    assert "src/pkg/a.py" not in missing


def test_resolves_bare_and_subpath_refs(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nSee `a.py` and `pkg/b.py` — both real.\n")
    assert find_drift(cfg).dangling == []


def test_non_code_backticks_are_ignored(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nRun `check`, see `../invariants.md`, call `st.lists`.\n")
    assert find_drift(cfg).dangling == []


def test_covers_glob_matching_nothing_is_dangling(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n**Covers:** `src/pkg/**`\n")       # matches a.py, b.py
    assert find_drift(cfg).dangling == []
    _doc(cfg, "ghost.md", "# Ghost\n\n**Covers:** `src/ghost/**`\n")  # matches nothing
    assert any("src/ghost/**" in ref for _, ref in find_drift(cfg).dangling)


def test_undocumented_gated_on_covers(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n**Covers:** `src/pkg/a.py`\n")  # covers only a.py
    r = find_drift(cfg)
    assert r.covers_declared is True
    assert "src/pkg/b.py" in r.undocumented
    assert "src/pkg/a.py" not in r.undocumented


def test_undocumented_skipped_without_covers(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nRefs `src/pkg/a.py` and `src/pkg/b.py` but no Covers.\n")
    r = find_drift(cfg)
    assert r.covers_declared is False
    assert r.undocumented == []


def test_json_cli_output(tmp_path):
    from typer.testing import CliRunner

    from archagent.cli import app

    _repo(tmp_path)
    (tmp_path / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nroot_package = "pkg"\nsource_paths = ["src"]\n')
    (tmp_path / "architecture" / "subsystems" / "pkg.md").write_text("# Pkg\n\nUses `src/pkg/gone.py`.\n")

    result = CliRunner().invoke(app, ["drift", "--project", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert set(data) >= {"dangling", "stale", "undocumented", "git_available", "covers_declared"}
    assert any(d["ref"] == "src/pkg/gone.py" for d in data["dangling"])


def test_no_git_skips_stale(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n`src/pkg/a.py`\n")
    r = find_drift(cfg)
    assert r.git_available is False
    assert r.stale == []


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_stale_doc_detected_via_git(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n**Covers:** `src/pkg/**`\n")

    def git(*args, date=None):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, env=env)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "docs+code", date="2020-01-01T00:00:00")
    # code moves on in a later commit; the doc does not
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 2\n")
    git("add", "-A")
    git("commit", "-qm", "code change", date="2021-01-01T00:00:00")

    r = find_drift(cfg)
    assert r.git_available is True
    assert any("pkg.md" in doc for doc, _ in r.stale)

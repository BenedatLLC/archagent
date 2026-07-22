"""install-hook — native git pre-commit hook (Phase 3, initial)."""

import os
import stat

import pytest

from archagent.hooks import install_hook


def _git(tmp):
    (tmp / ".git" / "hooks").mkdir(parents=True)
    return tmp


def _hook(tmp):
    return tmp / ".git" / "hooks" / "pre-commit"


def test_creates_executable_hook(tmp_path):
    _git(tmp_path)
    r = install_hook(tmp_path)
    assert r.action == "created" and _hook(tmp_path).exists()
    text = _hook(tmp_path).read_text()
    assert text.startswith("#!/bin/sh")
    assert "archagent check" in text and "--skip-pbt" not in text
    assert os.stat(_hook(tmp_path)).st_mode & stat.S_IXUSR   # executable


def test_skip_pbt_variant(tmp_path):
    _git(tmp_path)
    install_hook(tmp_path, skip_pbt=True)
    assert "archagent check --skip-pbt" in _hook(tmp_path).read_text()


def test_idempotent_update_in_place(tmp_path):
    _git(tmp_path)
    install_hook(tmp_path)                       # full
    r = install_hook(tmp_path, skip_pbt=True)    # toggle to static-only
    assert r.action == "updated"
    text = _hook(tmp_path).read_text()
    assert text.count("# >>> archagent >>>") == 1          # not duplicated
    assert "archagent check --skip-pbt" in text


def test_appends_to_existing_foreign_hook(tmp_path):
    _git(tmp_path)
    _hook(tmp_path).write_text("#!/bin/sh\necho hi\n")
    r = install_hook(tmp_path)
    assert r.action == "appended"
    text = _hook(tmp_path).read_text()
    assert "echo hi" in text and "# >>> archagent >>>" in text
    # re-running finds our marker and updates rather than appending again
    r2 = install_hook(tmp_path)
    assert r2.action == "updated"
    assert _hook(tmp_path).read_text().count("# >>> archagent >>>") == 1


def test_not_a_git_repo_raises(tmp_path):
    with pytest.raises(ValueError):
        install_hook(tmp_path)

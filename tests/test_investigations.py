"""Recorded investigations — the expensive half of the analysis, made durable.

An investigation means someone read the code and traced whether anything actually breaks. That work must
survive the run that prompted it: the next run should report the verdict rather than re-inviting the same
investigation, and the next person should start from the write-up.
"""

import subprocess

import pytest

from archagent.config import Config, PythonConfig, TSConfig
from archagent.evaluate import evaluate
from archagent.investigations import RATINGS, evidence_hash, load, load_all, path_for, record

BODY = "# CallTypes\n\nDeclared four times; the copies have drifted and a hook silently no-ops.\n"


def _git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)


def test_a_recorded_investigation_round_trips(tmp_path):
    record(tmp_path, "sign:owner.py:abc123", "critical", BODY, by="jf",
           subjects=["a.py", "b.py"], values=["x", "y"])
    inv = load(tmp_path, "sign:owner.py:abc123", ["a.py", "b.py"], ["x", "y"])
    assert inv.rating == "critical" and inv.by == "jf" and not inv.stale
    assert "drifted" in inv.body


def test_it_lands_in_the_target_repository(tmp_path):
    """Investigations are findings about *that* codebase and belong with it, committed, where whoever
    works on it next will see them."""
    p = record(tmp_path, "sign:owner.py:abc", "minor", BODY, subjects=[], values=[])
    assert p.is_relative_to(tmp_path / ".archagent" / "investigations")
    assert p.suffix == ".md", "prose with citations should diff as prose"


def test_an_unknown_rating_is_refused(tmp_path):
    """The scale is about consequence. A word nothing reads would make the record useless."""
    with pytest.raises(ValueError, match="rating must be one of"):
        record(tmp_path, "sign:o.py:a", "quite bad", BODY)
    assert RATINGS == ("minor", "moderate", "critical")


def test_evidence_moving_marks_the_verdict_stale(tmp_path):
    """The verdict was about the finding as it stood; presenting it as current when the involved files
    have changed would be asserting something nobody checked."""
    record(tmp_path, "k", "moderate", BODY, subjects=["a.py", "b.py"], values=["x"])
    assert not load(tmp_path, "k", ["a.py", "b.py"], ["x"]).stale
    assert load(tmp_path, "k", ["a.py", "b.py", "c.py"], ["x"]).stale


def test_the_evidence_hash_covers_all_subjects_not_just_the_owner():
    """The finding id keys on owner + values; a changed *set of involved files* is invisible to it."""
    assert evidence_hash(["a.py"], ["x"]) != evidence_hash(["a.py", "b.py"], ["x"])


def test_a_missing_investigation_is_absent_not_an_error(tmp_path):
    assert load(tmp_path, "never-investigated") is None
    assert load_all(tmp_path) == []


def test_a_file_without_frontmatter_is_ignored(tmp_path):
    p = path_for(tmp_path, "k")
    p.parent.mkdir(parents=True)
    p.write_text("just some notes\n")
    assert load(tmp_path, "k") is None


def test_the_summary_skips_the_heading(tmp_path):
    record(tmp_path, "k", "minor", "# Title\n\nThe substantive first line.\n")
    assert load(tmp_path, "k").summary == "The substantive first line."


# --- how it changes what evaluate reports -----------------------------------------------------

STATE_ENUM = ('from enum import Enum\n\n\nclass JobState(Enum):\n'
              '    QUEUED = "queued"\n    RUNNING = "running"\n    DONE = "done"\n    FAILED = "failed"\n')


def _repo_with_escape(tmp):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@e.com")
    _git(tmp, "config", "user.name", "t")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    (tmp / "src" / "pkg").mkdir(parents=True)
    (tmp / "src" / "pkg" / "state.py").write_text(STATE_ENUM)
    (tmp / "src" / "pkg" / "use.py").write_text(
        "".join(f'if s.value == "{v}":\n    pass\n' for v in ("queued", "running", "done")))
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-q", "-m", "init")
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="pkg", source_paths=["src"]),
                  ts=TSConfig(source_paths=["src"]))


def test_an_investigated_finding_stops_asking_to_be_investigated(tmp_path):
    cfg = _repo_with_escape(tmp_path)
    f = next(x for x in evaluate(cfg).findings if x.sign == "enum-value-escape")
    assert f.investigate, "the unwrapped .value escape should be flagged"

    record(tmp_path, f.id, "minor", BODY, by="jf", subjects=f.subjects, values=f.values)
    after = next(x for x in evaluate(cfg).findings if x.sign == "enum-value-escape")
    assert after.investigate is False
    assert after.investigation["rating"] == "minor" and not after.investigation["stale"]


def test_a_stale_investigation_still_asks(tmp_path):
    """If the finding has moved, the old verdict is shown but the question is open again."""
    cfg = _repo_with_escape(tmp_path)
    f = next(x for x in evaluate(cfg).findings if x.sign == "enum-value-escape")
    record(tmp_path, f.id, "minor", BODY, subjects=f.subjects + ["elsewhere.py"], values=f.values)
    after = next(x for x in evaluate(cfg).findings if x.sign == "enum-value-escape")
    assert after.investigation["stale"] and after.investigate is True

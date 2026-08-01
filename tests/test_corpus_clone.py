"""Cached-clone validation — a clone that cannot walk its own history must not be used.

Kibana arrived with a commit-graph referencing objects absent from the object database, a known
`--filter=blob:none` failure mode. Git aborts the walk with exit 128 and "in the commit graph file but not
in the object database"; the harness had been reading a failed walk as an empty one, so the repository
presented as having no history at all.

Note on what can and cannot be tested locally: a *malformed* commit-graph is not enough to reproduce it —
git validates the header and falls back gracefully, which the first attempt at this test discovered. The
real condition is a **valid** graph referencing objects that were never fetched, which needs an actual
partial clone against a real remote. So the repair path is exercised by controlling the walk result, and
the real case is recorded here rather than faked by a fixture that would not behave like it.
"""

import subprocess

import pytest

import corpus
from corpus import verify_clone


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    for i in range(3):
        (tmp / f"f{i}.txt").write_text(f"v{i}\n")
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", f"c{i}")
    return tmp


def test_a_healthy_clone_passes(tmp_path):
    verify_clone(_repo(tmp_path), "HEAD")


def test_a_healthy_clones_commit_graph_is_left_alone(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "commit-graph", "write", "--reachable")
    graph = repo / ".git" / "objects" / "info" / "commit-graph"
    verify_clone(repo, "HEAD")
    assert graph.exists(), "a working clone's cache should not be discarded"


def test_a_clone_that_cannot_walk_is_repaired_by_dropping_the_graph(tmp_path, monkeypatch):
    """The graph is a derived cache, so dropping it is lossless — that is what makes this repairable
    rather than fatal. First walk fails (as kibana's did), the graph is dropped, the retry succeeds."""
    repo = _repo(tmp_path)
    _git(repo, "commit-graph", "write", "--reachable")
    graph = repo / ".git" / "objects" / "info" / "commit-graph"
    assert graph.exists()

    seen = []

    def fake_walks(clone, rev):
        seen.append(rev)
        return len(seen) > 1          # fails once, succeeds after the repair

    monkeypatch.setattr(corpus, "_walks", fake_walks)
    verify_clone(repo, "HEAD")
    assert not graph.exists(), "the unusable graph should have been dropped"
    assert len(seen) == 2, "the walk should be retried exactly once after the repair"
    assert subprocess.run(["git", "-C", str(repo), "log", "--name-status", "-n", "3"],
                          capture_output=True).returncode == 0


def test_an_unrepairable_clone_raises_rather_than_looking_empty(tmp_path):
    """The failure that started this: a bad clone must be an error, never a repository that looks clean."""
    with pytest.raises(RuntimeError, match="cannot walk history"):
        verify_clone(_repo(tmp_path), "no-such-revision")


def test_the_error_says_how_to_repair_it(tmp_path):
    with pytest.raises(RuntimeError, match="refetch|re-clone"):
        verify_clone(_repo(tmp_path), "no-such-revision")

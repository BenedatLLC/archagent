"""Step 1 — learning this project's bug-fix commit wording (history.py)."""

import subprocess

import json

from archagent.history import (
    PROFILE_PATH,
    HistoryProfile,
    gather_evidence,
    history_profile,
    infer_profile,
    load_profile,
    save_profile,
)


def _git(tmp, *args):
    subprocess.run(["git", "-C", str(tmp), *args], check=True, capture_output=True)


def _repo(tmp, subjects):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    for i, s in enumerate(subjects):
        (tmp / "f.txt").write_text(f"v{i}\n")
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", s)
    return tmp


def _profile(tmp, subjects):
    _repo(tmp, subjects)
    return infer_profile(gather_evidence(tmp))


def _labels(profile, subjects):
    rx = profile.matcher()
    return [s for s in subjects if rx and rx.search(s)]


def test_learns_conventional_style(tmp_path):
    subjects = ["fix(router): retry loop", "fix: null deref", "feat(api): add endpoint",
                "docs: readme", "chore: bump deps", "feat: streaming"]
    p = _profile(tmp_path, subjects)
    assert "conventional" in p.style
    assert set(_labels(p, subjects)) == {"fix(router): retry loop", "fix: null deref"}


def test_learns_tracker_reference_style(tmp_path):
    """The style a hard-coded `fix(...)` matcher scores zero on (Django's) must still be learned."""
    subjects = [f"Fixed #{100 + i} -- corrected the thing" for i in range(6)]
    subjects += ["Added a new admin widget", "Refs #200 -- follow-up work"]
    p = _profile(tmp_path, subjects)
    labelled = _labels(p, subjects)
    assert len(labelled) == 6
    assert "Added a new admin widget" not in labelled
    assert "Refs #200 -- follow-up work" not in labelled  # a reference is not a fix


def test_learns_scope_first_prose(tmp_path):
    subjects = ["evaluate: fix a false positive", "drift: fixed the glob", "docs: rewrite the intro",
                "graph: add mermaid output", "check: fix exit code"]
    p = _profile(tmp_path, subjects)
    assert len(_labels(p, subjects)) == 3


def test_does_not_match_words_containing_fix(tmp_path):
    subjects = ["fix: real bug"] * 3 + ["add fixtures for the parser", "prefix the log lines",
                "refactor the fixation logic"]
    p = _profile(tmp_path, subjects)
    assert _labels(p, subjects) == ["fix: real bug"] * 3


def test_no_convention_leaves_weighting_off(tmp_path):
    subjects = [f"update thing {i}" for i in range(8)]
    p = _profile(tmp_path, subjects)
    assert p.fix_patterns == []
    assert not p.usable
    assert any("no recognizable bug-fix" in c for c in p.cautions)


def test_thin_history_is_flagged(tmp_path):
    p = _profile(tmp_path, ["fix: a", "fix: b", "feat: c"])
    assert any("thin history" in c for c in p.cautions)
    assert not p.usable  # patterns learned, but from too few commits to trust


def test_evidence_reports_guidelines_and_leading_words(tmp_path):
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nCommit messages follow Conventional Commits, e.g. `fix(scope): …`.\n")
    _repo(tmp_path, ["fix: a", "fix: b", "docs: c"])
    ev = gather_evidence(tmp_path)
    assert ev["subjects_sampled"] == 3
    assert ev["leading_words"][0] == {"word": "fix", "count": 2}
    assert ev["guidelines"][0]["file"] == "CONTRIBUTING.md"
    assert any(s["name"] == "conventional" and s["matches"] == 2 for s in ev["candidate_patterns"])


def test_domain_terms_come_from_the_architecture_docs(tmp_path):
    arch = tmp_path / "architecture"
    (arch / "subsystems").mkdir(parents=True)
    (arch / "subsystems" / "billing.md").write_text("# billing\n")
    (arch / "subsystems" / "_TEMPLATE.md").write_text("# template\n")
    (arch / "index.md").write_text("- **Settlement window** — the period a payment can be reversed in\n")
    _repo(tmp_path, ["fix: a"])
    ev = gather_evidence(tmp_path, arch)
    assert "billing" in ev["domain_terms"]
    assert "Settlement window" in ev["domain_terms"]
    assert "_TEMPLATE" not in ev["domain_terms"]


def test_cached_profile_wins_over_inference(tmp_path):
    _repo(tmp_path, ["fix: a", "fix: b"])
    save_profile(tmp_path, HistoryProfile(style="hand-written", fix_patterns=[r"^BUGFIX"],
                                          subjects_sampled=99, source="model"))
    p = history_profile(tmp_path)
    assert p.style == "hand-written" and p.source == "model"
    assert p.matcher().search("BUGFIX: something")
    assert not p.matcher().search("fix: a")


def test_unparsable_cached_pattern_is_dropped(tmp_path):
    save_profile(tmp_path, HistoryProfile(fix_patterns=[r"^fix", r"([unclosed"]))
    assert load_profile(tmp_path).fix_patterns == [r"^fix"]


def test_missing_cache_is_not_an_error(tmp_path):
    assert load_profile(tmp_path) is None


# --- the `archagent history-profile` command ----------------------------------------------

def _run(*args):
    from typer.testing import CliRunner

    from archagent.cli import app

    return CliRunner().invoke(app, ["history-profile", *args])


def test_command_reports_what_it_learned_without_writing(tmp_path):
    _repo(tmp_path, ["fix(router): retry loop", "fix: null deref", "feat: streaming", "docs: readme"])
    result = _run("--project", str(tmp_path))
    assert result.exit_code == 0
    assert "conventional" in result.stdout
    assert "2 of 4 sampled subject(s)" in result.stdout
    assert not (tmp_path / PROFILE_PATH).exists()   # inference only — nothing cached


def test_command_write_caches_the_profile(tmp_path):
    _repo(tmp_path, ["Fixed #1 -- a", "Fixed #2 -- b", "Added a widget"])
    assert _run("--project", str(tmp_path), "--write").exit_code == 0

    cached = load_profile(tmp_path)
    assert cached is not None and cached.fix_matched == 2
    assert cached.matcher().search("Fixed #3 -- c")
    assert not cached.matcher().search("Added a widget")


def test_command_write_reinfers_rather_than_echoing_a_stale_cache(tmp_path):
    _repo(tmp_path, ["fix: a", "fix: b", "feat: c"])
    save_profile(tmp_path, HistoryProfile(style="stale", fix_patterns=[r"^NOPE"]))
    assert _run("--project", str(tmp_path), "--write").exit_code == 0
    assert load_profile(tmp_path).style != "stale"


def test_command_evidence_emits_judgeable_json(tmp_path):
    (tmp_path / "CONTRIBUTING.md").write_text("Commit messages follow Conventional Commits.\n")
    _repo(tmp_path, ["fix: a", "fix: b", "docs: c"])
    result = _run("--project", str(tmp_path), "--evidence")
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["subjects_sampled"] == 3
    assert data["leading_words"][0]["word"] == "fix"
    assert data["guidelines"][0]["file"] == "CONTRIBUTING.md"
    assert any(c["name"] == "conventional" and c["matches"] == 2 for c in data["candidate_patterns"])
    assert "_subjects" not in data   # the raw sample would swamp the useful part


def test_command_reports_cautions_when_nothing_is_learned(tmp_path):
    _repo(tmp_path, [f"update thing {i}" for i in range(5)])
    result = _run("--project", str(tmp_path))
    assert result.exit_code == 0
    assert "caution" in result.stdout


def test_issue_closing_trailers_are_not_fix_labels(tmp_path):
    """Datasette trails `closes #N` on features and docs alike. Because that out-counted its real
    `Fix ...` vocabulary 582 to 353, a widest-first learner picked issue-closing as the repo's notion
    of a fix and reported a 17% fix rate against an actual 10%. Ticket-lifecycle words are not fix
    words — only the fix verbs are."""
    subjects = [f"Add feature {i}, closes #{i}" for i in range(12)]
    subjects += [f"Document thing {i}, resolves #{i}" for i in range(6)]
    subjects += [f"Fix the {i} bug" for i in range(9)]
    p = _profile(tmp_path, subjects)
    labelled = _labels(p, subjects)
    assert all(s.startswith("Fix the") for s in labelled)
    assert len(labelled) == 9


def test_a_genuine_fix_trailer_still_counts(tmp_path):
    subjects = [f"Correct the {i} rounding error (fixes #{i})" for i in range(8)]
    subjects += [f"Add feature {i}" for i in range(8)]
    p = _profile(tmp_path, subjects)
    assert len(_labels(p, subjects)) == 8

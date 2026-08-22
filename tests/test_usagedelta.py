"""Is a release warranted? — the usage-surface diff (issue #14).

The point of the check is to replace a judgement made under pressure with a list, so most of what matters
is *what it declines to count*. Prompt wording changes, new options, renamed internal functions and
reordered decorators must all come back clean, or the check says "release" every week and stops meaning
anything.
"""

import pytest

from usagedelta import Command, commands, compare, prompt_references

_BEFORE = '''
import typer
app = typer.Typer()

@app.command()
def init(project: Path = typer.Argument(...), yes: bool = typer.Option(False, "--yes")) -> None:
    """Scaffold."""

@app.command()
def check(project: Path = typer.Option(Path("."))) -> None:
    """Check."""

@app.command(name="lint-docs")
def lint_docs_cmd(project: Path = typer.Option(Path("."))) -> None:
    """Lint."""
'''


# --- reading the surface ----------------------------------------------------------------------------

def test_commands_are_keyed_by_the_name_a_user_types():
    """`lint_docs_cmd` is not a command anyone can run; `lint-docs` is."""
    cmds = commands(_BEFORE)
    assert set(cmds) == {"init", "check", "lint-docs"}
    assert "lint_docs_cmd" not in cmds


def test_a_required_argument_is_recorded_and_an_option_is_not():
    """Adding a required argument breaks every existing invocation. Adding an option cannot."""
    cmds = commands(_BEFORE)
    assert cmds["init"].required_args == ("project",)
    assert cmds["check"].required_args == ()


def test_a_callback_is_not_a_command():
    """`@app.callback()` is how `--version` was added; counting it would have reported a new command."""
    src = _BEFORE + '''
@app.callback()
def _main(version: bool = typer.Option(False, "--version")) -> None:
    """Root."""
'''
    assert "_main" not in commands(src)


def test_a_module_that_does_not_parse_yields_nothing_rather_than_raising():
    """The `before` side is read out of git and may predate a syntax the current interpreter accepts."""
    assert commands("def broken(:\n") == {}


# --- what warrants a release ------------------------------------------------------------------------

def test_a_new_command_warrants_a_release():
    after = commands(_BEFORE + '''
@app.command()
def graph(project: Path = typer.Option(Path("."))) -> None:
    """Graph."""
''')
    d = compare(commands(_BEFORE), after, {})
    assert d.added == ["graph"] and d.release_warranted


def test_a_removed_command_warrants_a_release():
    after = commands(_BEFORE.replace('@app.command()\ndef check', '@app.command()\ndef _check'))
    d = compare(commands(_BEFORE), after, {})
    assert "check" in d.removed and d.release_warranted


def test_a_rename_reads_as_one_removal_and_one_addition():
    after = commands(_BEFORE.replace('name="lint-docs"', 'name="lint"'))
    d = compare(commands(_BEFORE), after, {})
    assert d.removed == ["lint-docs"] and d.added == ["lint"]


def test_a_new_required_argument_warrants_a_release():
    after = commands(_BEFORE.replace(
        "def check(project: Path = typer.Option(Path(\".\")))",
        "def check(target: Path = typer.Argument(...), project: Path = typer.Option(Path(\".\")))"))
    d = compare(commands(_BEFORE), after, {})
    assert d.args_changed and d.args_changed[0][0] == "check"
    assert d.release_warranted


def test_a_prompt_telling_an_agent_to_run_a_command_the_release_lacks_is_flagged():
    """The failure this exists to prevent: a user installs a release, follows archagent's own
    instructions, and gets command-not-found. It is what happened in calibration round 4, where four
    prompt-referenced commands were missing from the build the reviewer had."""
    after = commands(_BEFORE + '''
@app.command()
def status(project: Path = typer.Option(Path("."))) -> None:
    """Status."""
''')
    refs = prompt_references({"describe.md": "Run `archagent status` to check coverage."})
    d = compare(commands(_BEFORE), after, refs)
    assert ("status", "describe.md") in d.prompt_refs_missing


# --- what must not warrant a release ----------------------------------------------------------------

def test_an_identical_surface_warrants_nothing():
    assert not compare(commands(_BEFORE), commands(_BEFORE), {}).release_warranted


def test_a_new_option_does_not_warrant_a_release():
    """Options are additive: every existing invocation still works."""
    after = commands(_BEFORE.replace(
        'def check(project: Path = typer.Option(Path(".")))',
        'def check(project: Path = typer.Option(Path(".")), deep: bool = typer.Option(False, "--deep"))'))
    assert not compare(commands(_BEFORE), after, {}).release_warranted


def test_renaming_the_python_function_behind_a_named_command_changes_nothing():
    after = commands(_BEFORE.replace("def lint_docs_cmd", "def run_lint_docs"))
    assert not compare(commands(_BEFORE), after, {}).release_warranted


def test_prompt_wording_alone_does_not_warrant_a_release():
    """`archagent upgrade` ships prompt bodies into a repo independently of the package version, so a user
    gets new wording without reinstalling. Counting it would report a release every time a prompt is
    edited — and prompts are edited constantly."""
    refs = prompt_references({"describe.md": "Run `archagent check` carefully, then read the output."})
    assert not compare(commands(_BEFORE), commands(_BEFORE), refs).release_warranted


def test_prose_is_not_read_as_a_command_reference():
    """"archagent will report…" is not an instruction to run anything."""
    refs = prompt_references({"help.md": "archagent will do this, and archagent cannot do that."})
    assert refs == {}, refs


# --- the baseline itself ----------------------------------------------------------------------------

def test_an_untagged_release_is_reported_as_a_bad_baseline(tmp_path, monkeypatch):
    """Written the day `0.3.0` turned out to be on PyPI and never tagged: `git tag` said `v0.2.0` while
    `pyproject.toml` said `0.3.0`, so a delta against the newest tag silently spanned two releases and
    reported surface changes users already had."""
    import usagedelta
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.3.0"\n')
    monkeypatch.setattr(usagedelta, "latest_tag", lambda root: "v0.2.0")
    problem = usagedelta.baseline_problem(tmp_path)
    assert "0.3.0" in problem and "v0.2.0" in problem and "never tagged" in problem


def test_a_matching_tag_and_version_is_a_sound_baseline(tmp_path, monkeypatch):
    import usagedelta
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.3.0"\n')
    monkeypatch.setattr(usagedelta, "latest_tag", lambda root: "v0.3.0")
    assert usagedelta.baseline_problem(tmp_path) == ""


def test_no_tags_at_all_is_reported_rather_than_guessed(tmp_path, monkeypatch):
    import usagedelta
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    monkeypatch.setattr(usagedelta, "latest_tag", lambda root: "")
    assert "no tags" in usagedelta.baseline_problem(tmp_path)


# --- against this repository ------------------------------------------------------------------------

def test_the_real_cli_parses_and_every_shipped_command_is_found():
    """A guard on the extractor rather than on the repo: if `commands` silently returned {} the whole
    check would report 'no release needed' forever."""
    from pathlib import Path as P
    src = (P(__file__).resolve().parents[1] / "src" / "archagent" / "cli.py").read_text()
    cmds = commands(src)
    for expected in ("init", "gen", "check", "drift", "evaluate", "status", "lint-docs", "graph"):
        assert expected in cmds, expected
    assert len(cmds) >= 15

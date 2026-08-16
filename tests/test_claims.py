"""Computed claims — the prototype behind step 1 of `docs/designs/computed-claims.md` §8.

Three things are worth testing and the rest is plumbing: that a command cannot become a shell, that a
predicate fails for the reason it should, and that nothing credential-shaped can be written into a file
that goes into version control.
"""

from pathlib import Path

import pytest

from claims import (Claim, check, judge, leaves_the_root, load, looks_like_a_secret, run,
                    split_pipeline, validate)


def _claim(**kw):
    base = dict(id="C-001", kind="holds", description="d", command="rg -q x .", evidence="")
    return Claim(**{**base, **kw})


# --- a command must not be able to become a shell ---------------------------------------------------

@pytest.mark.parametrize("command", [
    "rg foo . > /tmp/out",
    "rg foo . && rm -rf /",
    "rg foo .; cat /etc/passwd",
    "rg `whoami` .",
    "rg $(whoami) .",
    "python -c 'import os'",
    "sh -c 'anything'",
    "find . -exec rm {} ;",
    "sed -i 's/a/b/' file.txt",
    "curl https://example.com",
    "xargs rm",
    "rg --pre ./evil foo .",
    "git config user.email x@y.z",
])
def test_a_command_that_could_write_or_execute_is_refused(command):
    assert validate(command), f"{command!r} was accepted"


@pytest.mark.parametrize("command", [
    "rg -c pattern src/",
    "git ls-files backend | rg '\\.py$' | wc -l",
    "rg -o '@router\\.(get|post|delete)' api/ | sort | uniq",
    "sed -n '10,20p' file.py | rg foo",
])
def test_an_ordinary_read_only_command_is_accepted(command):
    assert validate(command) == [], validate(command)


def test_a_pipeline_is_split_outside_quotes_only():
    """The bug that showed up on the very first real claim. `rg -o '@router\\.(get|post)'` is one stage,
    not two, and the naive split reported `post` as a disallowed tool. Quote state is the only thing that
    tells a pipeline separator apart from a regex alternation."""
    assert split_pipeline("rg -o '@router\\.(get|post|delete)' api/") == ["rg -o '@router\\.(get|post|delete)' api/"]
    assert len(split_pipeline("git ls-files | rg foo | wc -l")) == 3


def test_a_regex_that_starts_with_a_slash_is_not_a_path():
    """`rg '/add_[a-z_]+\\.py$'` was refused as an absolute path by the first version."""
    assert validate("rg '/add_[a-z_]+\\.py$' migrations/") == []
    assert validate("rg foo /etc/passwd")


def test_a_path_leaving_the_target_root_is_refused():
    assert validate("wc -l ../../../etc/passwd")
    assert validate("cat ~/.aws/credentials")


def test_a_url_prefix_is_not_a_path():
    """`rg -v '/api/validation/'` filters a route list. The first version read the leading slash as an
    absolute path and refused the claim — and it was an `absent` claim about which routes mutate, which is
    the most valuable kind."""
    assert not leaves_the_root("/api/validation/")
    assert leaves_the_root("/etc/passwd") and leaves_the_root("~/.ssh/id_rsa")


# --- predicates fail for the right reason -----------------------------------------------------------

def test_absent_fails_when_something_is_found():
    r = judge(_claim(kind="absent"), "app/x.py:12: match\napp/y.py:3: match")
    assert "expected nothing" in r and "2" in r

def test_absent_passes_on_no_output():
    assert judge(_claim(kind="absent"), "") == ""

def test_holds_fails_when_nothing_is_found():
    assert "expected a match" in judge(_claim(kind="holds"), "   \n ")

def test_holds_does_not_compare_its_evidence(_=None):
    """The property that keeps this from crying wolf: a `holds` claim records what it saw so a reviewer can
    tell whether the command measured the right thing, but a line number moving must not be a divergence."""
    c = _claim(kind="holds", evidence="config.py:124:    raise RuntimeError(...)")
    assert judge(c, "config.py:131:    raise RuntimeError(...)") == ""

def test_a_set_names_what_moved_in_each_direction():
    c = _claim(kind="set", evidence="processing, ready, error, archived")
    why = judge(c, "processing\nready\nerror\narchived\nqueued")
    assert "not in the artifact: queued" in why
    why = judge(c, "processing\nready\nerror")
    assert "in the artifact but not in the code: archived" in why

def test_a_set_ignores_order_and_blank_lines():
    c = _claim(kind="set", evidence="b, a")
    assert judge(c, "a\n\nb\n") == ""


# --- nothing credential-shaped gets recorded --------------------------------------------------------

@pytest.mark.parametrize("output", [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "sk-abcdefghijklmnopqrstuvwx",
    "-----BEGIN RSA PRIVATE KEY-----",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
    "SECRET_KEY = supersecretvalue123",
    "api_key: abcdefgh12345678",
    "d41d8cd98f00b204e9800998ecf8427ed41d8cd9",
])
def test_credential_shaped_output_is_refused(output):
    assert looks_like_a_secret(output), f"{output!r} was accepted"


@pytest.mark.parametrize("output", [
    "processing\nready\nerror\narchived",
    "backend/migrations/versions/17e405de9371_add_pairing_source_to_outfits.py",
    "frontend/app/api/v1/[...path]/route.ts",
    "19",
    "config.py:124:    raise RuntimeError('SECRET_KEY must be set')",
])
def test_ordinary_output_is_not_mistaken_for_a_secret(output):
    """A false positive costs a rewritten command, so the scan is allowed to be crude — but not so crude
    that a hashed migration filename or a line mentioning `SECRET_KEY` in prose refuses to record."""
    assert looks_like_a_secret(output) == [], looks_like_a_secret(output)


def test_the_refusal_does_not_echo_what_it_refused(tmp_path):
    """The error message is written into a results file. A message quoting the output it declined to
    record would record it."""
    (tmp_path / "f.txt").write_text("ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")
    out, err = run("cat f.txt", tmp_path)
    assert out is None and "GitHub token" in err
    assert "ghp_" not in err


# --- execution --------------------------------------------------------------------------------------

def test_a_pipeline_runs_without_a_shell(tmp_path):
    (tmp_path / "a.py").write_text("x\ny\n")
    (tmp_path / "b.txt").write_text("z\n")
    out, err = run("ls | rg '\\.py$' | wc -l", tmp_path)
    assert err is None and out == "1"

def test_a_command_finding_nothing_is_an_answer_not_an_error(tmp_path):
    """`rg` exits 1 when it matches nothing, and for an `absent` claim that is precisely the passing
    case. Treating a non-zero exit as a failure would make every `absent` claim unrunnable."""
    (tmp_path / "a.py").write_text("x\n")
    out, err = run("rg nothinghere .", tmp_path)
    assert err is None and out == ""

def test_an_oversized_output_is_refused_where_it_would_be_recorded(tmp_path):
    """The cap belongs to recording, not to running. Applying it in `run` made every broad `absent` claim
    unrunnable — the kind the redesign leans on most — because an `absent` claim needs only to know
    whether the output was empty, and a failing one legitimately produces a lot of it."""
    (tmp_path / "big.txt").write_text("word " * 500)
    (r_set,) = check([_claim(kind="set", command="cat big.txt")], tmp_path)
    assert r_set.observed is None and "exceeds" in r_set.error

    (r_absent,) = check([_claim(kind="absent", command="cat big.txt")], tmp_path)
    assert r_absent.error is None and "expected nothing" in r_absent.why

def test_the_environment_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_SECRET_TOKEN", "hunter2hunter2")
    (tmp_path / "f.txt").write_text("nothing\n")
    out, err = run("cat f.txt", tmp_path)
    assert err is None and "hunter2" not in (out or "")


# --- the table --------------------------------------------------------------------------------------

def test_a_claims_table_round_trips(tmp_path):
    f = tmp_path / "claims.md"
    f.write_text(
        "| id | kind | claim | command | evidence | asserted in |\n"
        "|----|------|-------|---------|----------|-------------|\n"
        "| C-001 | set | item states | `rg -o 'x' m.py \\| sort` | a, b | domain.md:14 |\n")
    (c,) = load(f)
    assert c.kind == "set" and c.members() == {"a", "b"}
    assert c.command == "rg -o 'x' m.py | sort"      # the escaped pipe is a pipeline, not a cell break
    assert c.source == "domain.md:14"

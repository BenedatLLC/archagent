"""Has the documented usage surface changed since the last release? (issue #14)

A release should not be required before every evaluation — usage should not change that fast, and if it
does that is the bigger problem. But a release *is* warranted when what a user is told to do has changed,
and "significantly" needs to be a number rather than a judgement made under pressure.

**The usage surface is three things**, and nothing else counts:

1. the commands `cli.py` registers — added, removed or renamed;
2. their **required** arguments, since adding one breaks every existing invocation;
3. the commands the phase prompts tell an agent to run, which must exist in the release a user installs.

Prompt *wording* changes deliberately do not trigger a release: `archagent upgrade` ships prompt bodies
into a repo independently of the package version, so a user gets them without reinstalling.

**Why the baseline needs checking too.** This was written the day after `0.3.0` turned out to be published
to PyPI and never tagged — `git tag` showed `v0.2.0` as newest while `pyproject.toml` said `0.3.0`. A
delta computed against "the last tag" would have compared two releases' worth of change and reported a
surface change that had already shipped. `baseline_problem` catches exactly that, and it is the reason
this module reports on its own inputs before reporting on the diff.
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Command:
    name: str
    required_args: tuple[str, ...] = ()

    def signature(self) -> str:
        return f"{self.name}({', '.join(self.required_args)})" if self.required_args else self.name


@dataclass
class Delta:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    args_changed: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = field(default_factory=list)
    prompt_refs_missing: list[tuple[str, str]] = field(default_factory=list)   # (command, prompt file)

    @property
    def release_warranted(self) -> bool:
        return bool(self.added or self.removed or self.args_changed or self.prompt_refs_missing)


def _is_command_decorator(dec: ast.expr) -> ast.Call | None:
    """`@app.command()` or `@app.command(name="x")`, and not `@app.callback()`."""
    if isinstance(dec, ast.Call):
        f = dec.func
        if isinstance(f, ast.Attribute) and f.attr == "command":
            return dec
    elif isinstance(dec, ast.Attribute) and dec.attr == "command":
        return None      # bare `@app.command` — no call, so no name kwarg
    return None


def _required_args(fn: ast.FunctionDef) -> tuple[str, ...]:
    """Parameters a user must supply.

    A `typer.Argument(...)` whose first positional is `...` is required; so is a bare parameter with no
    default at all. Everything given a concrete default — including every `typer.Option` — is optional and
    cannot break an existing invocation by changing.
    """
    args = fn.args.args
    defaults = list(fn.args.defaults)
    pad = len(args) - len(defaults)
    out = []
    for i, a in enumerate(args):
        if i < pad:                                   # no default at all
            out.append(a.arg)
            continue
        d = defaults[i - pad]
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == "Argument" and d.args
                and isinstance(d.args[0], ast.Constant) and d.args[0].value is Ellipsis):
            out.append(a.arg)
    return tuple(out)


def commands(cli_source: str) -> dict[str, Command]:
    """The commands a CLI module registers, keyed by the name a user types."""
    try:
        tree = ast.parse(cli_source)
    except SyntaxError:
        return {}
    out: dict[str, Command] = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for dec in fn.decorator_list:
            call = _is_command_decorator(dec)
            if call is None and not (isinstance(dec, ast.Attribute) and dec.attr == "command"):
                continue
            name = fn.name
            if call is not None:
                for kw in call.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        name = kw.value.value
            out[name] = Command(name=name, required_args=_required_args(fn))
            break
    return out


#: A backtick-quoted `archagent <command>` is an instruction to run something; bare prose is not. The
#: phase prompts are consistent about this — every real reference is fenced, and the unfenced cases are
#: all "archagent can", "archagent cannot", "archagent works". Without the backtick, "archagent will do
#: this" registers `will` as a command.
_PROMPT_REF = re.compile(r"`archagent\s+([a-z][a-z-]{1,20})\b")


def prompt_references(prompt_texts: dict[str, str]) -> dict[str, set[str]]:
    """`{command: {prompt files that tell an agent to run it}}`."""
    out: dict[str, set[str]] = {}
    for name, text in prompt_texts.items():
        for m in _PROMPT_REF.finditer(text):
            out.setdefault(m.group(1), set()).add(name)
    return out


def compare(before: dict[str, Command], after: dict[str, Command],
            refs: dict[str, set[str]]) -> Delta:
    d = Delta()
    d.added = sorted(set(after) - set(before))
    d.removed = sorted(set(before) - set(after))
    for name in sorted(set(before) & set(after)):
        if before[name].required_args != after[name].required_args:
            d.args_changed.append((name, before[name].required_args, after[name].required_args))
    # A prompt telling an agent to run a command the *released* build does not have is the failure this
    # exists to prevent: the user installs a release, follows archagent's own instructions, and gets
    # command-not-found.
    for cmd, files in sorted(refs.items()):
        if cmd in after and cmd not in before:
            for f in sorted(files):
                d.prompt_refs_missing.append((cmd, f))
    return d


# --- reading a ref out of git ------------------------------------------------------------------------

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout


def latest_tag(root: Path) -> str:
    tags = [t for t in _git(root, "tag", "--sort=-v:refname").split() if t.strip()]
    return tags[0] if tags else ""


def declared_version(root: Path) -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(), re.MULTILINE)
    return m.group(1) if m else ""


def baseline_problem(root: Path) -> str:
    """Why the baseline may be wrong, or "" if it looks sound.

    The check that would have caught `0.3.0` shipping untagged: comparing against the newest tag then
    silently spans two releases, and the delta reports surface changes users already have.
    """
    tag, version = latest_tag(root), declared_version(root)
    if not tag:
        return "no tags in this repository — pass --since <ref> explicitly"
    if version and tag.lstrip("v") != version:
        return (f"pyproject declares {version} but the newest tag is {tag}. If {version} was released, it "
                f"was never tagged, and a delta against {tag} spans more than one release. Tag the "
                f"release commit, or pass --since <ref>.")
    return ""


def at_ref(root: Path, ref: str, path: str) -> str:
    return _git(root, "show", f"{ref}:{path}")


def phase_prompts(root: Path, ref: str | None = None) -> dict[str, str]:
    rel = "src/archagent/templates/agent/phases"
    if ref is None:
        return {p.name: p.read_text() for p in sorted((root / rel).glob("*.md"))}
    names = [n for n in _git(root, "ls-tree", "--name-only", f"{ref}:{rel}").split() if n.endswith(".md")]
    return {n: at_ref(root, ref, f"{rel}/{n}") for n in names}

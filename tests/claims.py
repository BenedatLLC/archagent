"""Computed claims — prototype for step 1 of the evaluation (`docs/designs/computed-claims.md` §8).

Lives in `tests/` rather than `src/` on purpose: the design is **proposed, not accepted**, and this exists
to measure whether it is worth accepting. If step 1 lands where it predicts, this moves into the package.

Two halves, matching the design:

- **Static validation** (§5.4) — parse the command into pipeline stages and refuse anything outside a
  small allowlist of read-only tools, or any flag on that list which can write or execute. This runs
  whether or not anything is going to be executed, because it is what makes an unsafe command visible in
  review.
- **Execution without a shell** — each stage is `shlex.split` and run with `shell=False`, wired together
  with pipes. Redirects, command substitution, chaining and globbing are not blocked so much as
  *unrepresentable*: nothing ever interprets them, so a command containing them fails to parse.

The recorded value is what the **artifact asserts**. A divergence therefore means the documents and the
code disagree — which for step 1, run against artifacts nobody has repaired, is the measurement.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# --- what may run -----------------------------------------------------------------------------------

#: Read-only source analysis only. `git` is restricted further below.
ALLOWED = {
    "rg", "grep", "ast-grep", "sg", "find", "ls", "wc", "sort", "uniq", "head", "tail",
    "cut", "tr", "awk", "sed", "jq", "cat", "basename", "dirname", "git", "xargs-none",
}

GIT_SUBCOMMANDS = {"log", "ls-files", "grep", "show", "rev-parse", "rev-list"}

#: Flags and script constructs that make an otherwise read-only tool write or execute.
FORBIDDEN_FLAGS = {
    "find": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprintf", "-fls", "-fprint"},
    "sed": {"-i", "--in-place"},
    "rg": {"--pre", "--pre-glob", "--hostname-bin", "-z", "--search-zip"},
    "grep": {"-Z"},
}

#: Anything here anywhere in a stage is refused outright.
FORBIDDEN_ANYWHERE = re.compile(
    r"system\s*\(|`|\$\(|>\s*\S|>>|<<|;|&&|&\s*$|\bsudo\b|\bxargs\b|\benv\b")

#: Paths that must never appear in a command, because their contents are secrets.
SECRET_PATHS = re.compile(
    r"(^|/)\.env|\.pem\b|\.key\b|id_rsa|\.npmrc|\.netrc|\.git-credentials|(^|/)\.aws(/|$)"
    r"|(^|/)\.ssh(/|$)|credential|secret|token|password", re.IGNORECASE)

MAX_VALUE_CHARS = 400
TIMEOUT_SECONDS = 30

#: An argument is a path for the purposes of the escaping check only if it looks like one. Splitting on
#: this mattered immediately: `rg '/add_[a-z_]+\.py$' ...` is a regex that starts with `/`, and the first
#: version refused it as an absolute path.
_REGEX_METACHARS = set("[]()*+?^$\\")


def split_pipeline(command: str) -> list[str]:
    r"""Split on `|` **outside quotes**.

    A naive `command.split("|")` looked obviously right and is wrong on the most common shape a claim
    command takes: `rg -o '@router\.(get|post|delete)'` is one stage, not three, and the first version
    reported `post` and `delete` as disallowed tools. Quote state is the whole difference between a
    pipeline separator and a regex alternation, and nothing else can tell them apart.
    """
    stages, buf, quote = [], [], None
    for ch in command:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\'\"":
            quote = ch
            buf.append(ch)
        elif ch == "|":
            stages.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    stages.append("".join(buf))
    return stages


@dataclass(frozen=True)
class Claim:
    id: str
    description: str
    command: str
    value: str                       # what the artifact asserts
    source: str = ""                 # where in the artifact the assertion appears


@dataclass
class Result:
    claim: Claim
    observed: str | None = None
    error: str | None = None         # command failed, or was refused before running

    @property
    def diverged(self) -> bool:
        return self.error is None and _norm(self.observed) != _norm(self.claim.value)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.diverged


def _norm(v: str | None) -> str:
    """Compare on content, not on whitespace or backticks. A claim written `19` and a command printing
    `19\\n` are the same claim, and treating them as a divergence would make the tool cry wolf (§5.3)."""
    return re.sub(r"\s+", " ", (v or "").replace("`", "").strip())


# --- static validation ------------------------------------------------------------------------------

def validate(command: str) -> list[str]:
    """Reasons this command must not run. Empty means it is acceptable."""
    bad: list[str] = []
    if FORBIDDEN_ANYWHERE.search(command):
        bad.append("contains shell metacharacters, substitution, redirection or an executing tool")
    if SECRET_PATHS.search(command):
        bad.append("names a path or word associated with secrets")
    for stage in split_pipeline(command):
        stage = stage.strip()
        if not stage:
            bad.append("empty pipeline stage")
            continue
        try:
            argv = shlex.split(stage)
        except ValueError as e:
            bad.append(f"does not parse: {e}")
            continue
        if not argv:
            bad.append("empty pipeline stage")
            continue
        prog = os.path.basename(argv[0])
        if prog not in ALLOWED:
            bad.append(f"{prog!r} is not an allowed tool")
            continue
        if prog == "git":
            sub = next((a for a in argv[1:] if not a.startswith("-")), "")
            if sub not in GIT_SUBCOMMANDS:
                bad.append(f"git subcommand {sub!r} is not allowed")
        for flag in FORBIDDEN_FLAGS.get(prog, ()):
            if flag in argv:
                bad.append(f"{prog} {flag} can write or execute")
        if prog == "awk" and any(re.search(r"print\s*>|printf\s*>|close\s*\(", a) for a in argv[1:]):
            bad.append("awk script writes to a file")
        if prog == "sed" and any(re.search(r"(^|;)\s*[wW]\s", a) for a in argv[1:]):
            bad.append("sed script writes to a file")
        for a in argv[1:]:
            if set(a) & _REGEX_METACHARS:      # a pattern, not a path
                continue
            if a.startswith("/") or a.startswith("~") or ".." in Path(a).parts:
                bad.append(f"path {a!r} may leave the target root")
    return bad


# --- execution --------------------------------------------------------------------------------------

def _env() -> dict[str, str]:
    """Almost nothing. A command cannot print a token it cannot see, and CI environments are full of
    tokens. `PATH` is kept so the tools resolve; `LC_ALL` so sort order is stable (§5.3)."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "LANG": "C",
            "NO_COLOR": "1", "TERM": "dumb"}


def run(command: str, root: Path) -> tuple[str | None, str | None]:
    """`(output, error)`. Never raises for an ordinary command failure — that is a result, not a crash."""
    bad = validate(command)
    if bad:
        return None, "refused: " + "; ".join(bad)
    stages = [shlex.split(s.strip()) for s in split_pipeline(command)]
    procs: list[subprocess.Popen] = []
    try:
        prev = None
        for i, argv in enumerate(stages):
            p = subprocess.Popen(
                argv, cwd=root, env=_env(),
                stdin=prev.stdout if prev is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if prev is not None:
                prev.stdout.close()          # let the upstream stage see EPIPE
            procs.append(p)
            prev = p
        out, err = procs[-1].communicate(timeout=TIMEOUT_SECONDS)
    except FileNotFoundError as e:
        return None, f"tool not found: {e.filename}"
    except subprocess.TimeoutExpired:
        for p in procs:
            p.kill()
        return None, f"timed out after {TIMEOUT_SECONDS}s"
    finally:
        for p in procs[:-1]:
            p.wait(timeout=5)
    if procs[-1].returncode not in (0, 1):   # 1 is "no matches" for rg/grep, which is a real answer
        return None, (err or "").strip().splitlines()[-1][:120] if err else \
            f"exit {procs[-1].returncode}"
    out = out.strip()
    if len(out) > MAX_VALUE_CHARS:
        return None, f"output exceeds {MAX_VALUE_CHARS} characters ({len(out)}) — narrow the command"
    return out, None


# --- the claims file --------------------------------------------------------------------------------

_ROW = re.compile(r"^\|\s*(C-\d+)\s*\|(.*)\|\s*$")


def load(path: Path) -> list[Claim]:
    """Read the Markdown table. Pipes inside a cell are escaped `\\|`, as they must be in Markdown."""
    claims = []
    for line in path.read_text().splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", m.group(2))]
        cells = [c.replace("\\|", "|") for c in cells]
        desc, command, value = cells[0], cells[1].strip("`"), cells[2]
        source = cells[3] if len(cells) > 3 else ""
        claims.append(Claim(id=m.group(1), description=desc, command=command,
                            value=value.strip("`"), source=source))
    return claims


def check(claims: list[Claim], root: Path) -> list[Result]:
    out = []
    for c in claims:
        observed, error = run(c.command, root)
        out.append(Result(claim=c, observed=observed, error=error))
    return out


@dataclass
class Summary:
    total: int = 0
    agreed: int = 0
    diverged: list[Result] = field(default_factory=list)
    errored: list[Result] = field(default_factory=list)

    @classmethod
    def of(cls, results: list[Result]) -> "Summary":
        s = cls(total=len(results))
        for r in results:
            if r.error:
                s.errored.append(r)
            elif r.diverged:
                s.diverged.append(r)
            else:
                s.agreed += 1
        return s

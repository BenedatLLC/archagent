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

**A claim is a predicate, not a number.** The first version recorded a value and checked that the value
still held, and step 1 measured what that reaches: 8 of a predicted 17 defects, because most fabricated
claims are not numbers. It also invited exactly the wrong kind of claim. *"Foo is called in ten places"*
being wrong by two changes nothing a reader would do; the documentation should carry statements that mean
something, not trivia about the code.

So there is no "this number is 19" kind. There are three kinds, and each is chosen because its falsity
changes what a reader would do:

- **`absent`** — the command must find nothing. *There is no local-auth mode. Nothing outside `cmd`
  constructs a service.* The strongest kind, because these are the claims artifacts get wrong.
- **`holds`** — the command must find something. Its output is recorded as evidence and **not compared**,
  so a line number moving is not a false alarm.
- **`set`** — the members are exactly these. Used where completeness *is* the meaning: the members of an
  enum, the routes that change state, the modes a function can return. A count is expressed as a set of
  names, never as a total, so what fires is "a fifth status appeared", not "the number moved".

The recorded evidence is what the **artifact asserts**. A divergence therefore means the documents and the
code disagree — which, run against artifacts nobody has repaired, is the measurement.
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


#: Top-level directories that actually exist on a POSIX system. An absolute argument is only a path if it
#: starts with one of these — `/api/validation/` is a URL prefix being matched, not a file, and the first
#: version refused it. Checking for existence rather than for a leading slash is what tells them apart.
_REAL_ROOTS = frozenset({"etc", "usr", "var", "home", "root", "bin", "sbin", "opt", "tmp", "dev",
                         "proc", "sys", "private", "Users", "Library", "Applications", "System",
                         "Volumes", "mnt", "media", "srv", "run"})


def leaves_the_root(arg: str) -> bool:
    if arg.startswith("~") or ".." in Path(arg).parts:
        return True
    parts = Path(arg).parts
    return arg.startswith("/") and len(parts) > 1 and parts[1] in _REAL_ROOTS


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


#: The three kinds of claim. There is deliberately no "this number is 19" kind — see the module docstring.
KINDS = ("holds", "absent", "set")


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str                        # holds | absent | set
    description: str
    command: str
    evidence: str = ""               # `set`: the members, comma-separated. `holds`: output, kept unchecked.
    source: str = ""                 # where in the artifact the assertion appears

    def members(self) -> set[str]:
        return {m.strip() for m in self.evidence.split(",") if m.strip()}


@dataclass
class Result:
    claim: Claim
    observed: str | None = None
    error: str | None = None         # command failed, refused, or its output looked like a secret
    why: str = ""                    # how it diverged, in the reader's terms

    @property
    def diverged(self) -> bool:
        return self.error is None and bool(self.why)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.why


def _lines(v: str | None) -> set[str]:
    return {ln.strip() for ln in (v or "").splitlines() if ln.strip()}


def judge(claim: Claim, observed: str) -> str:
    """How this claim failed, or "" if it holds.

    The three kinds differ in what they compare, and the difference is the point of the redesign:

    - **`absent`** — the command must find nothing. This is the strongest kind, because it is how a claim
      of the form *there is no local-auth mode* or *nothing outside `cmd` constructs a service* is stated,
      and those are the claims artifacts get wrong.
    - **`holds`** — the command must find something. Its output is recorded as evidence and **not
      compared**, so a line number moving does not raise a false alarm (§5.3). What is checked is that the
      thing is still there at all.
    - **`set`** — the members must be exactly these. Used where completeness is the meaning: the members
      of an enum, the routes that change state, the modes a function can return.
    """
    if claim.kind == "absent":
        return "" if not observed.strip() else f"expected nothing; found {len(_lines(observed))} match(es)"
    if claim.kind == "holds":
        return "" if observed.strip() else "expected a match; found none"
    if claim.kind == "set":
        want, got = claim.members(), _lines(observed)
        if want == got:
            return ""
        missing, extra = sorted(want - got), sorted(got - want)
        parts = []
        if extra:
            parts.append("not in the artifact: " + ", ".join(extra))
        if missing:
            parts.append("in the artifact but not in the code: " + ", ".join(missing))
        return "; ".join(parts)
    return f"unknown claim kind {claim.kind!r}"


# --- keeping secrets out of the recorded evidence ---------------------------------------------------

#: Shapes that must never be written into a file that goes into version control. Deliberately crude and
#: deliberately conservative: the cost of a false positive is rewriting one command, and the cost of a
#: false negative is a credential in git history.
_SECRET_SHAPES = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key block"),
    (re.compile(r"\b(sk|rk|pk)-[A-Za-z0-9]{16,}"), "an API-key prefix"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "a GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "a GitHub fine-grained token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "a Google API key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "a JWT"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "a long hex string"),
    # `[\w-]*` after the word: the name is usually `SECRET_KEY` or `api_token_value`, not the bare word,
    # and the first version matched neither.
    (re.compile(r"(?i)\b(secret|password|passwd|token|api[_-]?key|credential)[\w-]*\s*[:=]\s*\S{8,}"),
     "an assignment to a secret-looking name"),
]


def looks_like_a_secret(text: str) -> list[str]:
    """Reasons this output must not be recorded.

    A claim command is not supposed to read a credential, and §5.4 already refuses commands that name
    secret-bearing paths. This is the second line: the path check works on what the command *says*, and
    this works on what it *produced*. Refuse rather than truncate — truncating stores a partial secret and
    reports success.
    """
    found = [why for rx, why in _SECRET_SHAPES if rx.search(text)]
    for token in re.findall(r"[A-Za-z0-9+/=_-]{32,}", text):
        if _entropy(token) > 4.0 and why_not_a_path(token):
            found.append("a long high-entropy string")
            break
    return found


def why_not_a_path(token: str) -> bool:
    """A long random-looking run that is plainly a file path or an identifier is not a secret. Without
    this, any command listing hashed migration filenames refuses to record."""
    return not (("/" in token) or ("." in token) or ("_" in token and token.islower()))


def _entropy(s: str) -> float:
    from collections import Counter
    from math import log2
    n = len(s)
    return -sum((c / n) * log2(c / n) for c in Counter(s).values()) if n else 0.0


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
            if leaves_the_root(a):
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
    leak = looks_like_a_secret(out)
    if leak:
        # Never return the output alongside the complaint: the caller writes results into a file, and a
        # message quoting what it refused to record would record it.
        return None, ("output looks like it contains " + ", ".join(leak)
                      + " — refusing to record it; rewrite the command to count or name, not to print")
    return out, None


# --- the claims file --------------------------------------------------------------------------------

_ROW = re.compile(r"^\|\s*(C-\d+)\s*\|(.*)\|\s*$")


def load(path: Path) -> list[Claim]:
    """Read the Markdown table: `| id | kind | claim | command | evidence | asserted in |`.

    Pipes inside a cell are escaped `\\|`, as they must be in Markdown.
    """
    claims = []
    for line in path.read_text().splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", m.group(2))]
        cells = [c.replace("\\|", "|").strip("`") for c in cells]
        while len(cells) < 5:
            cells.append("")
        claims.append(Claim(id=m.group(1), kind=cells[0].lower(), description=cells[1],
                            command=cells[2], evidence=cells[3], source=cells[4]))
    return claims


def check(claims: list[Claim], root: Path) -> list[Result]:
    out = []
    for c in claims:
        observed, error = run(c.command, root)
        if error is None and c.kind != "absent" and len(observed) > MAX_VALUE_CHARS:
            # The cap exists to stop a runaway command committing a megabyte of output. It has to apply
            # where the output is *recorded*, not where it is run: an `absent` claim records nothing when
            # it passes and needs only a count when it fails, and capping at run time made every broad
            # `absent` claim unrunnable — the kind the redesign leans on most.
            error = f"output exceeds {MAX_VALUE_CHARS} characters ({len(observed)}) — narrow the command"
            observed = None
        why = "" if error is not None else judge(c, observed or "")
        out.append(Result(claim=c, observed=observed, error=error, why=why))
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

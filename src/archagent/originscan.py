"""Permissive cross-origin policy — who, besides the intended client, may call this service.

A locally-bound service is not an unreachable one. Any page a developer browses can issue cross-origin
requests to `127.0.0.1`, so a wide-open origin policy on a local tool means every site they visit can read
whatever that tool serves and call whatever routes it exposes. That is a trust boundary, and an
architecture document that says "local by default" without saying it is describing the deployment and
skipping the boundary.

**This scanner reads every code file, not only the configured languages.** Every other extractor is bound
to `languages` in `archagent.toml` because it needs a real parser — an import graph, a route table. This
one is a literal search for a handful of spellings, which works the same in any language. The finding that
prompted it was in Go, which archagent does not analyse: a tool that could not see the one case it was
built for would be worth nothing. The cost is that the patterns are textual and can be fooled; the
`confidence` field says so per kind.

**Evidence class: `single-instance` + `mechanism`** (design §18). One repository motivated this check and
one other has ever produced a hit, and twelve of fourteen corpus repositories contain no HTTP server at
all, so the corpus cannot yet say much about its false-positive rate. What justifies it is mechanism
rather than instance count: a wildcard or reflected origin is a web-platform behaviour with known
consequences, not one project's quirk. Confidence is set accordingly — never `high` on the textual
route evidence alone.

**A permissive origin is not automatically a defect** (issue #8). A public read-only API may want one. The
question is what else is reachable, which `evaluate` decides by checking whether the service also exposes a
state-changing route — so this module reports facts and rates nothing.

## What a line-based scan cannot see, measured rather than assumed

Probed against constructed cases; these are the known edges, not a guess at them.

*Missed (false negatives).* A policy assembled indirectly — `origin := "*"` on one line and the header set
from the variable on the next — is invisible; so is a value split across lines, e.g. `allow_origins=[`
newline `"*"`. Both need dataflow or a parser. The consequence is a quiet under-report, which is the
tolerable direction: the signal is a floor on exposure, never a clearance.

*Reported when it may be fine (false positive).* A wildcard inside `if devMode { … }` is reported exactly
like an unconditional one, because nothing here reads control flow. This is the most likely reason a
reader will dismiss a finding, and the `evaluate` prompt says so.

*Deliberately not attempted.* Whether the origin is *effectively* restricted by something upstream — a
reverse proxy, an auth middleware, a firewall — is invisible to any static scan of this repository. That is
part of why the finding is framed as "the artifact does not describe this boundary" rather than "this is
insecure".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".rb", ".kt")
_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv", ".mypy_cache", "dist", "build"}
_COMMENT_STARTS = ("#", "//", "*", "/*", "--")

#: (kind, pattern, confidence, what it means)
_PATTERNS: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    # The header itself, however it is spelled: Go's w.Header().Set(...), JS res.setHeader(...),
    # Python response.headers[...] = ... . Matching the header name plus a literal star covers all three.
    ("acao-wildcard",
     re.compile(r"""Access-Control-Allow-Origin["']?\s*[,:=\]]\s*["']\*["']""", re.IGNORECASE),
     "high", "Access-Control-Allow-Origin is set to `*`"),
    # Reflecting the request's own Origin back is *more* permissive than `*`, not less: a wildcard is
    # rejected by browsers when credentials are sent, so reflection is the form that actually allows a
    # cross-origin read of an authenticated response. It is the dangerous spelling and it does not
    # contain a star, so a wildcard-only scanner sees nothing.
    ("acao-reflects-request",
     re.compile(r"""Access-Control-Allow-Origin["']?\s*[,:=\]]\s*[^\n]*?"""
                r"""(?:\.origin\b|\[["']Origin["']\]|\(["']Origin["']\))""", re.IGNORECASE),
     "high", "Access-Control-Allow-Origin echoes the request's own Origin"),
    # gorilla/websocket: the upgrader's origin check replaced with an unconditional true. The default
    # (absent CheckOrigin) is same-origin, so this is an explicit opt-out.
    ("ws-checkorigin-true",
     re.compile(r"CheckOrigin\s*:\s*func\s*\([^)]*\)\s*bool\s*\{\s*return\s+true"),
     "high", "the WebSocket upgrader accepts every Origin"),
    # FastAPI / Starlette CORSMiddleware
    ("allow-origins-wildcard",
     re.compile(r"""allow_origins\s*=\s*[\[(][^\])]*["']\*["']"""),
     "high", "CORS middleware allows every origin"),
    # Express / Fastify / Nest: cors({ origin: "*" })
    ("cors-origin-wildcard",
     re.compile(r"""origin\s*:\s*["']\*["']"""),
     "med", "a CORS `origin` option is `*`"),
    # `app.use(cors())` with no options is permissive by default, and reads as if it were a restriction.
    ("cors-default-open",
     re.compile(r"\buse\s*\(\s*cors\s*\(\s*\)\s*\)"),
     "med", "`cors()` with no options allows every origin"),
    # flask_cors: CORS(app) with no `origins=` is send-wildcard by default
    ("flask-cors-default-open",
     re.compile(r"\bCORS\s*\(\s*app\s*\)"),
     "med", "`CORS(app)` with no `origins` allows every origin"),
)


@dataclass(frozen=True)
class Origin:
    file: str            # repo-relative
    line: int
    kind: str
    detail: str
    confidence: str

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line}"


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(_COMMENT_STARTS)


def scan(root: Path, skip_tests: bool = True) -> list[Origin]:
    """Every permissive-origin site in the tree, in path order.

    `skip_tests` drops the usual test locations: a fixture server opening its origin says nothing about
    the deployed policy, and reporting it trains a reader to ignore this signal.
    """
    out: list[Origin] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in CODE_EXTS:
            continue
        parts = set(path.parts)
        if _SKIP_DIRS & parts:
            continue
        if skip_tests and (parts & {"test", "tests", "__tests__", "testdata", "fixtures", "examples"}
                           or re.search(r"(^|[._-])(test|spec)s?[._]", path.name)):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            if _is_comment(line):
                continue
            for kind, pattern, confidence, detail in _PATTERNS:
                if pattern.search(line):
                    out.append(Origin(rel, lineno, kind, detail, confidence))
                    break
    return out


#: A state-changing route *registration*, restricted to what a literal search can identify without a
#: parser: a method-prefixed path passed to a handler-registration call, as Go 1.22's `net/http` mux
#: takes it — `mux.HandleFunc("DELETE /api/data", …)`.
#:
#: Deliberately only this form. Earlier attempts also matched `router.delete("/x")` and a bare quoted
#: `"DELETE /path"`; the first is indistinguishable from a *client* call to that route, and the second
#: matched `placeholder: "POST /charge"` — the hint text of a UI search box. Both would have raised a
#: finding's severity on evidence that was not a route at all. Python and JS/TS are covered by
#: `webapi.extract_routes`, which actually parses them, so nothing is lost by leaving their spellings out.
_MUTATING = (
    re.compile(r"""\b(?:HandleFunc|Handle|Route|Method)\s*\(\s*["'`](?:POST|PUT|PATCH|DELETE)\s+/"""),
)


def mutating_routes(root: Path, under: tuple[str, ...] = (), skip_tests: bool = True) -> list[str]:
    """`path:line` for each route that appears to change state, in any language.

    `under` restricts the search to path prefixes. The caller passes the components that set the
    permissive header, because the question is not "does this repository contain a DELETE route" but
    "is a DELETE route reachable *behind this policy*" — a fixture app under `evals/` answers neither.

    `webapi.extract_routes` is the real route extractor and is bound to the configured languages. This
    exists because the origin signal's severity turns on "is a state-changing route reachable", and the
    case it was built for is a Go service — where the proper extractor sees nothing and the finding would
    be rated as read-only exposure. A literal scan is weaker evidence than a parse, so it is used only to
    *raise* severity, never to lower it.
    """
    out: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in CODE_EXTS:
            continue
        parts = set(path.parts)
        if _SKIP_DIRS & parts:
            continue
        if skip_tests and (parts & {"test", "tests", "__tests__", "testdata", "fixtures", "examples"}
                           or re.search(r"(^|[._-])(test|spec)s?[._]", path.name)):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        if under and not rel.startswith(under):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _is_comment(line):
                continue
            if any(p.search(line) for p in _MUTATING):
                out.append(f"{rel}:{lineno}")
    return out

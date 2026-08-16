"""A server-side fetch of a URL the caller supplied (issue #12).

A route that takes a URL from the request and fetches it runs with the *server's* network position. A
caller can then reach what the server can reach and their browser cannot — cloud metadata endpoints,
internal admin ports, services bound to localhost. That is the SSRF shape.

**This reports two facts and not a verdict.** "A URL derived from request input reaches an outbound HTTP
call" is checkable from the source. "This is exploitable" depends on what network the service runs in,
which archagent cannot see, and on whether the fetch is a feature — a webhook tester, a feed reader, an
add-by-URL import all do exactly this on purpose. So the finding is *is the boundary described, and is
there an allow-list*, never *remove this*.

**Why the confidence is low by construction.** The taint is followed within a single function only. That
catches the common shape and misses anything routed through a helper, so a clean result is not a clearance.
More importantly, distinguishing a *validation* from an *allow-list* is the part that cannot be done
properly: a scheme check (`url.startswith("https://")`) is not a restriction on where the request goes,
while a host allow-list is. The two look alike from the AST, so this reports what guard it saw and lets a
reader judge.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

#: Modules that *are* an HTTP client when called directly (`httpx.get(...)`).
_PY_CLIENT_MODULES = {"httpx", "requests", "aiohttp", "urllib", "urllib3"}
#: Constructors whose result is a client, so the name it is bound to becomes one.
_PY_CLIENT_CTORS = re.compile(r"\b(?:httpx|requests|aiohttp)\.(?:Async)?(?:Client|Session|ClientSession)\b")
_PY_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream", "urlopen"}

#: Ways a value arrives from the caller. `data.get(...)` and friends are generic dict access and are
#: only treated as request input *inside a route handler*, where the dict is the parsed body — outside
#: one they tainted an ordinary `data.get("data", [])` in a service and produced a false finding.
_REQUEST_SOURCES = re.compile(r"\b(?:request\.(?:json|form|query_params|args|body|data)|await\s+request\.)")
_ROUTE_BODY_SOURCES = re.compile(r"\b(?:data|payload|body|form)\.get\b")

#: A guard that restricts *where* the request may go, as opposed to what it looks like.
_ALLOWLIST_HINTS = re.compile(
    r"\b(allow(?:ed)?_?(?:list|hosts?|domains?|origins?)|whitelist|is_allowed|in\s+ALLOWED|"
    r"ipaddress|is_private|resolve_host)\b", re.IGNORECASE)
#: A check on the shape of the string, which is not a restriction on the destination.
_SHAPE_ONLY_HINTS = re.compile(
    r"\b(startswith|urlparse|scheme|https?://|validate_url|HttpUrl|AnyUrl)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Fetch:
    file: str
    line: int
    callee: str            # e.g. "client.get"
    source: str            # how the URL reached it
    guard: str             # "none" | "shape-only" | "allow-list"
    in_route: bool         # the enclosing function is a route handler

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line}"


def _is_route(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        src = ast.unparse(dec) if hasattr(ast, "unparse") else ""
        if re.search(r"\.(get|post|put|patch|delete|route)\(", src):
            return True
    return False


def _client_names(fn: ast.AST) -> set[str]:
    """Names bound to an HTTP client in this function.

    A bare name list cannot do this job: `session` and `client` were on it, and SQLAlchemy's
    `session.delete(item)` and `session.get(User, id)` share their verbs with an HTTP client. The corpus
    regression caught three ORM deletes reported as server-side fetches. A name is a client only if
    something in scope assigned a client to it.
    """
    names = set(_PY_CLIENT_MODULES)
    for n in ast.walk(fn):
        val, targets = None, []
        if isinstance(n, ast.withitem):
            val, targets = n.context_expr, [n.optional_vars] if n.optional_vars else []
        elif isinstance(n, ast.Assign):
            val, targets = n.value, n.targets
        if val is None:
            continue
        src = ast.unparse(val) if hasattr(ast, "unparse") else ""
        if _PY_CLIENT_CTORS.search(src):
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
    return names


def _callee_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else (
            ast.unparse(f.value) if hasattr(ast, "unparse") else "")
        return f"{base}.{f.attr}"
    return f.id if isinstance(f, ast.Name) else ""


def _host_is_caller_controlled(node: ast.AST, tainted: set[str]) -> bool:
    """Does the caller decide *where* the request goes, or only what path it asks for?

    The discriminator the whole signal needs. Every proxy builds `f"{base}{path}"` with a base from
    configuration and a path from the request — the destination is fixed and that is not SSRF. Only a
    tainted value at the *front* of the URL controls the host.
    """
    if isinstance(node, ast.Name):
        return node.id in tainted
    if isinstance(node, ast.JoinedStr):                     # f-string: inspect the leading part
        for part in node.values:
            if isinstance(part, ast.Constant) and str(part.value).strip():
                return False                                # starts with a literal, e.g. "https://api/"
            if isinstance(part, ast.FormattedValue):
                return bool(_names_in(part.value) & tainted)
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _host_is_caller_controlled(node.left, tainted)
    if isinstance(node, ast.Call):
        # A method call carries its subject in the receiver, not the arguments: `url.replace("/v1", …)`
        # is still whatever `url` was. Only a plain call like `urljoin(base, path)` takes its base from
        # the first argument. Getting this backwards silently dropped the one true finding.
        if isinstance(node.func, ast.Attribute):
            return _host_is_caller_controlled(node.func.value, tainted)
        return bool(node.args) and _host_is_caller_controlled(node.args[0], tainted)
    if isinstance(node, ast.Attribute):
        return bool(_names_in(node) & tainted)
    return bool(_names_in(node) & tainted)


def _names_in(node: ast.AST) -> set[str]:
    """Identifiers actually referenced by an expression.

    Read from the AST rather than from `ast.unparse` text, because an f-string's literal segments are not
    references: `f"{endpoint.url}/models"` mentions the word `models` and refers to no such variable.
    Matching the text reported that as a tainted fetch.
    """
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _tainted_names(fn: ast.AST, params: set[str], in_route: bool) -> tuple[set[str], set[str]]:
    """Names in this function that hold something the caller supplied.

    Params of a route handler count, and so does anything assigned from a request accessor. One hop of
    propagation is followed (`u = url`, `h = u.replace(...)`), which is what the observed cases needed —
    a real taint engine is out of scope and would still not answer the guard question.
    """
    tainted = set(params)
    host = set(params)                       # ... and of those, the ones that choose the *host*
    for _ in range(3):                       # a few passes, so short chains settle
        for n in ast.walk(fn):
            if not isinstance(n, ast.Assign) or not n.targets:
                continue
            src = ast.unparse(n.value) if hasattr(ast, "unparse") else ""
            hits_request = bool(_REQUEST_SOURCES.search(src)) or (
                in_route and bool(_ROUTE_BODY_SOURCES.search(src)))
            hits_tainted = bool(_names_in(n.value) & tainted)
            if not (hits_request or hits_tainted):
                continue
            # Host-control has to travel with the name. `url = f"{base}{path}"` is tainted but its
            # destination is fixed, and once it is assigned to a name the position of the tainted part
            # is otherwise lost — which is how a proxy ends up reported as an SSRF.
            controls_host = hits_request or _host_is_caller_controlled(n.value, host)
            for tgt in n.targets:
                if isinstance(tgt, ast.Name):
                    tainted.add(tgt.id)
                    if controls_host:
                        host.add(tgt.id)
    return tainted, host


def _guard_in(fn: ast.AST) -> str:
    body = ast.unparse(fn) if hasattr(ast, "unparse") else ""
    if _ALLOWLIST_HINTS.search(body):
        return "allow-list"
    if _SHAPE_ONLY_HINTS.search(body):
        return "shape-only"
    return "none"


def scan_python(root: Path, files: set[str]) -> list[Fetch]:
    out: list[Fetch] = []
    for rel in sorted(files):
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse((root / rel).read_text(errors="replace"))
        except (OSError, SyntaxError):
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            in_route = _is_route(fn)
            # Parameters are caller-supplied only in a route handler. Inside a service method they come
            # from elsewhere in the application, and treating them as tainted made `self` taint every
            # method on every class — eight false positives against one real finding on the first run.
            params = ({a.arg for a in fn.args.args + fn.args.kwonlyargs} - {"self", "cls"}
                      if in_route else set())
            tainted, host_tainted = _tainted_names(fn, params, in_route)
            if not tainted:
                continue
            guard = _guard_in(fn)
            clients = _client_names(fn)
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                name = _callee_name(call)
                base, _, verb = name.rpartition(".")
                if verb not in _PY_VERBS:
                    continue
                if base.split(".")[0] not in clients:
                    continue
                if not call.args:
                    continue
                referenced = _names_in(call.args[0]) & tainted
                if referenced and _host_is_caller_controlled(call.args[0], host_tainted):
                    out.append(Fetch(rel, call.lineno, name, sorted(referenced)[0], guard, in_route))
    return out


# --- JS/TS ------------------------------------------------------------------------------------------
#
# Regex, not a parser, matching how archagent already reads JS/TS elsewhere (`drift._import_graph`,
# `webapi`): Python via `ast`, JS/TS via regex, no Node required. The cost is a coarser scope — the unit
# is the *file* rather than the function — which is tolerable only because the check first requires the
# file to look like server-side request handling. A React component that fetches a URL from props is not
# in scope and must not be: that request comes from the user's own browser, not from the server.

#: The file is a server-side request handler at all.
_TS_SERVER = re.compile(
    r"export\s+(?:async\s+)?function\s+(?:GET|POST|PUT|PATCH|DELETE)\b"   # Next.js route handler
    r"|\b(?:app|router)\.(?:get|post|put|patch|delete|all)\s*\("            # Express / Fastify
    r"|\bcreateServer\s*\(")

#: A value that came from the caller.
_TS_TAINT_SOURCE = re.compile(
    r"\b(?:req|request)\.(?:body|query|params|url|nextUrl)\b"
    r"|\bsearchParams\.get\s*\(|\bawait\s+(?:req|request)\.(?:json|text|formData)\s*\(")

#: An outbound request from the server.
_TS_FETCH = re.compile(
    r"\b(?:fetch|axios|got|superagent|ky)\s*(?:\.\s*(?:get|post|put|patch|delete|request))?\s*\(\s*([^,)]+)")

_TS_ALLOWLIST = re.compile(
    r"\b(allow(?:ed)?_?(?:list|Hosts?|Domains?|Origins?)|whitelist|isAllowed|ALLOWED_)\b", re.IGNORECASE)
_TS_SHAPE_ONLY = re.compile(
    r"\b(startsWith|new\s+URL|protocol|https?://|z\.string\(\)\.url)\b")

_TS_ASSIGN = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)")


def _ts_host_is_caller_controlled(expr: str, tainted: set[str]) -> bool:
    """As the Python version: only a tainted value at the front of the URL chooses the host.

    `` `${backend}${target.pathname}` `` is a proxy — the base is configuration and the caller picks the
    path. `` `${host}/health` `` is not.
    """
    e = expr.strip().lstrip("`'\"")
    if e.startswith(("http://", "https://", "/")):
        return False
    m = re.match(r"\$\{\s*([A-Za-z_$][\w$]*)", e)          # leading `${name}` of a template literal
    if m:
        return m.group(1) in tainted
    m = re.match(r"([A-Za-z_$][\w$]*)", e)                  # a bare identifier or `name + ...`
    return bool(m) and m.group(1) in tainted


def scan_ts(root: Path, files: set[str]) -> list[Fetch]:
    out: list[Fetch] = []
    for rel in sorted(files):
        if not rel.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
            continue
        try:
            text = (root / rel).read_text(errors="replace")
        except OSError:
            continue
        if not _TS_SERVER.search(text):
            continue
        tainted: set[str] = set()
        host_tainted: set[str] = set()
        for _ in range(3):
            for name, value in _TS_ASSIGN.findall(text):
                from_request = bool(_TS_TAINT_SOURCE.search(value))
                from_tainted = any(re.search(rf"\b{re.escape(v)}\b", value) for v in tainted)
                if not (from_request or from_tainted):
                    continue
                tainted.add(name)
                if from_request or _ts_host_is_caller_controlled(value, host_tainted):
                    host_tainted.add(name)
        if not host_tainted:
            continue
        guard = ("allow-list" if _TS_ALLOWLIST.search(text)
                 else "shape-only" if _TS_SHAPE_ONLY.search(text) else "none")
        for m in _TS_FETCH.finditer(text):
            arg = m.group(1)
            hit = next((v for v in sorted(tainted) if re.search(rf"\b{re.escape(v)}\b", arg)), None)
            if hit and _ts_host_is_caller_controlled(arg, host_tainted):
                line = text[:m.start()].count("\n") + 1
                out.append(Fetch(rel, line, m.group(0).split("(")[0].strip(), hit, guard, True))
    return out

"""Static extraction of a Python web app's route surface (for `archagent drift`).

No execution — routes are read straight from the source with `ast`:
  - FastAPI / Flask: `@x.get/post/put/delete/patch/head/options("/path")` and Flask
    `@x.route("/path", methods=[...])`.
  - Django: `path()/re_path()/url()` calls in a URLconf (a `urls.py`, or a file with `urlpatterns`).

The *intended* interface is a committed OpenAPI spec when one exists (`openapi.json/yaml`,
`swagger.*`); otherwise `drift` falls back to whether a route is mentioned in the architecture docs.
Routes are normalized (params -> `{}`, slashes trimmed) so the three frameworks and OpenAPI compare.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

_VERBS = {"get", "post", "put", "delete", "patch", "head", "options"}
_PARAM = re.compile(r"<[^>]+>|\{[^}]+\}|:[A-Za-z_]\w*|\(\?P<[^>]+>[^)]*\)")
_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
# Express / Fastify: `x.get('/path', ...)` — the "/path" first arg is the signal.
_JS_ROUTE = re.compile(r"""\.(get|post|put|delete|patch|head|options|all)\s*\(\s*['"`](/[^'"`]*)""", re.IGNORECASE)
# NestJS: `@Controller('prefix')` + `@Get('sub')` method decorators.
_NEST_CTRL = re.compile(r"""@Controller\(\s*['"`]?([^'"`)]*)""")
_NEST_METHOD = re.compile(r"""@(Get|Post|Put|Delete|Patch|Head|Options|All)\(\s*['"`]?([^'"`)]*)""")
_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv"}
_SPEC_NAMES = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml")


@dataclass(frozen=True)
class Route:
    method: str                                  # "GET".., or "*" when unknown (Django)
    path: str                                    # normalized: params -> {}, no surrounding slashes
    raw: str = field(default="", compare=False)  # original path string
    source: str = field(default="", compare=False)


def _norm(path: str) -> str:
    return _PARAM.sub("{}", path).strip("^$").strip("/")


# --- code routes ---------------------------------------------------------

def extract_routes(root: Path, source_files: set[str]) -> list[Route]:
    routes: list[Route] = []
    for rel in sorted(source_files):
        try:
            text = (root / rel).read_text()
        except OSError:
            continue
        if rel.endswith(".py"):
            try:
                tree = ast.parse(text)
            except (SyntaxError, ValueError):
                continue
            routes += _decorator_routes(tree, rel)
            if rel.endswith("urls.py") or "urlpatterns" in text:
                routes += _django_routes(tree, rel)
        elif rel.endswith(_JS_EXTS):
            routes += _js_routes(text, rel)
    return list(dict.fromkeys(routes))


def _js_routes(text: str, rel: str) -> list[Route]:
    out: list[Route] = []
    for verb, path in _JS_ROUTE.findall(text):  # Express / Fastify: x.get('/path', ...)
        out.append(Route("*" if verb.lower() == "all" else verb.upper(), _norm(path), path, rel))
    if "@Controller" in text:  # NestJS: combine controller prefix + method decorator
        prefixes = _NEST_CTRL.findall(text)
        prefix = prefixes[0] if prefixes else ""
        for verb, sub in _NEST_METHOD.findall(text):
            raw = "/" + "/".join(p.strip("/") for p in (prefix, sub) if p.strip("/"))
            out.append(Route("*" if verb.lower() == "all" else verb.upper(), _norm(raw), raw, rel))
    return out


def _first_str(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    for kw in call.keywords:
        if kw.arg in ("path", "rule") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _methods_kwarg(call: ast.Call) -> list[str] | None:
    for kw in call.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            return [e.value for e in kw.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return None


def _decorator_routes(tree: ast.AST, rel: str) -> list[Route]:
    out: list[Route] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            attr = dec.func.attr
            path = _first_str(dec)
            if path is None or not path.startswith("/"):
                continue  # a "/path" first arg is the strong signal this is a route decorator
            if attr in _VERBS:
                out.append(Route(attr.upper(), _norm(path), path, rel))
            elif attr == "route":
                for m in _methods_kwarg(dec) or ["GET"]:
                    out.append(Route(m.upper(), _norm(path), path, rel))
    return out


def _django_routes(tree: ast.AST, rel: str) -> list[Route]:
    out: list[Route] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name not in ("path", "re_path", "url"):
            continue
        p = _first_str(node)
        if p is not None:
            out.append(Route("*", _norm(p), p, rel))
    return out


# --- intended interface (OpenAPI spec) -----------------------------------

def load_openapi(root: Path) -> tuple[list[Route], str] | None:
    """Return (routes, spec_path) from the first committed OpenAPI/Swagger spec, or None."""
    for name in _SPEC_NAMES:
        for p in sorted(root.rglob(name)):
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            data = _parse_spec(p)
            paths = data.get("paths") if isinstance(data, dict) else None
            if isinstance(paths, dict):
                routes = [
                    Route(method.upper(), _norm(path), path, p.relative_to(root).as_posix())
                    for path, ops in paths.items()
                    if isinstance(ops, dict)
                    for method in ops
                    if method.lower() in _VERBS
                ]
                return routes, p.relative_to(root).as_posix()
    return None


def _parse_spec(path: Path):
    try:
        text = path.read_text()
    except OSError:
        return None
    if path.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    if yaml is not None:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            return None
    return None


# --- matching ------------------------------------------------------------

def matches(method: str, path: str, others: list[Route]) -> bool:
    """A route (method may be '*') is present in `others` if some entry shares its path and method."""
    return any(
        o.path == path and (method == "*" or o.method == "*" or o.method == method)
        for o in others
    )

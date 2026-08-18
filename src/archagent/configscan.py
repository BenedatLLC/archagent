"""Configuration surface — the environment keys the code reads vs. what's declared.

Extraction is static (no execution):
  - Python: `os.getenv("X")`, `os.environ["X"]`, `os.environ.get("X")`, and **one hop through a project's
    own helper** — `get_bool_from_env("X", ...)` where that function reaches the environment with its own
    parameter.
  - JS/TS:  `process.env.X`, `process.env["X"]`.

**Why the helper hop is not a nicety.** paperless-ngx reads 79 of its ~185 settings through
`get_bool_from_env`-style wrappers, so those names never appear as a literal argument to `os.getenv`. A
literal-only scan found exactly 98 keys; the artifact, written from archagent's own view of the surface,
declared exactly those 98; and `drift` then reported zero config drift in *both* directions — certifying
an incomplete list as complete. The loop is self-reinforcing, and nothing downstream could see out of it.

**And whatever this learns to parse, some project will read config another way.** `read_config_keys` can
therefore report how many reads it could *not* resolve, so a caller can state the limit instead of
implying there is none.

The *declared* config is a committed manifest when one exists — `.env.example` / `.env.sample` /
`.env.template` (the `KEY=` names) — plus any `**Config:**` lines in the architecture docs. `drift`
reports keys read-but-undeclared (undocumented) and declared-but-unread (dangling), gated on a manifest
existing so it stays low-noise.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .mdutil import is_empty_value

_KEY = r"([A-Za-z_][A-Za-z0-9_]*)"
_ENV_READS = [
    re.compile(r"os\.getenv\(\s*['\"]" + _KEY),
    re.compile(r"os\.environ\.get\(\s*['\"]" + _KEY),
    re.compile(r"os\.environ\[\s*['\"]" + _KEY),
    re.compile(r"process\.env\." + _KEY),
    re.compile(r"process\.env\[\s*['\"]" + _KEY),
]
_ENV_FILE = re.compile(r"^\s*(?:export\s+)?" + _KEY + r"\s*=", re.MULTILINE)
# require the bold `**Config:**` form so prose / a Mermaid `Configured` node isn't read as a manifest (issue #1)
#: `**Config:**` runs to the next blank line, not to the end of its first line.
#:
#: A real manifest is a long list of keys, and a writer wraps it. Reading only the first line silently
#: honours part of a declaration: the keys on line one verify, the keys on line two are reported as
#: "read in code but not declared" — a confident, wrong finding pointing at a document that *does*
#: declare them. Continuation lines must be indented or plain; a blank line or a new `**Field:**` ends it.
_CONFIG_DOC = re.compile(
    r"^\s*\*\*\s*Config\s*:?\s*\*\*\s*[:：]?\s*(.+(?:\n(?!\s*$|\s*\*\*\s*\w+\s*:).+)*)",
    re.IGNORECASE | re.MULTILINE)
_MANIFEST_GLOBS = (".env.example", ".env.sample", ".env.template", "*.env.example")
_CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


#: A call to `os.getenv` / `os.environ.get` / `os.environ[...]` whose key is *not* a literal. Counted so
#: the scan can say what it could not resolve rather than quietly returning a short list.
_ENV_READ_ANY = [
    re.compile(r"os\.getenv\(\s*(?!['\"])"),
    re.compile(r"os\.environ\.get\(\s*(?!['\"])"),
    re.compile(r"os\.environ\[\s*(?!['\"])"),
]


#: Same locations `originscan` skips, for the same reason: a test that sets `FLOAT_VAR` to exercise a
#: helper is not declaring deployment configuration. This only started to matter once wrapper calls became
#: visible — paperless-ngx's tests exercise `get_float_from_env` and friends with fixture names, which
#: arrived as seven junk keys in a list of 94. A tenth of a finding list being noise is how a check gets
#: switched off.
_TEST_DIRS = {"test", "tests", "__tests__", "testdata", "fixtures", "examples"}
_TEST_FILE = re.compile(r"(^|[._-])(test|spec)s?[._]")


def _is_test_path(rel: str) -> bool:
    parts = set(PurePosixPath(rel).parts)
    return bool(parts & _TEST_DIRS) or bool(_TEST_FILE.search(PurePosixPath(rel).name))


def _is_environ(node) -> bool:
    """`os.environ` or a bare `environ` imported from os."""
    import ast
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return True
    return isinstance(node, ast.Name) and node.id == "environ"


def _is_os_getenv(func) -> bool:
    import ast
    return isinstance(func, ast.Attribute) and func.attr == "getenv"


def _is_environ_get(func) -> bool:
    """`os.environ.get(...)` — and *only* that.

    The first version accepted any `.get(param)`, which is `dict.get`, so every
    `def lookup(key): return self._cache.get(key)` became an environment wrapper and every call to it
    contributed its first string argument as a config key. On paperless-ngx that turned 98 real keys into
    228 with `Archived`, `Checksum` and `Document` among them. The receiver is the whole check.
    """
    import ast
    return isinstance(func, ast.Attribute) and func.attr == "get" and _is_environ(func.value)


def _env_wrappers(text: str) -> dict[str, int]:
    """Python functions that read the environment using one of their own parameters.

    Returns `{function name: index of the parameter that carries the key}`. Only a function that actually
    reaches `os.getenv`/`os.environ` with that parameter counts — treating any `f("SOME_STRING")` as a
    config read would turn every string constant in the tree into a key.
    """
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    found: dict[str, int] = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        params = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
        if not params:
            continue
        for node in ast.walk(fn):
            name = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                a = node.args[0]
                arg = a.id if isinstance(a, ast.Name) else None
                if arg and (_is_os_getenv(node.func) or _is_environ_get(node.func)):
                    name = arg
            elif isinstance(node, ast.Subscript) and _is_environ(node.value):
                sl = node.slice
                name = sl.id if isinstance(sl, ast.Name) else None
            if name in params:
                found[fn.name] = params.index(name)
                break
    return found


def read_config_keys(root: Path, source_files: set[str], report_unresolved: bool = False):
    """The environment keys the code reads. With `report_unresolved`, also how many reads were opaque."""
    keys: set[str] = set()
    texts: dict[str, str] = {}
    for rel in source_files:
        if not rel.endswith(_CODE_EXTS) or _is_test_path(rel):
            continue
        try:
            texts[rel] = (root / rel).read_text()
        except OSError:
            continue

    wrappers: dict[str, int] = {}
    for rel, text in texts.items():
        if rel.endswith(".py"):
            wrappers.update(_env_wrappers(text))

    unresolved = 0
    for text in texts.values():
        for pat in _ENV_READS:
            keys.update(pat.findall(text))
        for pat in _ENV_READ_ANY:
            unresolved += len(pat.findall(text))
        for fn, idx in wrappers.items():
            # the literal in the key position of a call to a known wrapper
            arg = r"\s*(?:[^,()]+,){%d}\s*" % idx if idx else r"\s*"
            for m in re.finditer(rf"\b{re.escape(fn)}\({arg}['\"]" + _KEY, text):
                keys.add(m.group(1))

    return (keys, unresolved) if report_unresolved else keys


def declared_config_keys(root: Path, doc_text: str) -> set[str]:
    keys: set[str] = set()
    for glob in _MANIFEST_GLOBS:
        for p in root.glob(glob):
            if p.is_file():
                try:
                    keys.update(_ENV_FILE.findall(p.read_text()))
                except OSError:
                    pass
    for m in _CONFIG_DOC.finditer(doc_text):
        if is_empty_value(m.group(1)):
            continue
        keys.update(k.strip().strip("`") for k in re.split(r"[,\s]+", m.group(1).strip()) if k.strip())
    return keys

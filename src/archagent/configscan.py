"""Configuration surface — the environment keys the code reads vs. what's declared.

Extraction is static (no execution):
  - Python: `os.getenv("X")`, `os.environ["X"]`, `os.environ.get("X")`, and **one hop through a project's
    own helper** — `get_bool_from_env("X", ...)` where that function reaches the environment with its own
    parameter.
  - JS/TS:  `process.env.X`, `process.env["X"]`, and Vite's `import.meta.env.X`.

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

from .coverage import Coverage
from .mdutil import is_empty_value

_KEY = r"([A-Za-z_][A-Za-z0-9_]*)"
_ENV_READS = [
    re.compile(r"os\.getenv\(\s*['\"]" + _KEY),
    re.compile(r"os\.environ\.get\(\s*['\"]" + _KEY),
    re.compile(r"os\.environ\[\s*['\"]" + _KEY),
    re.compile(r"process\.env\." + _KEY),
    re.compile(r"process\.env\[\s*['\"]" + _KEY),
    # Vite's idiom, and the only way a Vite frontend reads configuration. Missing it reported
    # `VITE_API_URL` as declared-but-unread on `fastapi-template` while `main.tsx:16` reads it.
    re.compile(r"import\.meta\.env\." + _KEY),
    re.compile(r"import\.meta\.env\[\s*['\"]" + _KEY),
]
#: Keys a process **writes** for another process to read (issue #29).
#:
#: A write into an environment object is evidence the key is part of the configuration surface — arguably
#: better evidence than a read, because whoever wrote it knew the name mattered. obstudio is the worked
#: example: `extension/src/backend.ts:114` does `env.WEAVER_PATH = weaver` and
#: `extension.ts:619` builds `{ OBSTUDIO_WORKSPACE_ROOT: ... }`, both to configure the Go binary the
#: extension spawns. The reader is invisible — archagent does not parse Go — but the writer is right there
#: in TypeScript, and both keys were reported as declared-but-never-read.
#:
#: Deliberately narrow. `env.X = ` and a key inside an object literal passed to `spawn`/`exec`/`execFile`
#: are the two shapes seen; a bare `X = ` anywhere would match every assignment in the codebase.
_ENV_WRITES = [
    re.compile(r"\benv\.([A-Z][A-Z0-9_]{2,})\s*="),
    re.compile(r"\benv\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]\s*\]\s*="),
    re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]{2,})\s*="),
    re.compile(r"\bos\.environ\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]\s*\]\s*="),
    re.compile(r"\bos\.environ\.setdefault\(\s*['\"]([A-Z][A-Z0-9_]{2,})"),
]
#: The `env: { … }` object handed to a spawned process.
#:
#: Anchored on `env:` and brace-matched, not on the launcher call with a fixed window. obstudio's block is
#: fourteen keys long and `OBSTUDIO_WORKSPACE_ROOT` sits past any reasonable fixed distance from the
#: `spawn(`, while a window wide enough to reach it would sweep in whatever followed. The braces say where
#: the object ends; guessing a distance does not.
_ENV_OBJ = re.compile(r"\benv\s*:\s*\{")
_OBJ_KEY = re.compile(r"['\"]?([A-Z][A-Z0-9_]{2,})['\"]?\s*:")

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
#: An env read whose key is *not* a literal. The lookahead sits before the whitespace, not after it:
#: `\(\s*(?!['"])` matches `os.getenv( "LITERAL" )` anyway, because the engine backtracks `\s*` to zero
#: characters, looks ahead at the space and succeeds. That over-counted whitespace-padded literal reads
#: as opaque — harmless while the number was internal, and wrong once #46 put it in the report.
_ENV_READ_ANY = [
    re.compile(r"os\.getenv\((?!\s*['\"])"),
    re.compile(r"os\.environ\.get\((?!\s*['\"])"),
    re.compile(r"os\.environ\[(?!\s*['\"])"),
]


#: Same locations `originscan` skips, for the same reason: a test that sets `FLOAT_VAR` to exercise a
#: helper is not declaring deployment configuration. This only started to matter once wrapper calls became
#: visible — paperless-ngx's tests exercise `get_float_from_env` and friends with fixture names, which
#: arrived as seven junk keys in a list of 94. A tenth of a finding list being noise is how a check gets
#: switched off.
_TEST_DIRS = {"test", "tests", "__tests__", "testdata", "fixtures", "examples"}
_TEST_FILE = re.compile(r"(^|[._-])(test|spec)s?[._]")


def is_test_path(rel: str) -> bool:
    """Does this path look like test code?

    Public because three subsystems need the same answer and a fourth reading would be a fourth
    behaviour. `drift` uses it to decide what is exempt from documentation, `evaluate` to decide which
    reading of a hard-coded endpoint applies.
    """
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


def _settings_keys(text: str) -> set[str]:
    """Environment keys declared as pydantic-settings *fields*.

    The third way a project reads configuration, and the one with no call to find: pydantic-settings
    populates typed class attributes from the environment at import time. A scanner looking for
    `os.getenv` therefore concludes nothing reads them — which on `fastapi-template` reported all 18
    declared keys as dangling, and left `undocumented_config` unable to fire in the other direction, so
    the config half of `drift` was inert on the shape most modern FastAPI code uses.

    **Precision matters more than recall here.** A class is only scanned if it reaches `BaseSettings`,
    directly or through another class in the same file. Matching any class whose name ends in `Settings`
    would sweep up every `WorkerSettings` dataclass in the tree and turn its annotated attributes into
    environment keys, which is worse than the blind spot.
    """
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    settings_classes: set[str] = set()
    for _ in range(3):                     # resolve a short inheritance chain; deeper is vanishingly rare
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for b in cls.bases:
                name = ast.unparse(b).split(".")[-1]
                if name == "BaseSettings" or name in settings_classes:
                    settings_classes.add(cls.name)

    keys: set[str] = set()
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        if cls.name not in settings_classes:
            continue
        prefix = _env_prefix(cls)
        for node in cls.body:
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            field = node.target.id
            if field == "model_config" or field.startswith("_"):
                continue
            alias = _field_alias(node.value)
            # pydantic matches environment variables case-insensitively, so a field `debug` is set by
            # `DEBUG`. Reporting only the lowercase form would make every declared key look undeclared.
            keys.add(alias or (prefix + field).upper())
    return keys


def _env_prefix(cls) -> str:
    """`env_prefix` from `model_config = SettingsConfigDict(...)` or the older inner `class Config:`."""
    import ast
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "model_config" for t in node.targets):
            for kw in getattr(node.value, "keywords", []):
                if kw.arg == "env_prefix" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
        if isinstance(node, ast.ClassDef) and node.name == "Config":
            for inner in node.body:
                if (isinstance(inner, ast.Assign)
                        and any(getattr(t, "id", "") == "env_prefix" for t in inner.targets)
                        and isinstance(inner.value, ast.Constant)):
                    return str(inner.value.value)
    return ""


def _field_alias(value) -> str:
    """An explicit `Field(alias=...)` / `validation_alias=...`, which overrides the field name.

    `AliasChoices(...)` is not handled — it names several, and picking one would be a guess. Such a field
    falls back to its name, which is the conservative direction.
    """
    import ast
    if not (isinstance(value, ast.Call) and getattr(value.func, "id", "") == "Field"):
        return ""
    for kw in value.keywords:
        if kw.arg in ("alias", "validation_alias") and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return ""


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


def _spawned_env_keys(text: str) -> set[str]:
    """Keys in an `env: { … }` object literal — the environment handed to a spawned process.

    Anchored on `env:` rather than on the launcher call, because the object can be long: obstudio's is
    fourteen keys and the one that mattered sat past any reasonable fixed window. `{ FOO: bar }` alone is
    just a dictionary, so the `env:` label is what makes this specific rather than a sweep for shouting
    keys.
    """
    out: set[str] = set()
    for m in _ENV_OBJ.finditer(text):
        block = _braced(text, m.end() - 1)
        if block is not None:
            out.update(_OBJ_KEY.findall(block))
    return out


def _braced(text: str, open_at: int, limit: int = 4000) -> str | None:
    """The text between `text[open_at]` (a `{`) and its matching `}`, or None if unbalanced.

    Bounded so a stray brace cannot walk the whole file. Naive about braces inside strings, which is
    acceptable: the worst case is a slightly wide or narrow block, and the keys taken from it still have
    to look like environment names.
    """
    depth = 0
    for i in range(open_at, min(len(text), open_at + limit)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
    return None


def read_config_keys(root: Path, source_files: set[str], with_coverage: bool = False):
    """The environment keys the code reads. With `with_coverage`, also what it could not resolve.

    The unresolvable site is an env read whose key is not a literal — `os.getenv(name)`, where the name
    is computed. The key is real and this scanner cannot name it, so the configuration surface it reports
    is *incomplete by a known amount*, and saying so is the difference between a short list and a short
    list that admits it (#46).
    """
    keys: set[str] = set()
    texts: dict[str, str] = {}
    for rel in source_files:
        if not rel.endswith(_CODE_EXTS) or is_test_path(rel):
            continue
        try:
            texts[rel] = (root / rel).read_text()
        except OSError:
            continue

    wrappers: dict[str, int] = {}
    for rel, text in texts.items():
        if rel.endswith(".py"):
            wrappers.update(_env_wrappers(text))

    literal_sites = unresolved = 0
    for text in texts.values():
        keys |= _settings_keys(text)
        for pat in _ENV_READS:
            found = pat.findall(text)
            literal_sites += len(found)
            keys.update(found)
        # A key written for another process is part of the configuration surface too (issue #29).
        for pat in _ENV_WRITES:
            keys.update(pat.findall(text))
        keys |= _spawned_env_keys(text)
        for pat in _ENV_READ_ANY:
            unresolved += len(pat.findall(text))
        for fn, idx in wrappers.items():
            # the literal in the key position of a call to a known wrapper
            arg = r"\s*(?:[^,()]+,){%d}\s*" % idx if idx else r"\s*"
            for m in re.finditer(rf"\b{re.escape(fn)}\({arg}['\"]" + _KEY, text):
                keys.add(m.group(1))

    if not with_coverage:
        return keys
    cov = Coverage(
        what="environment reads", unit="read",
        seen=literal_sites + unresolved, resolved=literal_sites,
        # A repository that reads no environment at all is ordinary — a library, a CLI with only flags.
        empty_is_normal=True,
    )
    return keys, cov


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

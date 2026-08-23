"""`archagent drift` — a structural reflexion-diff between the architecture docs and the code.

Compares what the `architecture/` docs *say* against what the code *is*, and reports:
  - **dangling references** (absence): a doc names code (a `path/to/file.py` backtick ref, or a
    `**Covers:**` glob) that no longer exists.
  - **stale docs** (a git-staleness heuristic): a subsystem doc's covered code has newer git commits
    than the doc itself — the code moved on, the doc may not have.

Informational by design (the update work-list), not a per-commit gate. A doc maps to its code via an
explicit `**Covers:** <globs>` line when present, else the `path/to/file.py` references in its prose.
"""

from __future__ import annotations

import ast
import json
import posixpath
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # py < 3.11
    tomllib = None

from .config import Config
from .configscan import _is_test_path, declared_config_keys, read_config_keys
from .connscan import sync_call_targets
from .tiers import tier_of as _tier_of, tier_rank
from .mdutil import is_empty_value, strip_code_fences
from .deployscan import (declared_services, deployment_config_keys, extract_service_edges,
                         extract_services)
from .webapi import extract_routes, load_openapi, matches

CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".rb")
_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv", ".mypy_cache"}
_BACKTICK = re.compile(r"`([^`\n]+)`")
# Metadata declarations MUST use the bold `**Field:**` form (issue #1): the `**` markers are required so
# that ordinary prose or a Mermaid node that merely starts with the word is not mis-read as a declaration.
_COVERS = re.compile(r"^\s*\*\*\s*Covers\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_DEPENDS = re.compile(r"^\s*\*\*\s*Depends[- ]?on\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_CONNECTS = re.compile(r"^\s*\*\*\s*Connects\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_SERVICE = re.compile(r"^\s*\*\*\s*Service(?!s)\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)

# The connector kinds a **Connects:** edge may declare (Wright's canonical interaction types, mapped to
# what real systems do). `import` = in-process code dependency = the classic **Depends-on:** meaning.
CONNECTOR_KINDS = ("import", "sync-call", "async-event", "shared-data", "pipe")
_SYNC_KINDS = ("import", "sync-call", "shared-data")  # tight coupling (caller/data blocks)


@dataclass
class DriftResult:
    dangling: list[tuple[str, str]] = field(default_factory=list)  # (doc, missing ref/glob)
    stale: list[tuple[str, str]] = field(default_factory=list)     # (doc, detail)
    undocumented: list[str] = field(default_factory=list)          # source files no subsystem Covers
    undeclared_deps: list[tuple[str, str]] = field(default_factory=list)  # (subsystem, imported subsystem)
    stale_deps: list[tuple[str, str]] = field(default_factory=list)       # (subsystem, declared-but-unused dep)
    undocumented_entrypoints: list[tuple[str, str]] = field(default_factory=list)  # (name, target)
    undocumented_routes: list[tuple[str, str]] = field(default_factory=list)  # (method, path) in code, not intended
    dangling_routes: list[tuple[str, str]] = field(default_factory=list)      # (method, path) in spec, not in code
    undocumented_config: list[str] = field(default_factory=list)  # env key read in code, not declared
    dangling_config: list[str] = field(default_factory=list)      # declared config key not read in code
    undocumented_services: list[str] = field(default_factory=list)  # service in IaC, not declared
    dangling_services: list[str] = field(default_factory=list)      # declared service, not found in IaC
    missing_deploy_edges: list[tuple[str, str]] = field(default_factory=list)  # code needs it, compose doesn't wire it
    extra_deploy_edges: list[tuple[str, str]] = field(default_factory=list)    # compose wires it, code doesn't need it
    connector_mismatches: list[tuple[str, str, str, str]] = field(default_factory=list)  # (subsystem, target, declared kind, observed kind)
    #: (subsystem, declared tier) — covers only non-production code but claims a place on the layer
    #: ladder. Issue #26: the artifact says something the code contradicts, which is this command's job.
    mistiered: list[tuple[str, str]] = field(default_factory=list)
    openapi_spec: str | None = None  # the committed spec used as the intended interface, if any
    git_available: bool = False
    covers_declared: bool = False  # did any subsystem doc declare **Covers:**? (gates undocumented)

    @property
    def any(self) -> bool:
        return bool(
            self.dangling or self.stale or self.undocumented
            or self.undeclared_deps or self.stale_deps or self.undocumented_entrypoints
            or self.undocumented_routes or self.dangling_routes
            or self.undocumented_config or self.dangling_config
            or self.undocumented_services or self.dangling_services
            or self.missing_deploy_edges or self.extra_deploy_edges
            or self.connector_mismatches or self.mistiered
        )


def find_drift(config: Config, until: str | None = None) -> DriftResult:
    """`until` bounds the staleness comparison to a past window, so `drift` can be scored as of a
    revision the way the rest of the evaluation is (see docs/designs/evaluating-archagent.md §5)."""
    root = config.project_root
    arch = config.architecture_dir
    result = DriftResult(git_available=_git_available(root))
    if not arch.is_dir():
        return result

    source_files = _source_files(config)  # relative posix paths, for robust ref resolution
    covered_by_globs: set[str] = set()    # accumulates files claimed by any **Covers:** glob
    all_text: list[str] = []
    subs: list[tuple[str, set[str], dict[str, str] | None]] = []  # (name, covered files, declared connectors {target: kind})
    sub_service: dict[str, str] = {}  # subsystem name -> the deployment service it runs as (**Service:**)

    for doc in sorted(arch.rglob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        text = strip_code_fences(doc.read_text())  # fenced code / Mermaid can't declare metadata (issue #1)
        all_text.append(text)
        rel_doc = doc.relative_to(root).as_posix()
        refs = _file_refs(text)
        covers = _covers_globs(text)
        if covers:
            result.covers_declared = True

        # absence: references / covers globs that resolve to nothing
        for ref in refs:
            if _resolve_ref(ref, root, source_files) is None:
                result.dangling.append((rel_doc, ref))
        for glob in covers:
            matched = _glob_files(root, glob)  # code files only; these count toward coverage
            covered_by_globs.update(matched)
            # Only truly dangling if the glob matches NO file at all. A glob that matches non-code assets
            # (prompt `.md`, fixtures, SQL) is a legitimate data-file Covers, not a dangling ref (issue #1).
            if not matched and not _glob_matches_any(root, glob):
                result.dangling.append((rel_doc, f"{glob}  (Covers matches no files)"))

        if _is_subsystem(doc, arch):
            covered_files = set()
            for glob in covers:
                covered_files.update(_glob_files(root, glob))
            subs.append((doc.stem, covered_files, _connectors(text)))
            svc = _service_of(text)
            if svc:
                sub_service[doc.stem] = svc
            mistier = _mistiered(covered_files, _tier_of(text))
            if mistier:
                result.mistiered.append((doc.stem, mistier))

            # staleness: only subsystem docs describe code, and only when git can tell us
            if result.git_available:
                covered = _covered_files(root, covers, refs, source_files)
                newer = [f for f in covered if _committed_after(root, f, rel_doc, until)]
                if newer:
                    shown = ", ".join(newer[:3]) + (f" (+{len(newer) - 3} more)" if len(newer) > 3 else "")
                    result.stale.append((rel_doc, f"{len(newer)} covered file(s) changed after the doc: {shown}"))

    # divergence: source files owned by no subsystem's Covers glob. Only meaningful once some
    # doc declares Covers (otherwise every file is "undocumented", which is noise).
    if result.covers_declared:
        result.undocumented = sorted(
            f for f in source_files
            if f not in covered_by_globs and not f.endswith("__init__.py")
        )

    # dependency-edge + entry-point + interface-surface drift (Python + JS/TS)
    doc_text = "\n".join(all_text)
    import_graph = _import_graph(root, config, source_files)
    result.undeclared_deps, result.stale_deps = _dependency_drift(subs, import_graph)
    result.undocumented_entrypoints = _entrypoint_drift(root, doc_text)
    result.undocumented_routes, result.dangling_routes, result.openapi_spec = \
        _interface_drift(root, source_files, doc_text)

    # configuration drift: env keys read in code vs a declared manifest (gated on one existing)
    declared_cfg = declared_config_keys(root, doc_text)
    if declared_cfg:
        read_cfg = read_config_keys(root, source_files)
        # A key the deployment consumes is read, just not by application code (issue #24). `read_config_keys`
        # scans `source_paths`, which is exactly where deployment configuration does not live, so a key used
        # only by a compose file or a container entrypoint came back "declared but never read" — true, and
        # not a defect. wardrowbe produced 24 of those at once, every one correct, which invites deleting an
        # accurate manifest and buries the finding that matters: a key nothing reads anywhere.
        deploy_cfg = deployment_config_keys(root)
        result.dangling_config = sorted(declared_cfg - read_cfg - deploy_cfg)
        # Deliberately asymmetric: the deployment's keys suppress a dangling finding but do not create an
        # undocumented one. Compose interpolation picks up image tags and port numbers, and treating every
        # one as part of the configuration surface would trade two dozen false dangling findings for two
        # dozen false undocumented ones.
        result.undocumented_config = sorted(read_cfg - declared_cfg)

    # deployment drift: services in IaC vs a declared **Services:** list (gated on a declaration)
    declared_svc = declared_services(doc_text)
    if declared_svc or sub_service:
        actual_svc = extract_services(root)
        if declared_svc:
            result.undocumented_services = sorted(actual_svc - declared_svc)
            result.dangling_services = sorted(declared_svc - actual_svc)
        # service-dependency edge cross-check: code's cross-service deps vs compose depends_on
        if sub_service and actual_svc:
            result.missing_deploy_edges, result.extra_deploy_edges = _service_edge_drift(
                subs, sub_service, import_graph, extract_service_edges(root))

    # connector-kind mismatch: a declared connector the code contradicts (declared async-event, but the
    # code makes a resolved synchronous HTTP call to that target)
    result.connector_mismatches = _connector_mismatch(root, subs, sub_service)

    return result


# --- doc parsing ---------------------------------------------------------

def _file_refs(text: str) -> list[str]:
    """Backtick tokens that look like references to CODE files.

    A bare extension is not one. Prose says things like "the suite is `.ts` only" or "three `.mjs`
    tools", and reading those as filenames reported them as code that no longer exists — a dangling
    finding against a document that named no file at all.
    """
    out: list[str] = []
    for tok in _BACKTICK.findall(text):
        t = tok.strip()
        if " " in t or not t.endswith(CODE_EXTS):
            continue
        stem = t.rsplit("/", 1)[-1]
        if stem.startswith("."):        # `.ts`, `.mjs` — an extension, not a file
            continue
        if t not in out:
            out.append(t)
    return out


#: A subsystem whose covered files are *entirely* non-production — tests, migrations, fixtures — has no
#: place on the layer ladder, and saying it does is a claim about the code that the code contradicts.
#: That makes it drift rather than a smell, which is why it is reported here and not by `evaluate`.
#:
#: Issue #26. Seven `layer-inversion` findings were labelled blind across three repositories: all three
#: confirmations were production code and all four dismissals were test or migration packages, every one
#: of them tiered `infra` — the bottom rank — so that everything the tests imported read as "upward".
#:
#: **Every covered file must be non-production**, not merely most. A subsystem mixing production code with
#: its tests is a production subsystem and belongs on the ladder; flagging it would move the false
#: positives rather than remove them.
#: Directories whose contents are not the product. `scripts` is here because the tier vocabulary already
#: recognises `scripts` as non-layered, so treating it as production here would contradict the spec.
#:
#: Known limit: this catches two of the four mis-tierings the calibration rounds found. It misses
#: fastapi-template's `backend-ops`, whose startup and seed files sit in the app package under no
#: distinguishing path, and it would miss any similar case. That is deliberate — inferring "this is
#: really operational code" from `backend_pre_start.py` is the name-based guess this project has twice
#: regretted. `describe` emitting the right tier is what covers those; this is the backstop for artifacts
#: that already exist, and a backstop that only catches the unambiguous cases is still worth having.
_MIGRATION_DIRS = {"migrations", "migration", "alembic", "versions", "scripts"}


def _mistiered(covered: set[str], tier: str | None) -> str:
    """The declared production tier of a subsystem that covers only non-production code, or "".

    Silent when nothing is covered, when no tier is declared, or when the tier already says the subsystem
    is off the ladder — there is nothing to correct in any of those.
    """
    if not covered or tier_rank(tier) is None:
        return ""
    def _non_production(rel: str) -> bool:
        return _is_test_path(rel) or bool(set(PurePosixPath(rel).parts) & _MIGRATION_DIRS)
    return tier if all(_non_production(f) for f in covered) else ""


def _covers_globs(text: str) -> list[str]:
    globs: list[str] = []
    for m in _COVERS.finditer(text):
        if is_empty_value(m.group(1)):  # e.g. `**Covers:** (none)` — not a real declaration (issue #1)
            continue
        for part in re.split(r"[,\s]+", m.group(1).strip()):
            g = part.strip().strip("`")
            if g:
                globs.append(g)
    return globs


# --- resolution ----------------------------------------------------------

def _source_files(config: Config) -> set[str]:
    root = config.project_root
    roots: list[str] = []
    for cfg in (config.python, config.ts):
        roots += getattr(cfg, "source_paths", []) or []
    files: set[str] = set()
    for sp in dict.fromkeys(roots):  # dedupe, keep order irrelevant
        base = root / sp
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in CODE_EXTS and not any(part in _SKIP_DIRS for part in p.parts):
                files.add(p.relative_to(root).as_posix())
    return files


def _resolve_ref(ref: str, root: Path, source_files: set[str]) -> str | None:
    """Return the actual root-relative path a doc reference points to, or None if it doesn't exist.

    Two things this must not call dangling, both found by running against a repo unlike this one:

    **A glob is not a missing file.** `**Covers:** `observer/internal/otlp/*.go`` puts a pattern in
    backticks, and a literal `exists()` on `.../*.go` is always false. Every wildcard `Covers` line in a
    repo that uses them was reported as "a doc names code that no longer exists".

    **A file in a language we do not analyse still exists.** `source_files` holds only the configured
    languages, so on a Go repo every accurate `main.go` citation resolved to nothing. Saying "no longer
    exists" about code sitting in the tree is a confident false claim — worse than saying nothing. The
    filesystem is checked before that verdict is reached.
    """
    if (root / ref).exists():
        return ref
    r = ref.lstrip("./")
    if any(ch in r for ch in "*?["):
        if _glob_matches_any(root, r):
            return r
        # Not necessarily a pattern. A literal path can contain glob metacharacters: every Next.js
        # App Router dynamic segment does — `[id]`, `[...path]`, `[[...slug]]` — and as a glob those
        # brackets are a character class that matches none of them. Fall through to the ordinary
        # lookups rather than reporting a file that exists as missing.
    if "/" in r:
        for sf in source_files:
            if sf == r or sf.endswith("/" + r):
                return sf
    else:
        for sf in source_files:
            if sf.rsplit("/", 1)[-1] == r:
                return sf
    return _find_in_tree(root, r)


@lru_cache(maxsize=8)
def _tree_basenames(root: Path) -> dict[str, str]:
    """basename -> one root-relative path, over every file archagent can see.

    Used only to decide whether a reference points at something real in an unanalysed language, so one
    representative path per basename is enough.
    """
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if not p.is_file() or _SKIP_DIRS & set(p.parts):
            continue
        out.setdefault(p.name, p.relative_to(root).as_posix())
    return out


def _find_in_tree(root: Path, ref: str) -> str | None:
    hit = _tree_basenames(root).get(ref.rsplit("/", 1)[-1])
    if hit and (ref == hit or hit.endswith("/" + ref) or "/" not in ref):
        return hit
    return None


def _covered_files(root: Path, covers: list[str], refs: list[str], source_files: set[str]) -> list[str]:
    """The code a subsystem doc covers: Covers globs if declared, else its resolved file refs."""
    if covers:
        out: list[str] = []
        for glob in covers:
            out += _glob_files(root, glob)
        return list(dict.fromkeys(out))
    resolved = [_resolve_ref(r, root, source_files) for r in refs]
    return [r for r in dict.fromkeys(resolved) if r]


def _glob_files(root: Path, glob: str) -> list[str]:
    return [
        p.relative_to(root).as_posix()
        for p in root.glob(glob)
        if p.is_file() and p.suffix in CODE_EXTS and not any(part in _SKIP_DIRS for part in p.parts)
    ]


def _glob_matches_any(root: Path, glob: str) -> bool:
    """Whether the glob matches any file at all (code or data). Used to tell a legitimate data-file
    Covers (matches `.md`/fixtures) from a genuinely dangling glob (matches nothing)."""
    try:
        return any(
            p.is_file() and not any(part in _SKIP_DIRS for part in p.parts)
            for p in root.glob(glob)
        )
    except (OSError, ValueError):
        return False


def _is_subsystem(doc: Path, arch: Path) -> bool:
    return doc.parent == arch / "subsystems"


# --- git -----------------------------------------------------------------

def _git(root: Path, *args: str, timeout: int = 30) -> str | None:
    """Run git, or return None if it fails. Callers that cannot tell an empty result from a failure must
    check for None themselves — `mine_cochange` learned this the hard way (see `CoChange.mining_failed`).

    30s suits the single-fact queries this is mostly used for. The full-history walk needs longer: on a
    large repository `git log --name-only` over thousands of commits takes tens of seconds, and more again
    on a partial clone that fetches trees on demand.
    """
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _git_available(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree") == "true"


def _last_commit_ts(root: Path, rel_path: str, until: str | None = None) -> int | None:
    args = ["log", "-1", "--format=%ct"]
    if until:
        args.append(f"--until={until}")
    out = _git(root, *args, "--", rel_path)
    return int(out) if out else None


def _committed_after(root: Path, file_rel: str, doc_rel: str, until: str | None = None) -> bool:
    ft = _last_commit_ts(root, file_rel, until)
    dt = _last_commit_ts(root, doc_rel, until)
    return ft is not None and dt is not None and ft > dt


# --- dependency-edge + entry-point drift (Python v1) ---------------------

def _connectors(text: str) -> dict[str, str] | None:
    """Parse `**Connects:** a via sync-call, b` (preferred) or the `**Depends-on:** a, b` alias into
    `{target: kind}`. Kind defaults to `import` (what Depends-on always meant); an unknown kind falls back
    to `import` so a typo stays low-noise. None if the doc declares neither field."""
    src = _CONNECTS.search(text) or _DEPENDS.search(text)
    if not src or is_empty_value(src.group(1)):  # `**Connects:** _(none)_` is not a declaration (issue #1)
        return None
    out: dict[str, str] = {}
    for item in src.group(1).strip().split(","):
        item = item.strip()
        if not item:
            continue
        parts = re.split(r"\s+via\s+", item, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            target = parts[0].strip().strip("`")
            kind = parts[1].strip().strip("`").lower()
            if target:
                out[target] = kind if kind in CONNECTOR_KINDS else "import"
        else:  # no "via" — legacy form, one or more whitespace-separated targets, all import-kind
            for tok in item.split():
                t = tok.strip("`")
                if t:
                    out[t] = "import"
    return out


def _service_of(text: str) -> str | None:
    """Parse a subsystem doc's `**Service:** <name>` line (the service it deploys as). Not `Services:`."""
    m = _SERVICE.search(text)
    if not m or is_empty_value(m.group(1)):
        return None
    parts = [p.strip().strip("`") for p in re.split(r"[,\s]+", m.group(1).strip()) if p.strip()]
    return parts[0] if parts else None


def _service_edge_drift(subs, sub_service, import_graph, compose_edges):
    """Cross-service code dependencies (subsystem edges mapped via **Service:**) vs compose depends_on.

    A service pair declared as an `async-event` connector is exempt from needing a compose `depends_on`:
    an event consumer doesn't need the producer up at startup, so the deployment needn't wire it."""
    file_subs: dict[str, set[str]] = {}
    for name, files, _ in subs:
        for f in files:
            file_subs.setdefault(f, set()).add(name)
    # service pairs the docs declare as async-event (either direction) — exempt from depends_on
    async_pairs: set[tuple[str, str]] = set()
    for name, _, declared in subs:
        for target, kind in (declared or {}).items():
            if kind == "async-event":
                ss, st = sub_service.get(name), sub_service.get(target)
                if ss and st and ss != st:
                    async_pairs.add((ss, st))
    # actual cross-service edges the code requires
    needed: set[tuple[str, str]] = set()
    for name, files, _ in subs:
        for f in files:
            for target_file in import_graph.get(f, ()):
                for tsub in file_subs.get(target_file, ()):
                    ss, st = sub_service.get(name), sub_service.get(tsub)
                    if ss and st and ss != st:
                        needed.add((ss, st))
    compose = set(compose_edges)
    hosting = set(sub_service.values())  # services that actually host a subsystem
    missing = sorted(needed - compose - async_pairs)  # code needs it, deploy doesn't wire it (async exempt)
    extra = sorted(e for e in compose - needed if e[0] in hosting and e[1] in hosting)  # wired, unneeded
    return missing, extra


def _connector_mismatch(root, subs, sub_service):
    """A declared connector kind the code contradicts. v1: declared `async-event` but the code makes a
    resolved synchronous HTTP call to that target — the doc claims a decoupling the code doesn't have."""
    names = {name for name, _, _ in subs} | set(sub_service.values())
    out: list[tuple[str, str, str, str]] = []
    for name, files, declared in subs:
        async_targets = [t for t, k in (declared or {}).items() if k == "async-event"]
        if not async_targets:  # only async-event declarations can be contradicted by a sync call
            continue
        observed_sync: set[str] = set()  # resolved subsystem/service names this subsystem sync-calls
        for f in files:
            observed_sync |= sync_call_targets(root, f, names)
        for target in async_targets:
            identity = {target, sub_service.get(target, "")}  # the target subsystem or its service
            if observed_sync & identity:
                out.append((name, target, "async-event", "sync-call"))
    return out


def _dependency_drift(subs, import_graph):
    """Declared connectors vs the actual cross-subsystem import graph (only for docs that declare).

    Only `import`-kind connectors are checked against the import graph: a `sync-call`/`async-event`/
    `shared-data` edge is a *runtime* connector, not an import, so it must not be reported as stale for
    lacking one. An actual import is "undeclared" only if the target isn't acknowledged under any kind."""
    file_subs: dict[str, set[str]] = {}
    for name, files, _ in subs:
        for f in files:
            file_subs.setdefault(f, set()).add(name)

    undeclared: list[tuple[str, str]] = []
    stale: list[tuple[str, str]] = []
    for name, files, declared in subs:
        if declared is None:  # gated: only subsystems that declare connectors participate
            continue
        actual: set[str] = set()
        for f in files:
            for target_file in import_graph.get(f, ()):
                actual |= {t for t in file_subs.get(target_file, ()) if t != name}
        declared_any = set(declared)                                     # acknowledged under any kind
        declared_import = {t for t, k in declared.items() if k == "import"}
        undeclared += [(name, t) for t in sorted(actual - declared_any)]
        stale += [(name, t) for t in sorted(declared_import - actual)]   # only import-kind can be import-stale
    return undeclared, stale


def _import_graph(root: Path, config: Config, source_files: set[str]) -> dict[str, set[str]]:
    """file -> set of internal files it imports. Python via `ast`, JS/TS via regex (no node)."""
    py_index = _module_index(source_files, config.python.source_paths)
    graph: dict[str, set[str]] = {}
    for f in source_files:
        if f.endswith(".py"):
            graph[f] = _internal_targets(root, f, config.python.source_paths, py_index)
        elif f.endswith(_JS_EXTS):
            graph[f] = _js_targets(root, f, source_files)
    return graph


# --- JS/TS imports (regex, no node) --------------------------------------

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_JS_IMPORT = re.compile(
    r"""(?:import|export)\s+(?:[^'"]*?\sfrom\s+)?['"]([^'"]+)['"]"""  # import/export ... from '...'
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)"""                          # require('...')
    r"""|import\(\s*['"]([^'"]+)['"]\s*\)""",                          # dynamic import('...')
)


def _js_targets(root: Path, rel_file: str, source_files: set[str]) -> set[str]:
    try:
        text = (root / rel_file).read_text()
    except OSError:
        return set()
    targets: set[str] = set()
    for m in _JS_IMPORT.finditer(text):
        spec = m.group(1) or m.group(2) or m.group(3)
        if spec and spec.startswith("."):  # relative -> internal; bare specifiers are npm packages
            resolved = _resolve_js(rel_file, spec, source_files)
            if resolved and resolved != rel_file:
                targets.add(resolved)
    return targets


def _resolve_js(rel_file: str, spec: str, source_files: set[str]) -> str | None:
    target = posixpath.normpath(posixpath.join(posixpath.dirname(rel_file), spec))
    cands = [target] + [target + e for e in _JS_EXTS] + [posixpath.join(target, "index" + e) for e in _JS_EXTS]
    if target.endswith(".js"):  # NodeNext: a '.js' specifier often maps to a '.ts' source
        cands += [target[:-3] + ".ts", target[:-3] + ".tsx"]
    return next((c for c in cands if c in source_files), None)


def _module_of(rel_path: str, source_paths: list[str]) -> str | None:
    """Which import module a file resolves to, given the directories that are on the path.

    **A source path of `.` means the repository root**, and until this handled it the prefix was built as
    `"." + "/"` — so no path ever matched and a repository whose package sits at the root resolved *no
    modules at all*. That is one of the two standard Python layouts (`dspy/`, `requests/`, `flask/`);
    every target archagent had been run against happened to use the other one (`src/`, `backend/`).

    The failure was total and silent in the usual way: no modules means an empty import graph, so
    BOUNDARY contracts scope to nothing and every structural signal reports nothing, while `check` says
    all invariants hold.
    """
    for sp in source_paths:
        # `src`, `src/`, `./src` and `"."` are all things a person writes in a config file and all mean
        # something unambiguous. Normalising here beats a config-format rule nobody would read.
        stripped = sp.strip().removeprefix("./").strip("/")
        prefix = "" if stripped in ("", ".") else stripped + "/"
        if rel_path.startswith(prefix) and rel_path.endswith(".py"):
            parts = rel_path[len(prefix):-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts)
    return None


def _module_index(source_files: set[str], source_paths: list[str]) -> dict[str, str]:
    idx: dict[str, str] = {}
    for f in source_files:
        m = _module_of(f, source_paths)
        if m:
            idx[m] = f
    return idx


def module_map(config: Config) -> dict[str, list[str]]:
    """How each Python source file resolves to a top-level import module, keyed by module name.

    Collision-aware (unlike `_module_index`, which keeps one file per module): a module mapping to more than
    one file is a name collision — two packages that install under the same top-level name, which quietly
    breaks import-linter scoping. Exposed by `archagent modules` so that fact is a one-command check rather
    than a debugging session. Python only (module resolution is language-specific)."""
    out: dict[str, list[str]] = {}
    for f in sorted(_source_files(config)):
        if not f.endswith(".py"):
            continue
        m = _module_of(f, config.python.source_paths)
        if m:
            out.setdefault(m, []).append(f)
    return out


def _imports_of(root: Path, rel_file: str, self_mod: str | None) -> list[str]:
    try:
        tree = ast.parse((root / rel_file).read_text())
    except (SyntaxError, OSError, ValueError):
        return []
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — resolve against this file's package
                if not self_mod:
                    continue
                base = self_mod.split(".")
                pkg = base[:-node.level] if len(base) >= node.level else []
                if node.module:
                    stem = pkg + node.module.split(".")
                    mods.append(".".join(stem))
                    mods += [".".join(stem + [a.name]) for a in node.names]
                else:
                    mods += [".".join(pkg + [a.name]) for a in node.names]
            elif node.module:
                mods.append(node.module)
                mods += [f"{node.module}.{a.name}" for a in node.names]  # from pkg import submodule
    return mods


def _internal_targets(root: Path, rel_file: str, source_paths: list[str], module_index: dict[str, str]) -> set[str]:
    self_mod = _module_of(rel_file, source_paths)
    targets = {module_index.get(cand) for cand in _imports_of(root, rel_file, self_mod)}
    targets.discard(None)
    targets.discard(rel_file)
    return targets  # type: ignore[return-value]


def _entry_points(root: Path) -> list[tuple[str, str]]:
    return _pyproject_scripts(root) + _package_json_bin(root)


def _pyproject_scripts(root: Path) -> list[tuple[str, str]]:
    pp = root / "pyproject.toml"
    if tomllib is None or not pp.exists():
        return []
    try:
        data = tomllib.loads(pp.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return []
    proj = data.get("project", {})
    eps: dict[str, str] = {}
    eps.update(proj.get("scripts", {}) or {})
    eps.update(proj.get("gui-scripts", {}) or {})
    return list(eps.items())


def _package_json_bin(root: Path) -> list[tuple[str, str]]:
    pj = root / "package.json"
    if not pj.exists():
        return []
    try:
        data = json.loads(pj.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    b = data.get("bin")
    if isinstance(b, str):
        return [(data.get("name", "(package)"), b)]
    if isinstance(b, dict):
        return list(b.items())
    return []


def _entrypoint_drift(root: Path, doc_text: str) -> list[tuple[str, str]]:
    """Declared entry points not mentioned (by name or target module) in any architecture doc."""
    out: list[tuple[str, str]] = []
    for name, target in _entry_points(root):
        tgt_mod = target.split(":", 1)[0]
        if name not in doc_text and tgt_mod not in doc_text:
            out.append((name, target))
    return out


def _interface_drift(root, source_files, doc_text):
    """Web-route surface (static) vs a committed OpenAPI spec if present, else the architecture docs."""
    code_routes = extract_routes(root, source_files)
    if not code_routes:
        return [], [], None
    spec = load_openapi(root)
    if spec is not None:
        spec_routes, spec_path = spec
        undocumented = [(r.method, r.raw) for r in code_routes if not matches(r.method, r.path, spec_routes)]
        dangling = [(s.method, s.raw) for s in spec_routes if not matches(s.method, s.path, code_routes)]
        return undocumented, dangling, spec_path
    # no spec — fall back to whether the route path is mentioned in any architecture doc
    undocumented = [(r.method, r.raw) for r in code_routes
                    if r.raw not in doc_text and ("/" + r.path) not in doc_text]
    return undocumented, [], None

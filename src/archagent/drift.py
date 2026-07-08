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

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".rb")
_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv", ".mypy_cache"}
_BACKTICK = re.compile(r"`([^`\n]+)`")
_COVERS = re.compile(r"^\s*\*{0,2}Covers:?\*{0,2}\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)


@dataclass
class DriftResult:
    dangling: list[tuple[str, str]] = field(default_factory=list)  # (doc, missing ref/glob)
    stale: list[tuple[str, str]] = field(default_factory=list)     # (doc, detail)
    git_available: bool = False

    @property
    def any(self) -> bool:
        return bool(self.dangling or self.stale)


def find_drift(config: Config) -> DriftResult:
    root = config.project_root
    arch = root / "architecture"
    result = DriftResult(git_available=_git_available(root))
    if not arch.is_dir():
        return result

    source_files = _source_files(config)  # relative posix paths, for robust ref resolution

    for doc in sorted(arch.rglob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        text = doc.read_text()
        rel_doc = doc.relative_to(root).as_posix()
        refs = _file_refs(text)
        covers = _covers_globs(text)

        # absence: references / covers globs that resolve to nothing
        for ref in refs:
            if _resolve_ref(ref, root, source_files) is None:
                result.dangling.append((rel_doc, ref))
        for glob in covers:
            if not _glob_files(root, glob):
                result.dangling.append((rel_doc, f"{glob}  (Covers matches no files)"))

        # staleness: only subsystem docs describe code, and only when git can tell us
        if result.git_available and _is_subsystem(doc, arch):
            covered = _covered_files(root, covers, refs, source_files)
            newer = [f for f in covered if _committed_after(root, f, rel_doc)]
            if newer:
                shown = ", ".join(newer[:3]) + (f" (+{len(newer) - 3} more)" if len(newer) > 3 else "")
                result.stale.append((rel_doc, f"{len(newer)} covered file(s) changed after the doc: {shown}"))

    return result


# --- doc parsing ---------------------------------------------------------

def _file_refs(text: str) -> list[str]:
    """Backtick tokens that look like references to CODE files."""
    out: list[str] = []
    for tok in _BACKTICK.findall(text):
        t = tok.strip()
        if " " in t or not t.endswith(CODE_EXTS):
            continue
        if t not in out:
            out.append(t)
    return out


def _covers_globs(text: str) -> list[str]:
    globs: list[str] = []
    for m in _COVERS.finditer(text):
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
    """Return the actual root-relative path a doc reference points to, or None if it doesn't exist."""
    if (root / ref).exists():
        return ref
    r = ref.lstrip("./")
    if "/" in r:
        for sf in source_files:
            if sf == r or sf.endswith("/" + r):
                return sf
    else:
        for sf in source_files:
            if sf.rsplit("/", 1)[-1] == r:
                return sf
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


def _is_subsystem(doc: Path, arch: Path) -> bool:
    return doc.parent == arch / "subsystems"


# --- git -----------------------------------------------------------------

def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _git_available(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree") == "true"


def _last_commit_ts(root: Path, rel_path: str) -> int | None:
    out = _git(root, "log", "-1", "--format=%ct", "--", rel_path)
    return int(out) if out else None


def _committed_after(root: Path, file_rel: str, doc_rel: str) -> bool:
    ft, dt = _last_commit_ts(root, file_rel), _last_commit_ts(root, doc_rel)
    return ft is not None and dt is not None and ft > dt

"""`archagent status` — a repo-scale / coverage snapshot to size the describe work before starting.

`drift` reports raw undocumented-module *counts* as a flat wall of paths, which doesn't answer the question
a first `describe` pass actually has ("how big is this repo, and which package should I write next?"). This
groups the source tree by top-level package and reports, per package, how many code files a subsystem's
`**Covers:**` glob already claims — turning the existing signal into a prioritization tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .drift import _covers_globs, _glob_files, _is_subsystem, _source_files
from .mdutil import strip_code_fences


@dataclass
class PackageCoverage:
    name: str
    total: int           # code files in the package
    covered: int         # code files claimed by some **Covers:** glob (or an __init__.py)

    @property
    def pct(self) -> int:
        return round(100 * self.covered / self.total) if self.total else 0


@dataclass
class StatusReport:
    packages: list[PackageCoverage] = field(default_factory=list)
    subsystem_docs: int = 0        # how many subsystems/*.md docs exist (M)
    covers_declared: bool = False  # did any doc declare **Covers:**? (else covered counts are all 0)

    @property
    def total(self) -> int:
        return sum(p.total for p in self.packages)

    @property
    def covered(self) -> int:
        return sum(p.covered for p in self.packages)

    @property
    def documented_packages(self) -> int:
        return sum(1 for p in self.packages if p.covered)

    @property
    def pct(self) -> int:
        return round(100 * self.covered / self.total) if self.total else 0


def _source_prefixes(config: Config) -> list[str]:
    prefixes: list[str] = []
    for cfg in (config.python, config.ts):
        for sp in getattr(cfg, "source_paths", []) or []:
            prefixes.append(sp.strip("/") + "/")
    return prefixes


def _package_of(rel_path: str, prefixes: list[str]) -> str:
    """The top-level package a source file belongs to: the first path segment under its source root
    (e.g. `base/svc_a/mod.py` under source root `base` -> `svc_a`). A file directly in the source root
    has no package of its own -> `(root)`."""
    for prefix in prefixes:
        if rel_path.startswith(prefix):
            rest = rel_path[len(prefix):]
            return rest.split("/", 1)[0] if "/" in rest else "(root)"
    return rel_path.split("/", 1)[0] if "/" in rel_path else "(root)"


def status(config: Config) -> StatusReport:
    root = config.project_root
    arch = config.architecture_dir
    source_files = _source_files(config)
    prefixes = _source_prefixes(config)

    covered: set[str] = set()
    subsystem_docs = 0
    covers_declared = False
    if arch.is_dir():
        for doc in sorted(arch.rglob("*.md")):
            if doc.name.endswith("_TEMPLATE.md"):
                continue
            if _is_subsystem(doc, arch):
                subsystem_docs += 1
            text = strip_code_fences(doc.read_text())
            for glob in _covers_globs(text):
                covers_declared = True
                covered.update(_glob_files(root, glob))

    buckets: dict[str, list[int]] = {}  # package -> [total, covered]
    for f in source_files:
        pkg = _package_of(f, prefixes)
        b = buckets.setdefault(pkg, [0, 0])
        b[0] += 1
        # Mirror drift: an __init__.py is never "undocumented", so once coverage is declared it counts as
        # covered. With no **Covers:** at all, nothing is documented yet — don't inflate the count.
        if f in covered or (covers_declared and f.endswith("__init__.py")):
            b[1] += 1

    packages = [PackageCoverage(name=n, total=t, covered=c)
                for n, (t, c) in sorted(buckets.items(), key=lambda kv: (-kv[1][0], kv[0]))]
    return StatusReport(packages=packages, subsystem_docs=subsystem_docs, covers_declared=covers_declared)

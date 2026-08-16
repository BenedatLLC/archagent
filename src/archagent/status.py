"""`archagent status` — a repo-scale / coverage snapshot to size the describe work before starting.

`drift` reports raw undocumented-module *counts* as a flat wall of paths, which doesn't answer the question
a first `describe` pass actually has ("how big is this repo, and which package should I write next?"). This
groups the source tree by top-level package and reports, per package, how many code files a subsystem's
`**Covers:**` glob already claims — turning the existing signal into a prioritization tool.
"""

from __future__ import annotations

import re
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
class SubsystemDepth:
    """How much a subsystem document actually says about the code it claims.

    Coverage answers "is this code described by *something*". It says nothing about whether the
    description is usable, and the two come apart: an artifact scored 100% coverage while a reader found
    three of its documents too thin to trace a change through. This is the second half of the question
    `status` was written to answer — the docstring already claims it shows an author where the artifact
    is thin, and until now it only showed where the artifact was *absent*.
    """
    name: str
    files: int            # code files its **Covers:** globs claim
    words: int            # prose words, excluding metadata lines, code fences and tables
    diagrams: int         # mermaid blocks
    types: int            # type/table/class declarations in the code it covers

    @property
    def words_per_file(self) -> float:
        return self.words / self.files if self.files else 0.0

    @property
    def wants_a_diagram(self) -> bool:
        """Its subject is a set of relationships and it has drawn none.

        Not "every document needs a diagram" — a CLI with no states was right to say a lifecycle diagram
        would be decoration. But a document covering many type or table declarations is describing how
        they relate, and prose about relationships is where a reader gives up.
        """
        return self.diagrams == 0 and self.types >= 5


@dataclass
class StatusReport:
    packages: list[PackageCoverage] = field(default_factory=list)
    subsystem_docs: int = 0        # how many subsystems/*.md docs exist (M)
    depth: list["SubsystemDepth"] = field(default_factory=list)
    covers_declared: bool = False  # did any doc declare **Covers:**? (else covered counts are all 0)

    @property
    def total(self) -> int:
        return sum(p.total for p in self.packages)

    @property
    def covered(self) -> int:
        return sum(p.covered for p in self.packages)

    @property
    def thin(self) -> list["SubsystemDepth"]:
        """Documents well below the artifact's own median density.

        Relative, not absolute: a terse house style is a style, and a fixed words-per-file bar would
        punish it everywhere. What is informative is one document being markedly thinner than its
        siblings, which is a claim about this artifact rather than about prose in general.
        """
        rated = [d for d in self.depth if d.files]
        if len(rated) < 3:
            return []
        ranked = sorted(d.words_per_file for d in rated)
        median = ranked[len(ranked) // 2]
        return [d for d in rated if d.words_per_file < median * 0.5]

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


#: A type, table or class declaration — what a document covering many of them has to relate to each other.
_TYPE_DECL = re.compile(
    r"^\s*(?:class\s+\w+|__tablename__\s*=|"
    r"export\s+(?:interface|type|enum|class)\s+\w+|interface\s+\w+\s*\{)", re.MULTILINE)


def _prose_words(text: str) -> int:
    """Words a reader actually reads: metadata lines, fenced code and table rows are not prose.

    Counting them would let a document look substantial by listing its own `**Covers:**` globs and a
    twenty-row table, which is the shape the thin documents already had.
    """
    out, in_fence = 0, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or s.startswith(("|", "#", "**Covers:", "**Connects:", "**Tier:", "**Service:")):
            continue
        out += len(s.split())
    return out


def _subsystem_depth(config: Config, arch: Path, root: Path) -> list[SubsystemDepth]:
    subs = arch / "subsystems"
    if not subs.is_dir():
        return []
    out: list[SubsystemDepth] = []
    for doc in sorted(subs.glob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        text = doc.read_text(errors="replace")
        stripped = strip_code_fences(text)
        files: set[str] = set()
        for glob in _covers_globs(stripped):
            files.update(_glob_files(root, glob))
        types = 0
        for rel in files:
            try:
                types += len(_TYPE_DECL.findall((root / rel).read_text(errors="replace")))
            except OSError:
                pass
        out.append(SubsystemDepth(name=doc.stem, files=len(files), words=_prose_words(text),
                                  diagrams=text.count("```mermaid"), types=types))
    return out


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
    report = StatusReport(packages=packages, subsystem_docs=subsystem_docs,
                          covers_declared=covers_declared)
    report.depth = _subsystem_depth(config, arch, root)
    return report

"""Which assigned code the documents actually *describe* — the completeness half of coverage.

`status` answers *is this file claimed by a subsystem*. That is assignment, and a `**Covers:**` glob
proves it. It does not answer whether the document that claims a file says anything about it, and the two
diverge in the direction that matters: an artifact can report 100% coverage while a whole cross-cutting
mechanism goes unmentioned.

Calibration round 4 is the worked example. `paperless-ngx` scored 727/727 assigned and 1.00 on the
deterministic rubric, and the human reviewer found three things sitting inside a glob and never described:
django-cachalot, an optional whole-ORM read cache that changes staleness reasoning in the permission and
search paths the artifact documents in detail; `documents/schema.py`, the public API's OpenAPI
customisation; and 137 test files counted in the coverage figure with no document describing the test
architecture. The reviewer found the first by running `grep -r cachalot architecture/` and getting nothing.
That grep is this module.

**Every accuracy instrument this project has is saturated** — fresh artifacts score 0.88 to 1.00 on
per-item checklists across three targets, because `describe` is accurate. What it is not is uniformly
*deep*, and depth is where the remaining headroom is. This measures it without a judge.

**Mention is a proxy, and a weak one taken alone.** A module named once in a table row is not described.
The mitigations are to weight by size — an unmentioned 800-line module is a finding, a 12-line `__init__`
is not — and to report units rather than a score, so a reader judges the list instead of a number judging
them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import Config

#: A floor low enough to keep a pure re-export out and nothing else, because **size turned out to be a bad
#: proxy for significance**. The first version used 40 lines and thereby excluded the most important
#: completeness finding of calibration round 4: `paperless/db_cache.py` is **17 lines** and wires an
#: optional whole-ORM Redis read cache into `INSTALLED_APPS`, changing staleness reasoning across the
#: permission and search paths. Meanwhile the largest findings by line count were Angular form components
#: the artifact deliberately describes as a group.
#:
#: So the list is not ranked by size. It is grouped by package and left for a reader to judge, which is the
#: honest shape for a proxy this rough.
MIN_LINES = 10

#: Directories whose contents are described collectively or not at all: migrations are generated, tests are
#: a subject in their own right (and *that* absence is reported separately), locales are data.
_SKIP_DIRS = {"migrations", "locale", "locales", "__pycache__", "node_modules", "messages"}
_TEST_DIRS = {"test", "tests", "__tests__", "testdata", "fixtures", "e2e"}

#: Only code is a subject. The first run against a real repository listed `package-lock.json`, `styles.scss`
#: and `theme.scss` among its largest findings, which says nothing about whether the architecture is
#: described.
_CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".kt", ".rs")

#: A directory holding at least this many source files is a *group*, and an artifact that describes the
#: group has described its members. Round 4's artifact covers 216 Angular components by directory, base
#: class and pattern — deliberately, and it says so — and demanding a sentence per component would push
#: `describe` toward exactly the inventory the prose criterion penalises. Without this the check reported
#: 154 findings of which the great majority were components in described directories.
GROUP_SIZE = 5

#: A group is a directory of sibling components deep in a tree, not a top-level package. Without this,
#: `src/paperless` — cited in passing by any file:line reference — credited every module inside it,
#: including the 17-line `db_cache.py` that round 4's reviewer found undescribed.
_GROUP_DEPTH = 3

#: A stem shorter than this carries no information — `a`, `db`, `ui` appear inside ordinary words and
#: would match any prose. Such a module has to be named by its path to count as described.
_MIN_STEM = 3
_TEST_FILE = re.compile(r"(^|[._-])(test|spec)s?[._]")

#: Prose that treats testing as a subject rather than mentioning the word. Named tools and named artefacts
#: only: a bare "test" appears in every artifact ever written, so matching it would make this always pass.
#: `\btest` also misses `pytest`, which was the first thing this got wrong.
_TESTS_AS_A_SUBJECT = re.compile(
    r"pytest|conftest|vitest|\bjest\b|playwright|test suite|test harness|test architecture|"
    r"testing strategy|test fixtures|factory.boy|factories", re.IGNORECASE)


@dataclass(frozen=True)
class Undescribed:
    path: str                      # repo-relative
    lines: int
    subsystem: str                 # the doc whose Covers glob claims it, or "" if none

    def __str__(self) -> str:
        where = f" (claimed by {self.subsystem})" if self.subsystem else ""
        return f"{self.path}  {self.lines} lines{where}"


@dataclass
class DescribedReport:
    considered: int = 0                       # modules over the size bar, excluding tests and generated
    mentioned: int = 0
    grouped: int = 0                          # mentioned only via a described directory of siblings
    undescribed: list[Undescribed] = None     # sorted, largest first
    tests_described: bool = True              # does any document discuss the test suite at all?
    test_files: int = 0

    def __post_init__(self) -> None:
        if self.undescribed is None:
            self.undescribed = []

    @property
    def pct(self) -> int:
        return round(100 * self.mentioned / self.considered) if self.considered else 0

    @property
    def undescribed_lines(self) -> int:
        return sum(u.lines for u in self.undescribed)

    def by_package(self) -> dict[str, list[Undescribed]]:
        """Findings grouped by their top two path segments.

        `src/paperless: 3 modules` is a thing a reader acts on. Eighty-three modules sorted by line count
        is a thing a reader scrolls past, and the ranking was misleading anyway — see `MIN_LINES`.
        """
        out: dict[str, list[Undescribed]] = {}
        for u in self.undescribed:
            parts = PurePosixPath(u.path).parts
            out.setdefault("/".join(parts[:2]) if len(parts) > 1 else parts[0], []).append(u)
        return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


def _is_test(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    return bool(set(parts) & _TEST_DIRS) or bool(_TEST_FILE.search(PurePosixPath(rel).name))


def _skip(rel: str) -> bool:
    return bool(set(PurePosixPath(rel).parts) & _SKIP_DIRS)


def _mentions(prose: str, rel: str) -> bool:
    """Is this module named in the documents?

    Three spellings count, because all three are how a document legitimately refers to a module: the path
    (`src/paperless/db_cache.py`), the stem (`db_cache`), and the dotted import path (`paperless.db_cache`).
    A stem alone is the loosest, and it is deliberately allowed — a document writing "the `db_cache` key
    generators" has described the module, and demanding a full path would fire on good prose.
    """
    p = PurePosixPath(rel)
    stem = p.stem
    if stem in ("__init__", "index", "main"):          # named by their directory, not themselves
        stem = p.parent.name
    dotted = ".".join(p.with_suffix("").parts[-2:])
    if rel in prose:
        return True
    # Word boundaries, not substrings. A substring test let a module named `a.py` match the letter "a"
    # inside "named", and would let `api` match "rapid" — every short module name silently passing is a
    # false *negative*, which is the direction that makes a completeness check useless.
    for s in (stem, dotted):
        if len(s) >= _MIN_STEM and re.search(rf"\b{re.escape(s)}\b", prose):
            return True
    return False


def _described_as_a_group(prose: str, rel: str, siblings: dict[str, int]) -> bool:
    """Is this file a member of a directory the documents describe collectively?

    Only for directories big enough to be a group — one unmentioned module beside two siblings is a gap,
    one of thirty components in a described directory is not.
    """
    p = PurePosixPath(rel)
    for parent in list(p.parents)[:2]:                 # the directory and its parent
        d = parent.as_posix()
        if siblings.get(d, 0) < GROUP_SIZE or len(parent.parts) < _GROUP_DEPTH:
            continue
        # The directory must be named *as a path*. A bare name is far too loose: `src/paperless` is a
        # large directory and the word "paperless" appears in every paragraph, which credited every
        # module in the backend — including the one the round-4 reviewer found undescribed.
        tail = "/".join(parent.parts[-2:])
        if d in prose or (len(parent.parts) >= 2 and tail in prose):
            return True
    return False


#: The metadata lines are the *assignment*. Reading them as prose makes this circular — every covered file
#: is "mentioned" by the glob that covers it, which is precisely the claim being tested. Same exclusion
#: `status._prose_words` already applies when measuring density.
_METADATA_LINE = re.compile(r"^\s*\*\*(Covers|Connects|Tier|Service|Config)\s*:", re.IGNORECASE)


def artifact_prose(arch: Path) -> str:
    """Everything a reader reads, with the metadata declarations removed."""
    parts = []
    for doc in sorted(arch.rglob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        try:
            text = doc.read_text(errors="replace")
        except OSError:
            continue
        keep, skipping = [], False
        for line in text.splitlines():
            if _METADATA_LINE.match(line):
                skipping = True
                continue
            # a declaration wraps; it ends at a blank line or the next field
            if skipping and (not line.strip() or line.lstrip().startswith(("**", "#"))):
                skipping = False
            if not skipping:
                keep.append(line)
        parts.append("\n".join(keep))
    return "\n".join(parts)


def described(config: Config, source_files: set[str], claimed_by: dict[str, str] | None = None
              ) -> DescribedReport:
    """Modules assigned to a subsystem that no document mentions.

    `claimed_by` maps a repo-relative path to the subsystem doc that covers it, when the caller knows it;
    it only enriches the report.
    """
    arch = config.architecture_dir
    report = DescribedReport()
    if not arch.is_dir():
        return report
    prose = artifact_prose(arch)
    root = config.project_root
    claimed_by = claimed_by or {}

    siblings: dict[str, int] = {}
    for rel in source_files:
        if rel.endswith(_CODE_EXTS):
            siblings[PurePosixPath(rel).parent.as_posix()] = \
                siblings.get(PurePosixPath(rel).parent.as_posix(), 0) + 1

    for rel in sorted(source_files):
        if _skip(rel) or not rel.endswith(_CODE_EXTS):
            continue
        if _is_test(rel):
            report.test_files += 1
            continue
        try:
            lines = len((root / rel).read_text(errors="replace").splitlines())
        except OSError:
            continue
        if lines < MIN_LINES:
            continue
        report.considered += 1
        if _mentions(prose, rel):
            report.mentioned += 1
        elif _described_as_a_group(prose, rel, siblings):
            report.mentioned += 1
            report.grouped += 1
        else:
            report.undescribed.append(Undescribed(rel, lines, claimed_by.get(rel, "")))

    report.undescribed.sort(key=lambda u: u.path)
    # A suite of hundreds of files that no document discusses is one finding, not hundreds. Reported
    # separately for that reason: round 4 counted 137 test files toward 100% coverage while no document
    # described the test architecture at all.
    report.tests_described = report.test_files == 0 or bool(_TESTS_AS_A_SUBJECT.search(prose))
    return report

"""Check B — scattered single source of truth: one decision re-implemented across several files.

The shape being hunted: a set of domain values that *should* be resolved in one place (`{pending, paid,
shipped, refunded}`, a list of provider names, a set of job states) but is instead branched on in five
different files, which then drift apart. Nothing structural is wrong — the files may sit in the same
subsystem and may already import each other for other reasons — so the dependency graph is blind to it.

An earlier plan mined recurring words out of bug-fix commit *messages*. On real repositories that mostly
rediscovered each subsystem's own subject matter ("commits about forms mention 'form'"), so it was dropped.
The reliable signal is in the **code**: a value set that is demonstrably duplicated. Commit history is kept,
but only to *rank* — a duplicated decision whose files barely change is a curiosity, one whose files churn
constantly is a running cost (probe-results.md, experiments 2 and 2b).

The pipeline, all deterministic:

  1. per file, collect the literals it *branches on* (`== "x"`, `case "x"`, `in ("x", "y")`)
  2. per subsystem, keep values branched on in several files, and cluster values that keep co-occurring
  3. keep only **tight** clusters — some file must branch on most of the set. That file is the likely owner;
     the others hold pieces. Loose clusters are grab-bags of common strings, and this is what kills them.
  4. rank by the churn of the files involved

What survives is a *candidate*. Adapters, database backends, and plugin families legitimately branch on the
same values in parallel; the scan surfaces them and the reviewer dismisses them. That is the intended
division of labour — the code finds facts, the model judges them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hotspots import is_excluded, looks_generated

MIN_FILES_PER_VALUE = 3     # a value must be branched on in this many files to be a duplication at all
MIN_SHARED_FILES = 2        # two values join a cluster when this many files branch on both
MIN_CLUSTER_VALUES = 3      # below this, a "decision" is just a pair like {create, edit}
TIGHTNESS = 0.6             # some file must branch on this share of the cluster's values (the owner)
MIN_REIMPLEMENTORS = 2      # ... and this many other files must hold a piece of it
MIN_PIECE = 2               # a file counts as a re-implementor at this many of the cluster's values
_MAX_VALUES_PER_FILE = 200  # a file this broad is a table or a test fixture, not one decision

_CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".kt", ".rs")

# A branched-on literal, in the forms that survive across languages without a parser.
_EQ = re.compile(r"""[=!]=\s*(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")
_EQ_REV = re.compile(r"""(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)\s*[=!]=""")
_CASE = re.compile(r"""\bcase\s+(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")
# membership: `in ("a", "b")` / `in ['a', 'b']` / `in {'a', 'b'}` — the literals are pulled out separately
_IN_SET = re.compile(r"""\bin\s*[\(\[\{]([^)\]\}\n]{4,300})[\)\]\}]""")
_LITERAL = re.compile(r"""(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")

_VALUE_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")
# Values that are branched on everywhere and decide nothing about *this* system's domain.
_STOPVALUES = {
    "true", "false", "none", "null", "nil", "undefined", "yes", "no", "on", "off",
    "utf-8", "utf8", "ascii", "latin-1", "str", "int", "float", "bool", "list", "dict", "object",
    "string", "number", "boolean", "array", "function", "type", "name", "id", "key", "value",
    "http", "https", "get", "post", "put", "patch", "delete", "head", "options",
    "win32", "darwin", "linux", "posix", "nt", "utf-16", "ignore", "strict", "replace",
    "__main__", "__init__", "self", "cls", "args", "kwargs",
}
_COMMENT = re.compile(r"^\s*(#|//|\*|/\*)")


@dataclass
class Decision:
    """A candidate duplicated decision within one subsystem."""

    subsystem: str
    values: list[str]
    owner: str                              # the file branching on most of the value set
    owner_coverage: float                   # share of the set the owner branches on
    files: dict[str, int] = field(default_factory=dict)   # file -> how many of the values it branches on
    churn: int = 0                          # total commits across the involved files
    fix_churn: int = 0                      # of those, fix-labeled

    @property
    def reimplementors(self) -> list[str]:
        return sorted(f for f in self.files if f != self.owner)


def branch_values(text: str) -> set[str]:
    """The domain literals a file branches on — equality tests, `case` arms, membership sets."""
    values: set[str] = set()
    for line in text.splitlines():
        if _COMMENT.match(line):
            continue
        for rx in (_EQ, _EQ_REV, _CASE):
            for m in rx.finditer(line):
                values.add(m.group("v"))
        for m in _IN_SET.finditer(line):
            for lit in _LITERAL.finditer(m.group(1)):
                values.add(lit.group("v"))
    return {v for v in values if _keep(v)}


def _keep(v: str) -> bool:
    v = v.strip()
    return bool(v) and v.lower() not in _STOPVALUES and bool(_VALUE_OK.match(v)) and not v.isdigit()


def scan_files(root, files: set[str]) -> dict[str, set[str]]:
    """`file -> branched-on values`, skipping vendored, generated, and non-code files."""
    out: dict[str, set[str]] = {}
    for rel in sorted(files):
        if not rel.endswith(_CODE_EXTS) or is_excluded(rel):
            continue
        try:
            text = (root / rel).read_text(errors="replace")
        except OSError:
            continue
        if looks_generated(text):
            continue
        vals = branch_values(text)
        if vals:
            out[rel] = vals
    return out


class _Union:
    """Union-find over values, so a chain of pairwise co-occurrences becomes one decision."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def cluster(
    per_file: dict[str, set[str]],
    subsystem: str = "",
    min_files: int = MIN_FILES_PER_VALUE,
    min_shared: int = MIN_SHARED_FILES,
    min_values: int = MIN_CLUSTER_VALUES,
    tightness: float = TIGHTNESS,
) -> list[Decision]:
    """Group co-occurring duplicated values into candidate decisions, keeping only the tight ones."""
    value_files: dict[str, set[str]] = {}
    for rel, vals in per_file.items():
        for v in vals:
            value_files.setdefault(v, set()).add(rel)
    duplicated = {v: fs for v, fs in value_files.items() if len(fs) >= min_files}
    if len(duplicated) < min_values:
        return []

    # Co-occurrence is counted by walking files, not by comparing every pair of values: only pairs that
    # actually appear together are ever considered, which keeps this near-linear on real repos.
    ordered = sorted(duplicated)
    co: dict[tuple[str, str], int] = {}
    for rel, vals in per_file.items():
        mine = sorted(v for v in vals if v in duplicated)
        if len(mine) > _MAX_VALUES_PER_FILE:
            continue  # a file branching on hundreds of duplicated values links everything to everything
        for i, a in enumerate(mine):
            for b in mine[i + 1:]:
                co[(a, b)] = co.get((a, b), 0) + 1

    uf = _Union()
    for v in ordered:
        uf.find(v)
    for (a, b), n in co.items():
        if n >= min_shared:
            uf.union(a, b)

    groups: dict[str, list[str]] = {}
    for v in ordered:
        groups.setdefault(uf.find(v), []).append(v)

    out: list[Decision] = []
    for values in groups.values():
        if len(values) < min_values:
            continue
        vset = set(values)
        # how much of the decision each involved file holds
        coverage = {
            rel: len(vals & vset) for rel, vals in per_file.items() if vals & vset
        }
        owner, held = max(coverage.items(), key=lambda kv: (kv[1], -len(kv[0])))
        owner_cov = held / len(values)
        if owner_cov < tightness:
            continue  # a grab-bag of common strings: nobody owns the whole set
        pieces = [rel for rel, n in coverage.items() if rel != owner and n >= MIN_PIECE]
        if len(pieces) < MIN_REIMPLEMENTORS:
            continue
        out.append(Decision(
            subsystem=subsystem, values=sorted(values), owner=owner,
            owner_coverage=round(owner_cov, 2),
            files={rel: coverage[rel] for rel in [owner, *sorted(pieces)]},
        ))
    return out


def find_decisions(
    root,
    file_groups: dict[str, set[str]],
    churn: dict[str, int] | None = None,
    fix_churn: dict[str, int] | None = None,
) -> list[Decision]:
    """Candidate duplicated decisions across every group, ranked by the churn of the files involved.

    `file_groups` maps a group name to its files — subsystems when the architecture docs define them,
    top-level directories otherwise. Duplication is looked for *within* a group: the same value set
    appearing in two unrelated subsystems is usually coincidence, not one decision torn in half.
    """
    churn = churn or {}
    fix_churn = fix_churn or {}
    out: list[Decision] = []
    for group in sorted(file_groups):
        per_file = scan_files(root, file_groups[group])
        for d in cluster(per_file, subsystem=group):
            d.churn = sum(churn.get(f, 0) for f in d.files)
            d.fix_churn = sum(fix_churn.get(f, 0) for f in d.files)
            out.append(d)
    out.sort(key=lambda d: (-d.churn, -d.fix_churn, -len(d.values), d.owner))
    return out

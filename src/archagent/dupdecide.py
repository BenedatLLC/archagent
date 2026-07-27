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

A second detector lives at the bottom of this module: `find_enum_escapes`. Where the scan above *infers*
the decision and its owner, an enum *declares* both — which makes a sharper question answerable, and is the
"never calls the owner" idea of the design's Appendix A.
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
# Union-find only needs a *chain* to merge values into one "decision": a co-occurs with b, b with c, and
# a and c are joined although they never appear together. A real decision is denser than a chain — most
# pairs of its values genuinely co-occur. Measured over the labelled clusters of the evaluation pass:
# every confirmed finding scored >= 0.67, while the two grab-bags scored 0.26 and 0.57 (a 23-value
# opencode cluster mixing message roles, session status, error names and the JS `typeof` results).
COHESION = 0.6
_MAX_VALUES_PER_FILE = 200  # a file this broad is a table or a test fixture, not one decision

_CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".kt", ".rs")

# A branched-on literal, in the forms that survive across languages without a parser.
_EQ = re.compile(r"""[=!]=\s*(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")
_EQ_REV = re.compile(r"""(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)\s*[=!]=""")
_CASE = re.compile(r"""\bcase\s+(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")
# Ruby's `when "x"`, and the arm form Rust (`match`) and Kotlin (`when`) share: a literal opening the
# line, then `=>` or `->`. Anchoring at the line start keeps it away from JS arrow functions and object
# literals, which never lead with a bare quoted string followed by an arrow.
_WHEN = re.compile(r"""\bwhen\s+(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")
_ARM = re.compile(r"""^\s*(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)\s*(?:=>|->)""")
# Java/Kotlin compare strings with `.equals(...)`, not `==`
_EQUALS = re.compile(r"""\.equals\(\s*(?P<q>['"])(?P<v>[^'"\n]{2,40})(?P=q)""")
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
    # DOM `KeyboardEvent.key` names. Several UI components each handling their own keys is ordinary
    # event handling, not one decision torn apart — and the vocabulary belongs to the platform, not to
    # this system, so no file here could be its owner. (Deliberately not `home`, `end`, `delete` or
    # `space`, which are as often domain words as key names.)
    "arrowup", "arrowdown", "arrowleft", "arrowright", "escape", "enter", "tab", "backspace",
    "capslock", "pageup", "pagedown", "shift", "control", "alt", "meta",
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
    cohesion: float = 1.0                   # share of the value pairs that actually co-occur
    churn: int = 0                          # total commits across the involved files
    fix_churn: int = 0                      # of those, fix-labeled

    @property
    def reimplementors(self) -> list[str]:
        return sorted(f for f in self.files if f != self.owner)


def _line_branch_values(line: str) -> set[str]:
    values: set[str] = set()
    for rx in (_EQ, _EQ_REV, _CASE, _WHEN, _ARM, _EQUALS):
        for m in rx.finditer(line):
            values.add(m.group("v"))
    for m in _IN_SET.finditer(line):
        for lit in _LITERAL.finditer(m.group(1)):
            values.add(lit.group("v"))
    return values


def branch_values(text: str) -> set[str]:
    """The domain literals a file branches on — equality tests, `case` arms, membership sets."""
    values: set[str] = set()
    for line in text.splitlines():
        if _COMMENT.match(line):
            continue
        values |= _line_branch_values(line)
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
    cohesion: float = COHESION,
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
        dense = _cohesion(values, co, min_shared)
        if dense < cohesion:
            continue  # a chain of coincidences that union-find strung together, not one decision
        out.append(Decision(
            subsystem=subsystem, values=sorted(values), owner=owner,
            owner_coverage=round(owner_cov, 2), cohesion=round(dense, 2),
            files={rel: coverage[rel] for rel in [owner, *sorted(pieces)]},
        ))
    return out


def _cohesion(values: list[str], co: dict[tuple[str, str], int], min_shared: int) -> float:
    """Share of the cluster's value pairs that actually co-occur — 1.0 for a clique, low for a chain."""
    pairs = len(values) * (len(values) - 1) // 2
    if pairs == 0:
        return 1.0
    linked = sum(
        1
        for i, a in enumerate(values)
        for b in values[i + 1:]
        if max(co.get((a, b), 0), co.get((b, a), 0)) >= min_shared
    )
    return linked / pairs


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


# --- the enum-value escape: a declared owner bypassed by its own serialized values ---------
#
# The duplication scan above infers the decision from co-occurrence. When the project has already
# *declared* one — an enum — the owner is not a guess, and a sharper question becomes answerable:
# does anyone re-decide it by comparing against the enum's raw string values instead of calling the
# owner? That is the "never calls the owner" detector of the design's Appendix A, arriving through a
# door the clustering scan can't use.
#
# Found in the wild on the first repo it was pointed at: a `WorkflowState` enum with a full set of
# transition methods beside it, and one file asking `current_state.value == "summarized"` five times.
# The clustering scan cannot see that — the enum's values are *assigned* in the definer and only
# *compared* in one other file, so they never reach the "branched on in >= 3 files" bar.

# Precision knobs, all set by measuring false alarms on real repos. The failure mode is a *word
# collision*: LiteLLM has a `Role` enum containing "system", and a hundred files compare an API
# payload's `role` field to "system" without knowing that enum exists. Requiring either several of
# the enum's members or a real share of them separates "re-deciding this enum" from "using a word
# that happens to be one of its values".
MIN_ESCAPED_VALUES = 3      # this many distinct members escaped in one file is enough on its own
MIN_PAIR_COVERAGE = 0.5     # ... or two, if they are at least this share of the whole enum

_ENUM_BASE = re.compile(r"\b(?:Enum|IntEnum|StrEnum|Flag|IntFlag)\b")
_PY_CLASS = re.compile(r"^(?P<indent>[ \t]*)class\s+(?P<name>\w+)\s*\((?P<bases>[^)]*)\)\s*:")
_PY_MEMBER = re.compile(
    r"""^[ \t]+(?P<member>[A-Za-z_]\w*)\s*(?::[^=\n]+)?=\s*(?P<q>['"])(?P<v>[^'"\n]+)(?P=q)""")
_TS_ENUM = re.compile(r"\benum\s+(?P<name>\w+)\s*\{(?P<body>[^}]*)\}", re.DOTALL)
_TS_MEMBER = re.compile(r"""(?P<member>\w+)\s*=\s*(?P<q>['"`])(?P<v>[^'"`\n]+)(?P=q)""")
# `state.value == "x"` — the enum object is in hand and deliberately unwrapped, which is close to
# conclusive. Two guards, both learned from false alarms: it must be *adjacent to the comparison*
# (a bare `.value` anywhere on the line matches every other line of a Vue codebase, where `.value`
# reads a ref), and it only counts in Python, where `.value` is how you unwrap an enum member. In
# TypeScript `.value` is an ordinary property name — Vue compares a Babel AST node's `key.value`
# against `'set'`, which has nothing to do with the `TriggerOpTypes` enum that also has a `set`.
# Which language a file belongs to. An enum can only be *imported* by files in its own language, so
# whether the escapers share the definer's language changes what the fix even is.
_LANG_BY_EXT = {
    ".py": "python",
    ".ts": "ts", ".tsx": "ts", ".js": "ts", ".jsx": "ts", ".mjs": "ts", ".cjs": "ts",
    ".go": "go", ".rb": "ruby", ".java": "jvm", ".kt": "jvm", ".rs": "rust",
}
_UNWRAPPED = re.compile(r"""\.value\s*(?:[=!]=|\bin\b|\bnot\s+in\b)|[=!]=\s*[\w.\[\]()'"]*\.value\b""")


@dataclass
class EnumDef:
    name: str
    file: str
    members: dict[str, str] = field(default_factory=dict)   # member name -> its string value


@dataclass
class EnumEscape:
    """An enum whose string values are compared directly, outside the file that declares it."""

    enum: str
    definer: str
    escapes: dict[str, list[tuple[int, str]]] = field(default_factory=dict)  # file -> [(line, value)]
    unwrapped: set[str] = field(default_factory=set)   # files using the `.value` idiom
    churn: int = 0
    fix_churn: int = 0

    @property
    def files(self) -> list[str]:
        return sorted(self.escapes)

    @property
    def definer_lang(self) -> str:
        return language_of(self.definer)

    @property
    def cross_language(self) -> list[str]:
        """Escapers written in a different language from the enum.

        These cannot be fixed by importing the enum — no import crosses the boundary — so the finding
        has to recommend something else. Measured on OpenHands: five of nine escapes were a Python enum
        with TypeScript escapers, three of them exclusively so.
        """
        return sorted(f for f in self.escapes if language_of(f) != self.definer_lang)

    @property
    def same_language(self) -> list[str]:
        return sorted(f for f in self.escapes if language_of(f) == self.definer_lang)

    @property
    def values(self) -> list[str]:
        return sorted({v for hits in self.escapes.values() for _, v in hits})


def language_of(rel: str) -> str:
    """The language family of a path, or "" when unrecognized."""
    dot = rel.rfind(".")
    return _LANG_BY_EXT.get(rel[dot:], "") if dot != -1 else ""


def type_checked(rel: str) -> bool:
    """Whether a compiler already guards this file's literal comparisons.

    `tsc` reports TS2367 on a comparison between a typed value and a literal that is not one of its
    members — verified for string enums, union types, `as const` unions, and `switch` arms alike. So a
    stale string in TypeScript cannot survive a build *when the compared value is typed*, and an escape
    there is only a real risk where the value arrives untyped (a `string`/`any` field off an API
    response, or an event declared with literal unions rather than the enum). Python has no equivalent
    check, and plain JavaScript has no checker at all — hence `.ts`/`.tsx` only.
    """
    return rel.endswith((".ts", ".tsx"))


def enum_defs(root, files: set[str]) -> list[EnumDef]:
    """Every string-valued enum the project declares. Auto-numbered and `auto()` members are skipped:
    only a member with a string value can be escaped by a string comparison.

    **Python and TypeScript/JavaScript only.** Go has no enum construct at all (its `const` blocks are
    a different shape), and Java/Kotlin enum bodies carry constructor arguments this parser does not
    read. Files in other languages are still scanned for *escapes* — they just cannot declare an owner.
    """
    out: list[EnumDef] = []
    for rel in sorted(files):
        if not rel.endswith(_CODE_EXTS) or is_excluded(rel):
            continue
        try:
            text = (root / rel).read_text(errors="replace")
        except OSError:
            continue
        out += _py_enums(rel, text) if rel.endswith(".py") else _ts_enums(rel, text)
    return [d for d in out if d.members]


def _py_enums(rel: str, text: str) -> list[EnumDef]:
    lines = text.splitlines()
    out: list[EnumDef] = []
    for i, line in enumerate(lines):
        m = _PY_CLASS.match(line)
        if not m or not _ENUM_BASE.search(m.group("bases")):
            continue
        indent = len(m.group("indent").expandtabs(4))
        members: dict[str, str] = {}
        for body in lines[i + 1:]:
            if body.strip() and len(body.expandtabs(4)) - len(body.expandtabs(4).lstrip()) <= indent:
                break  # dedented out of the class body
            mm = _PY_MEMBER.match(body)
            if mm:
                members[mm.group("member")] = mm.group("v")
        out.append(EnumDef(name=m.group("name"), file=rel, members=members))
    return out


def _ts_enums(rel: str, text: str) -> list[EnumDef]:
    return [
        EnumDef(name=m.group("name"), file=rel,
                members={x.group("member"): x.group("v") for x in _TS_MEMBER.finditer(m.group("body"))})
        for m in _TS_ENUM.finditer(text)
    ]


def find_enum_escapes(
    root,
    files: set[str],
    churn: dict[str, int] | None = None,
    fix_churn: dict[str, int] | None = None,
) -> list[EnumEscape]:
    """Files that branch on an enum's raw string values instead of on the enum itself.

    A value claimed by two different enums is dropped — it can't be attributed, and guessing would
    manufacture findings. A file is only reported when it escapes several of one enum's values, or
    when it uses the `.value` idiom, which says outright that the enum object was in hand.
    """
    churn, fix_churn = churn or {}, fix_churn or {}
    defs = enum_defs(root, files)
    owner: dict[str, EnumDef | None] = {}
    for d in defs:
        for v in d.members.values():
            if not _keep(v):
                continue
            owner[v] = None if v in owner and owner[v] is not d else d
    claimed = {v: d for v, d in owner.items() if d is not None}
    if not claimed:
        return []

    found: dict[str, EnumEscape] = {}
    for rel in sorted(files):
        if not rel.endswith(_CODE_EXTS) or is_excluded(rel):
            continue
        try:
            text = (root / rel).read_text(errors="replace")
        except OSError:
            continue
        if looks_generated(text):
            continue
        per_enum: dict[str, list[tuple[int, str]]] = {}
        unwrapped: set[str] = set()
        for lineno, line in enumerate(text.splitlines(), 1):
            if _COMMENT.match(line):
                continue
            for v in _line_branch_values(line):
                d = claimed.get(v)
                if d is None or d.file == rel:
                    continue  # unknown value, or the enum's own declaring file
                per_enum.setdefault(d.name, []).append((lineno, v))
                if rel.endswith(".py") and _UNWRAPPED.search(line):
                    unwrapped.add(d.name)
        for name, hits in per_enum.items():
            d = next(x for x in defs if x.name == name)
            distinct = len({v for _, v in hits})
            coverage = distinct / len(d.members)
            strong = name in unwrapped
            if not (strong or distinct >= MIN_ESCAPED_VALUES
                    or (distinct >= 2 and coverage >= MIN_PAIR_COVERAGE)):
                continue  # too few of the enum's members to be anything but a word collision
            esc = found.setdefault(name, EnumEscape(enum=name, definer=d.file))
            esc.escapes[rel] = sorted(hits)
            if name in unwrapped:
                esc.unwrapped.add(rel)

    out = list(found.values())
    for esc in out:
        esc.churn = sum(churn.get(f, 0) for f in esc.escapes)
        esc.fix_churn = sum(fix_churn.get(f, 0) for f in esc.escapes)
    out.sort(key=lambda e: (-e.churn, -len(e.escapes), e.enum))
    return out

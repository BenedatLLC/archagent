"""Scan docs and code for **stated invariants** — the candidate generator for issue #3.

`describe` should enforce the invariants a team already wrote down. This module makes the *enumeration*
deterministic (process, not luck): it greps design/spec docs and source code for invariant statements and
emits a candidate list — the agent then classifies each into the DSL, verifies it with `check`, and curates
(exactly the `evaluate` shape: deterministic candidates → judgment).

Three precision tiers, and the split between the first two is the correction issue #40 forced:
- **markers** — an explicit `INVARIANT` / `@invariant` / `Invariant:` label, or a contract decorator
  (`@require`/`@ensure`/`@deal`). Someone wrote the word; whether the rule is *architectural* is still a
  judgement.
- **assertions** — the message on an `assert`, in non-test code only. It sometimes states intent
  ("Cannot mix named and unnamed arguments") and often just names a value. In a test file the message is
  the *test's* failure text rather than a stated rule, which is how `response`, `123, 456` and
  `Transfer-Encoding` were once reported as high-confidence invariants on httpx.
- **modal** (docs only) — normative language (MUST / NEVER / ALWAYS / "only X may") that is often but not
  always an invariant; the agent must judge.

Confidence here is about *detection*, never about the statement being an architectural rule. Reporting
the first as though it were the second is what the old "high confidence" heading did.

Purely static: it reads text, never executes. It classifies nothing on its own — the `guess` is a hint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .configscan import is_test_path
from .drift import _source_files

_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv", ".mypy_cache", "architecture"}
_DOC_EXTS = (".md", ".markdown", ".rst", ".txt")
_SPEC_DIRS = ("designs", "design", "rfcs", "adr", "adrs", "spec", "specs", "docs")

# explicit invariant markers (high precision) — case-sensitive INVARIANT is the common code convention
_MARKER = re.compile(r"\bINVARIANT\b|\bInvariant\s*:|@invariant\b|@require\b|@ensure\b|@deal\.")
# an assertion carrying a message — the message states the intent
_ASSERT_MSG = re.compile(r"""\bassert\b[^,\n]+,\s*['"]([^'"]{4,})['"]""")
# normative / modal language (high recall, low precision) — docs only
_MODAL = re.compile(
    r"\bmust\s+not\b|\bmust\s+never\b|\bmust\b|\bshall\s+not\b|\bshall\b|\balways\b|\bnever\b"
    r"|\bshould\s+never\b|\bis\s+guaranteed\s+to\b|\bguaranteed\s+to\b|\bexactly\s+one\b"
    r"|\bonly\b[^.\n]{0,40}?\b(?:may|can|must)\b",  # "only <…> may/can/must" (allow a few words between)
    re.IGNORECASE,
)


@dataclass
class Candidate:
    source: str          # repo-relative "path:line"
    text: str            # the matched line/message (trimmed)
    kind: str            # "marker" | "modal"
    confidence: str      # "high" | "low"
    guess: str           # a coarse DSL-tier hint: BOUNDARY | STRUCTURAL | PBT | prose


def scan_invariants(config: Config) -> list[Candidate]:
    root = config.project_root
    out: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    def add(rel: str, lineno: int, text: str, kind: str, conf: str):
        t = text.strip()[:160]
        key = (f"{rel}:{lineno}", t)
        if t and key not in seen:
            seen.add(key)
            out.append(Candidate(f"{rel}:{lineno}", t, kind, conf, _guess(t)))

    # code: explicit markers + assertion messages only (modal words are too noisy in code)
    #
    # The two are not equal evidence, and treating them as one produced most of the noise round 2's user
    # tester complained about (#40). An `INVARIANT:` marker is someone declaring a rule. An assertion
    # message is whatever text explains a failure — in a test, that is the *test's* failure text, not a
    # stated architectural rule, which is how `response`, `123, 456` and `Transfer-Encoding` came to be
    # listed as high-confidence invariants on httpx.
    #
    # So the marker keeps its confidence everywhere, including in tests, where `# INVARIANT:` still means
    # what it says. The assertion message is dropped in test files and demoted elsewhere.
    for rel in sorted(_source_files(config)):
        in_test = is_test_path(rel)
        for lineno, line in _lines(root, rel):
            if _MARKER.search(line):
                add(rel, lineno, line, "marker", "high")
                continue
            m = _ASSERT_MSG.search(line)
            if m and not in_test:
                add(rel, lineno, m.group(1), "assertion", "low")

    # docs: markers (high) + modal language (low)
    for rel in _doc_files(root, config.arch_dir):
        for lineno, line in _lines(root, rel):
            if _MARKER.search(line):
                add(rel, lineno, line, "marker", "high")
            elif _MODAL.search(line):
                add(rel, lineno, line, "modal", "low")
    return out


def _guess(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(import|imports|depend|dependenc|access|reach)\w*\b", t) and \
       re.search(r"(must not|only|never|forbid|not\s+import)", t):
        return "BOUNDARY"
    if re.search(r"\b(call|use|print|log|instantiat|construct|getenv|os\.environ|process\.env)\w*\b", t):
        return "STRUCTURAL"
    if re.search(r"\b(sort|order|always|state|reset|guarante|idempotent|exactly one|unique|preserv)\w*\b", t):
        return "PBT"
    return "prose"


def _doc_files(root: Path, arch_dir: str = "architecture") -> list[str]:
    """Doc files worth scanning: root-level markdown (README/AGENTS/CLAUDE + siblings) and everything under
    the recognized design/spec directories, minus our own architecture artifact (`arch_dir`)."""
    arch_prefix = arch_dir.strip("/") + "/"
    files: list[str] = []
    for p in root.glob("*"):
        if p.is_file() and p.suffix.lower() in _DOC_EXTS:
            files.append(p.relative_to(root).as_posix())
    for d in _SPEC_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and p.suffix.lower() in _DOC_EXTS \
                    and not rel.startswith(arch_prefix) \
                    and not any(part in _SKIP_DIRS for part in p.parts):
                files.append(rel)
    return sorted(dict.fromkeys(files))


def _lines(root: Path, rel: str):
    try:
        text = (root / rel).read_text()
    except OSError:
        return
    for lineno, line in enumerate(text.splitlines(), 1):
        yield lineno, line

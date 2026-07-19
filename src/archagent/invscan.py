"""Scan docs and code for **stated invariants** — the candidate generator for issue #3.

`describe` should enforce the invariants a team already wrote down. This module makes the *enumeration*
deterministic (process, not luck): it greps design/spec docs and source code for invariant statements and
emits a candidate list — the agent then classifies each into the DSL, verifies it with `check`, and curates
(exactly the `evaluate` shape: deterministic candidates → judgment).

Two precision tiers:
- **markers** (high confidence) — explicit `INVARIANT` / `@invariant` / `Invariant:` labels, assertion
  messages, and contract decorators (`@require`/`@ensure`/`@deal`).
- **modal** (low confidence, docs only) — normative language (MUST / NEVER / ALWAYS / "only X may") that is
  often but not always an invariant; the agent must judge.

Purely static: it reads text, never executes. It classifies nothing on its own — the `guess` is a hint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
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
    for rel in sorted(_source_files(config)):
        for lineno, line in _lines(root, rel):
            if _MARKER.search(line):
                add(rel, lineno, line, "marker", "high")
            m = _ASSERT_MSG.search(line)
            if m:
                add(rel, lineno, m.group(1), "marker", "high")

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

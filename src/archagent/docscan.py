"""`archagent lint-docs` — a deterministic linter for the Mermaid diagrams the describe skill writes.

`archagent check` only exercises the invariants table; the prose Mermaid blocks in the subsystem docs have
no gate at all, so a malformed diagram surfaces only when a human (or GitHub/VS Code) tries to render it.
This module extracts every ```` ```mermaid ```` block under the architecture dir and applies a few cheap,
low-false-positive checks — no Node, no headless renderer required, so it runs out of the box.

The checks target the classes of error actually seen in the wild:
  - `unterminated-block` — a ```` ```mermaid ```` fence with no closing fence.
  - `empty-block` — a fenced block with no diagram content.
  - `unknown-diagram` — the first content line isn't a recognised diagram directive (catches typos like
    `stateDiagramv2`).
  - `state-label-colon` — a `stateDiagram(-v2)` transition label (`A --> B : text`) with a *second* colon.
    Mermaid treats everything after the first `:` as the label; a second `:` (a port `:5300`, a time
    `10:30`, a ratio) breaks the parser. This is the specific, well-known gotcha worth naming.

It also checks **invariant-ID integrity across documents**, which is not about Mermaid but belongs to the
same job: catching what `check` structurally cannot. `check` reads `invariants.md` and nothing else, so a
subsystem document is free to cite an ID that does not exist, or to attach a different rule to one that
does. Calibration round 4 produced both in one artifact — a doc presenting `PAR-001` as a table row when
the rule is `BND-006`, and `UI-002` meaning one thing in the table and something unrelated in a subsystem
doc. A reader chasing either lands nowhere, and every existing check passes.

  - `unknown-invariant-id` — an ID cited in a subsystem doc with no matching row in `invariants.md`.

**The other half of that defect is not checked, deliberately.** `UI-002` meant one thing in the table and
something unrelated in a subsystem doc, and a check for it was built and then removed. Comparing the words
of a citation against the words of its row cannot tell "restated in other words" from "describes something
different": a DSL row (`forbid a -> b`) names modules where the prose names concepts, so they share no
vocabulary however faithful the restatement is; and a row that only cross-references another rule has no
rule text to compare. Three successive narrowings left it at three false positives out of four findings.
A check at that rate gets switched off, and switching one off is worse than never having it. Detecting a
redefined ID needs a reader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config

# Diagram directives Mermaid recognises as the first token of a block. Kept generous so a valid-but-unusual
# diagram type isn't flagged; the point is to catch typos, not to police which diagrams are allowed.
_DIAGRAM_DIRECTIVES = (
    "graph", "flowchart", "sequencediagram", "statediagram", "statediagram-v2", "classdiagram",
    "erdiagram", "journey", "gantt", "pie", "gitgraph", "mindmap", "timeline", "quadrantchart",
    "requirementdiagram", "c4context", "c4container", "c4component", "c4dynamic", "c4deployment",
    "sankey-beta", "xychart-beta", "block-beta", "packet-beta", "architecture-beta",
)
_TRANSITION = re.compile(r"-->")


@dataclass
class MermaidBlock:
    start_line: int          # 1-based line of the ```mermaid fence
    lines: list[str]         # content lines between the fences
    terminated: bool


@dataclass
class DocIssue:
    doc: str                 # repo-relative doc path
    line: int                # 1-based line in the doc
    code: str                # machine-readable issue kind
    message: str


def extract_mermaid_blocks(text: str) -> list[MermaidBlock]:
    """Every ```` ```mermaid ```` fenced block in `text`, with its 1-based fence line and content."""
    blocks: list[MermaidBlock] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.fullmatch(r"(```+|~~~+)\s*mermaid\s*", stripped, re.IGNORECASE):
            fence = "```" if stripped.startswith("`") else "~~~"
            start = i + 1  # 1-based fence line
            body: list[str] = []
            i += 1
            terminated = False
            while i < len(lines):
                if lines[i].strip().startswith(fence):
                    terminated = True
                    break
                body.append(lines[i])
                i += 1
            blocks.append(MermaidBlock(start_line=start, lines=body, terminated=terminated))
        i += 1
    return blocks


def lint_block(block: MermaidBlock) -> list[tuple[int, str, str]]:
    """Issues for one block as (1-based-doc-line, code, message). Line is relative to the whole doc."""
    issues: list[tuple[int, str, str]] = []
    if not block.terminated:
        issues.append((block.start_line, "unterminated-block",
                       "```mermaid block is never closed with a matching fence"))
        return issues  # can't trust the rest of an unterminated block
    content = [(n, ln) for n, ln in enumerate(block.lines) if ln.strip()]
    if not content:
        issues.append((block.start_line, "empty-block", "mermaid block has no diagram content"))
        return issues

    first_off, first_line = content[0]
    directive = first_line.strip().split()[0].split(":", 1)[0].lower()
    if directive not in _DIAGRAM_DIRECTIVES:
        issues.append((block.start_line + 1 + first_off, "unknown-diagram",
                       f"first line '{first_line.strip()[:40]}' is not a recognised Mermaid diagram type"))

    is_state = directive.startswith("statediagram")
    if is_state:
        for off, raw in content[1:]:
            if not _TRANSITION.search(raw) or ":" not in raw:
                continue
            label = raw.split(":", 1)[1]
            if ":" in label:
                issues.append((block.start_line + 1 + off, "state-label-colon",
                               "stateDiagram transition label contains a second ':' — everything after the "
                               "first ':' is the label and a second ':' breaks the parser (write 'port 5300', "
                               "not 'on :5300')"))
    return issues


def lint_text(text: str, doc: str = "") -> list[DocIssue]:
    """Lint every Mermaid block in one document's text."""
    out: list[DocIssue] = []
    for block in extract_mermaid_blocks(text):
        for line, code, msg in lint_block(block):
            out.append(DocIssue(doc=doc, line=line, code=code, message=msg))
    return out


#: `ABC-001` — the ID shape the ADL uses. Bounded deliberately: a looser pattern matches version strings,
#: HTTP codes and Mermaid node names.
_INV_ID = re.compile(r"\b([A-Z][A-Z0-9]{1,7}-\d{3})\b")

def _invariant_rows(text: str) -> dict[str, str]:
    """`{ID: rule text}` from the invariants table. The Rule column is the fifth cell."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        m = _INV_ID.fullmatch(cells[0])
        if m:
            rows[cells[0]] = cells[4]
    return rows


def lint_invariant_ids(arch: Path, root: Path | None = None) -> list[DocIssue]:
    """IDs cited in subsystem docs against the rows in `invariants.md`.

    `doc` paths are relative to `root`, matching the Mermaid issues — the CLI groups findings by `doc`,
    and two conventions in one list silently split one file into two groups.
    """
    root = root or arch
    table = arch / "invariants.md"
    if not table.is_file():
        return []
    try:
        rows = _invariant_rows(table.read_text())
    except OSError:
        return []
    if not rows:
        return []

    issues: list[DocIssue] = []
    for doc in sorted(arch.rglob("*.md")):
        if doc.name.endswith("_TEMPLATE.md") or doc.name == "invariants.md":
            continue
        try:
            lines = doc.read_text().splitlines()
        except OSError:
            continue
        rel = doc.relative_to(root).as_posix()
        for n, line in enumerate(lines, 1):
            for cid in set(_INV_ID.findall(line)):
                if cid not in rows:
                    issues.append(DocIssue(
                        doc=rel, line=n, code="unknown-invariant-id",
                        message=f"{cid} is cited here but has no row in invariants.md"))
                    continue
    return issues


def lint_docs(config: Config) -> list[DocIssue]:
    """Lint every Mermaid block in every `.md` under the architecture dir (skipping the template)."""
    arch = config.architecture_dir
    root = config.project_root
    issues: list[DocIssue] = []
    if not arch.is_dir():
        return issues
    for doc in sorted(arch.rglob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        try:
            text = doc.read_text()
        except OSError:
            continue
        rel = doc.relative_to(root).as_posix()
        issues.extend(lint_text(text, rel))
    issues.extend(lint_invariant_ids(arch, root))
    return issues

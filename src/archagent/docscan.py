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
    return issues

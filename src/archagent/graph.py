"""`archagent graph` — generate a Mermaid system map from the subsystem metadata.

Every subsystem doc already declares its outgoing `**Connects:**` edges (typed by connector kind) plus an
optional `**Tier:**`; those are parsed deterministically for `drift`/`evaluate`. This turns the same data
into a single Mermaid `flowchart` — one node per subsystem, one edge per declared connector — so the system
diagram is generated from the metadata instead of hand-drawn (and re-drawn) every time an edge changes.

`--write` splices the block into `index.md` between the `<!-- archagent:graph -->` markers (idempotent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .drift import _connectors, _service_of
from .mdutil import is_empty_value, strip_code_fences

GRAPH_START = "<!-- archagent:graph -->"
GRAPH_END = "<!-- /archagent:graph -->"

_TIER = re.compile(r"^\s*\*\*\s*Tier\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# per-kind edge arrow: solid for synchronous/blocking coupling, dotted for asynchronous/loose
_ARROW = {"import": "-->", "sync-call": "-->", "shared-data": "-->", "async-event": "-.->", "pipe": "-.->"}


@dataclass
class Subsystem:
    name: str
    tier: str | None
    connectors: dict[str, str]  # target -> kind


def _tier_of(text: str) -> str | None:
    m = _TIER.search(text)
    if not m or is_empty_value(m.group(1)):
        return None
    return re.split(r"[\s,|]+", m.group(1).strip())[0].strip("`") or None


def collect_subsystems(config: Config) -> list[Subsystem]:
    arch = config.architecture_dir
    subs: list[Subsystem] = []
    sub_dir = arch / "subsystems"
    if not sub_dir.is_dir():
        return subs
    for doc in sorted(sub_dir.glob("*.md")):
        if doc.name.endswith("_TEMPLATE.md"):
            continue
        text = strip_code_fences(doc.read_text())
        subs.append(Subsystem(name=doc.stem, tier=_tier_of(text), connectors=_connectors(text) or {}))
    return subs


def _node_id(name: str) -> str:
    nid = re.sub(r"[^0-9A-Za-z_]", "_", name)
    return nid if nid and not nid[0].isdigit() else f"n_{nid}"


def build_mermaid(subs: list[Subsystem]) -> str:
    """A Mermaid `flowchart LR` for the subsystems and their declared connectors (no code fences)."""
    if not subs:
        return "flowchart LR\n    %% no subsystems documented yet"
    known = {s.name for s in subs}
    lines = ["flowchart LR"]
    for s in sorted(subs, key=lambda x: x.name):
        label = f"{s.name}<br/><i>{s.tier}</i>" if s.tier else s.name
        lines.append(f'    {_node_id(s.name)}["{label}"]')
    edges: list[str] = []
    for s in sorted(subs, key=lambda x: x.name):
        for target, kind in sorted(s.connectors.items()):
            if target not in known:  # skip edges to non-subsystems (services / externals)
                continue
            arrow = _ARROW.get(kind, "-->")
            edges.append(f"    {_node_id(s.name)} {arrow}|{kind}| {_node_id(target)}")
    if edges:
        lines.append("")
        lines.extend(edges)
    return "\n".join(lines)


def graph_block(config: Config) -> str:
    """The fenced Mermaid block ready to drop into a Markdown doc."""
    mermaid = build_mermaid(collect_subsystems(config))
    return f"```mermaid\n{mermaid}\n```"


def _wrapped(block: str) -> str:
    return f"{GRAPH_START}\n{block}\n{GRAPH_END}"


def write_to_index(config: Config, block: str) -> str:
    """Splice the fenced block into index.md between the markers. Returns the action taken.

    If the markers exist, replace what's between them. If not, insert a `## System map` section with markers
    after the title line. Idempotent: re-running replaces the block in place."""
    index = config.architecture_dir / "index.md"
    if not index.exists():
        raise ValueError(f"{index} does not exist — run `archagent init` first")
    text = index.read_text()
    wrapped = _wrapped(block)
    if GRAPH_START in text and GRAPH_END in text:
        new = re.sub(re.escape(GRAPH_START) + r".*?" + re.escape(GRAPH_END), lambda _: wrapped, text, count=1, flags=re.DOTALL)
        action = "updated"
    else:
        lines = text.splitlines()
        insert_at = 1 if lines and lines[0].startswith("#") else 0
        section = ["", "## System map", wrapped, ""]
        new = "\n".join(lines[:insert_at] + section + lines[insert_at:])
        action = "inserted"
    if not new.endswith("\n"):
        new += "\n"
    index.write_text(new)
    return action

"""`archagent graph` — generate a Mermaid system map from the subsystem metadata.

Every subsystem doc already declares its outgoing `**Connects:**` edges (typed by connector kind) plus an
optional `**Tier:**`; those are parsed deterministically for `drift`/`evaluate`. This turns the same data
into a single Mermaid `flowchart` — one node per subsystem, one edge per declared connector — so the system
diagram is generated from the metadata instead of hand-drawn (and re-drawn) every time an edge changes.

`--write` splices the block into the artifact's `README.md` between the `<!-- archagent:graph -->`
markers (idempotent), and refreshes the provenance stamp beside it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .drift import _connectors, _git, _service_of
from .mdutil import is_empty_value, strip_code_fences
from .tiers import tier_of as _tier_of

GRAPH_START = "<!-- archagent:graph -->"
GRAPH_END = "<!-- /archagent:graph -->"
CAPTION_START = "<!-- archagent:graph-caption -->"
CAPTION_END = "<!-- /archagent:graph-caption -->"

#: What a caption looks like before anyone has written one. Deliberately obvious, so an artifact that
#: never filled it in is visible rather than merely uncaptioned.
CAPTION_PLACEHOLDER = "_What to notice: (unwritten — say what this map shows about **this** system.)_"


def _caption_block(existing: str | None = None) -> str:
    return f"{CAPTION_START}\n{existing or CAPTION_PLACEHOLDER}\n{CAPTION_END}"

_TIER = re.compile(r"^\s*\*\*\s*Tier\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# per-kind edge arrow: solid for synchronous/blocking coupling, dotted for asynchronous/loose
_ARROW = {"import": "-->", "sync-call": "-->", "shared-data": "-->", "async-event": "-.->", "pipe": "-.->"}


@dataclass
class Subsystem:
    name: str
    tier: str | None
    connectors: dict[str, str]  # target -> kind




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


def _existing_caption(text: str) -> str | None:
    """Whatever a person already wrote between the caption markers, so a re-run never discards it."""
    m = re.search(re.escape(CAPTION_START) + r"\n(.*?)\n" + re.escape(CAPTION_END), text, re.DOTALL)
    body = m.group(1).strip() if m else None
    return body or None


PROV_START = "<!-- archagent:provenance -->"
PROV_END = "<!-- /archagent:provenance -->"


def provenance_block(config: Config) -> str:
    """What produced this artifact, as a generated line rather than an authored one.

    A reader who lands on the artifact in a browser wants one thing first: *is this current?* The version
    and the revision answer it approximately, and nothing else in the directory does — `log.md` has the
    full record but reading it is a second step.

    **Generated, because a hand-written one is guaranteed to be wrong.** Issue #18 is a list of authored
    facts that drifted: "55 imports" was 58, "19 concrete models" was 20, "all sixteen management commands"
    was fifteen. A hand-maintained version string is the same defect in its quietest form — nothing ever
    prompts anyone to update it.

    The revision is the repository's HEAD *when this ran*, so it necessarily predates the commit that
    carries the stamp. That off-by-one is inherent and harmless: the number that matters is how far behind
    the artifact has fallen, and one commit is not it.

    No date. Git already shows a reader when the file last changed, and a date would make every re-run a
    diff without adding anything the revision does not already say.
    """
    from .version import __version__
    rev = _head(config.project_root)
    at = f" · repository at `{rev}`" if rev else ""
    return (f"_Generated by **archagent {__version__}**{at}. "
            f"Refresh with `archagent graph --write`._")


def _head(root: Path) -> str:
    """Via `drift._git`, not a subprocess call of our own.

    STR-004 caught the first version of this the moment it was written: one module owns the git plumbing
    (ADR 0003), so `--until` and the timeout policy land in one place instead of being re-decided here.
    """
    return (_git(root, "rev-parse", "--short", "HEAD") or "").strip()


def _splice(text: str, start: str, end: str, body: str) -> str | None:
    """Replace what is between two markers, or None if they are not both present."""
    if start not in text or end not in text:
        return None
    return re.sub(re.escape(start) + r".*?" + re.escape(end),
                  lambda _: f"{start}\n{body}\n{end}", text, count=1, flags=re.DOTALL)


def write_to_index(config: Config, block: str) -> str:
    """Splice the fenced block into the artifact's `README.md` between the markers, and refresh the
    provenance stamp. Returns the action taken.

    If the markers exist, replace what's between them. If not, insert a `## System map` section with markers
    after the title line. Idempotent: re-running replaces the block in place.

    **`README.md`, not `index.md`** (issue #28). GitHub and every comparable forge render `README.md` when
    a reader opens a directory and render nothing otherwise, so the artifact's entry document was the one
    file a browsing reader never saw. Switched outright rather than aliased: pre-1.0 is when a rename is
    free, and carrying two names for one document would need explaining forever.
    """
    index = config.architecture_dir / "README.md"
    if not index.exists():
        raise ValueError(f"{index} does not exist — run `archagent init` first")
    text = index.read_text()
    wrapped = _wrapped(block)
    # The caption lives OUTSIDE the replaced region. The generated map is the artifact's most prominent
    # diagram and was the one with nowhere to put a caption, while the prompt demands one everywhere
    # else (issue #11). Keeping it outside means a re-run refreshes the graph and never eats the
    # sentence someone wrote about it.
    existing = _existing_caption(text)
    if GRAPH_START in text and GRAPH_END in text:
        new = re.sub(re.escape(GRAPH_START) + r".*?" + re.escape(GRAPH_END), lambda _: wrapped, text, count=1, flags=re.DOTALL)
        action = "updated"
        if CAPTION_START not in new:
            new = new.replace(wrapped, wrapped + "\n\n" + _caption_block(existing), 1)
    else:
        lines = text.splitlines()
        insert_at = 1 if lines and lines[0].startswith("#") else 0
        section = ["", "## System map", wrapped, "", _caption_block(), ""]
        new = "\n".join(lines[:insert_at] + section + lines[insert_at:])
        action = "inserted"
    stamped = _splice(new, PROV_START, PROV_END, provenance_block(config))
    if stamped is not None:
        new = stamped
    if not new.endswith("\n"):
        new += "\n"
    index.write_text(new)
    return action

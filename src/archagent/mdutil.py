"""Small Markdown helpers shared by the doc-metadata parsers.

The metadata parsers (Covers / Connects / Service / Tier / Config / Services) key on line-initial
`**Field:**` declarations. Two guards keep ordinary prose and diagrams from being mis-read as
declarations (see issue #1): `strip_code_fences` removes fenced code blocks (Mermaid diagrams, code
samples) before scanning, and `is_empty_value` recognises a "no declaration" placeholder (an empty /
`(none)` / `n/a` value) so an author's aside isn't tokenised into fake items.
"""

from __future__ import annotations

import re

_EMPTY_WORDS = {"none", "n/a", "na", "nil", "null", "tbd", "todo", ""}


def strip_code_fences(text: str) -> str:
    """Return `text` with fenced code blocks (```` ``` ```` or `~~~`) removed, so their contents are not
    scanned for `**Field:**` declarations. Fence lines and everything between a matching pair are dropped."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
            else:
                out.append(line)
        elif stripped.startswith(fence):
            fence = None
    return "\n".join(out)


def is_empty_value(value: str) -> bool:
    """True if a field value is a "no declaration" placeholder rather than a real list — empty, a
    parenthetical aside (`_(none — base of the graph)_`), or a `none`/`n/a`/`tbd` word. Prevents prose
    written into a metadata value from being tokenised into fake declarations."""
    v = value.strip().strip("_*`~ ").strip()
    if not v or v.startswith("("):
        return True
    first = re.split(r"[\s,]+", v, maxsplit=1)[0].strip("()_*`—–- ").lower()
    return first in _EMPTY_WORDS

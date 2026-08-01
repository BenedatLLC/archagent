"""Recorded investigations — what a finding turned out to *mean*, kept next to the code it is about.

`evaluate` produces candidates and rates them mechanically, by counting files and commits. An
investigation is the other half: someone read the code, traced whether anything actually breaks, and wrote
down what they found. That work is expensive and it must not evaporate — the next run should show the
verdict rather than re-inviting the same investigation, and the next person should start from the write-up
rather than from nothing.

**Investigations live in the architecture artifact**, under `<arch-dir>/investigations/`, and are meant to
be committed. They belong with the architecture documents rather than under `.archagent/`, which holds
configuration and generated output: an investigation is durable, human-facing prose about the system, of
the same kind as an ADR. The distinction from an ADR is that an ADR records a *decision* while an
investigation records an *analysis* — one that may lead to a decision, and a confirmed critical one
usually should, graduating into an ADR and often a `check` invariant.

The location follows the configured `architecture_dir`, so a project keeping its artifact at
`docs/architecture` gets `docs/architecture/investigations/`.

**A rating is a claim about consequence, not about counts.** The scale is deliberately about what happens,
not how much duplication there is:

- `minor` — untidy; nothing depends on the duplication, or a typo fails loudly.
- `moderate` — a real maintenance hazard; the copies can drift and nothing would catch it.
- `critical` — it already misbehaves, or a plausible edit makes it misbehave *silently*.

The first calibration round found exactly one critical among nineteen findings, where a drifted call-type
vocabulary had left a security hook scanning nothing and reporting success. Most were minor to moderate.
A scale that rated by duplication size would have inverted that.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RATINGS = ("minor", "moderate", "critical")
STORE = "investigations"      # relative to the configured architecture directory
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def evidence_hash(subjects: list[str], values: list[str] | None) -> str:
    """A fingerprint of what the finding was about when it was investigated.

    Wider than the finding id, which keys on the owner and value set alone: if the set of involved files
    changes, the investigation may no longer describe the finding in front of you. Better to say so than
    to present a stale verdict as current.
    """
    blob = "\x1f".join(sorted(subjects)) + "\x1e" + "\x1f".join(sorted(values or []))
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


@dataclass
class Investigation:
    finding: str
    rating: str
    by: str
    dated: str
    evidence: str
    body: str
    path: Path | None = None
    stale: bool = False        # set when the finding's evidence has moved since this was written

    @property
    def summary(self) -> str:
        """The first line of actual prose, for a one-line report entry.

        Headings are skipped: a write-up titled with the finding's own name would otherwise summarise
        itself as the thing the reader already knows.
        """
        for line in self.body.splitlines():
            s = line.strip()
            if not s or s.startswith(("#", "---", "|", "```")):
                continue
            return s[:160]
        return ""

    def to_dict(self) -> dict:
        return {"finding": self.finding, "rating": self.rating, "by": self.by, "dated": self.dated,
                "stale": self.stale, "path": str(self.path) if self.path else None,
                "summary": self.summary}


def _slug(finding_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", finding_id).strip("-")[:120]


def path_for(arch_dir: Path, finding_id: str) -> Path:
    return arch_dir / STORE / f"{_slug(finding_id)}.md"


def record(arch_dir: Path, finding_id: str, rating: str, body: str, by: str = "",
           subjects: list[str] | None = None, values: list[str] | None = None) -> Path:
    """Write an investigation. Refuses an unknown rating rather than storing a word nothing reads."""
    if rating not in RATINGS:
        raise ValueError(f"rating must be one of {', '.join(RATINGS)}; got {rating!r}")
    dest = path_for(arch_dir, finding_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    head = (f"---\nfinding: {finding_id}\nrating: {rating}\nby: {by or '(unrecorded)'}\n"
            f"date: {date.today().isoformat()}\n"
            f"evidence: {evidence_hash(subjects or [], values)}\n---\n\n")
    dest.write_text(head + body.strip() + "\n")
    return dest


def load(arch_dir: Path, finding_id: str, subjects: list[str] | None = None,
         values: list[str] | None = None) -> Investigation | None:
    p = path_for(arch_dir, finding_id)
    if not p.is_file():
        return None
    text = p.read_text(errors="replace")
    m = _FRONTMATTER.match(text)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    inv = Investigation(
        finding=meta.get("finding", finding_id), rating=meta.get("rating", ""),
        by=meta.get("by", ""), dated=meta.get("date", ""), evidence=meta.get("evidence", ""),
        body=text[m.end():], path=p)
    if subjects is not None and inv.evidence:
        inv.stale = inv.evidence != evidence_hash(subjects, values)
    return inv


def load_all(arch_dir: Path) -> list[Investigation]:
    d = arch_dir / STORE
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        text = p.read_text(errors="replace")
        m = _FRONTMATTER.match(text)
        if not m:
            continue
        meta = dict(
            (k.strip(), v.strip())
            for k, v in (line.split(":", 1) for line in m.group(1).splitlines() if ":" in line))
        out.append(Investigation(finding=meta.get("finding", p.stem), rating=meta.get("rating", ""),
                                 by=meta.get("by", ""), dated=meta.get("date", ""),
                                 evidence=meta.get("evidence", ""), body=text[m.end():], path=p))
    return out

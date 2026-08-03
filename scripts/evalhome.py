"""Where evaluation output goes.

Evaluation data lives in a separate private repository (`BenedatLLC/archagent-evaluations`) because it
grows without bound: every defect-study run adds per-repo flagged-file dumps, and every calibration round
adds a whole generated artifact. The tool's own repository should not carry that.

Resolution order, most explicit first:

1. ``$ARCHAGENT_EVAL_HOME`` — set it and everything writes there.
2. ``../archagent-evaluations/`` — the sibling checkout, if it exists. The ordinary case.
3. ``<repo>/evaluations/`` — a gitignored local working area.

Step 3 matters: a fresh clone with no data repo must still run the scripts rather than failing on a
missing directory, and its output must not land in git by accident. The directory is gitignored for
exactly that reason.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def eval_home() -> Path:
    env = os.environ.get("ARCHAGENT_EVAL_HOME")
    if env:
        return Path(env).expanduser().resolve()
    sibling = ROOT.parent / "archagent-evaluations"
    if sibling.is_dir():
        return sibling
    return ROOT / "evaluations"


def eval_dir(*parts: str) -> Path:
    """A subdirectory of the evaluation home, created on demand."""
    p = eval_home().joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p

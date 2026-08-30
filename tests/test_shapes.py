"""The shape matrix, run (issue #45).

One test per cell, so a failure names the idiom rather than saying "the graph is wrong". See
`tests/shapes.py` for the table and `docs/designs/extraction-confidence.md` for why it exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import _import_graph, _source_files
from shapes import SHAPES, Shape

DESIGN = Path(__file__).resolve().parents[1] / "docs" / "designs" / "extraction-confidence.md"


def _build(tmp_path: Path, shape: Shape) -> Config:
    (tmp_path / "architecture" / "subsystems").mkdir(parents=True)
    for rel, text in shape.files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return Config(
        project_root=tmp_path, languages=["python"],
        python=PythonConfig(root_package=shape.root_package, source_paths=list(shape.source_paths)),
        ts=TSConfig(source_paths=list(shape.source_paths)),
    )


def _nonempty(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    return {k: v for k, v in graph.items() if v}


@pytest.mark.parametrize("shape", SHAPES, ids=lambda s: s.name)
def test_shape(tmp_path, shape: Shape):
    """The graph this idiom produces, asserted completely.

    Complete rather than partial on purpose: a spurious edge is as much a defect as a missing one, and
    every bug this table pins produced one or the other. `#37` invented edges; `#41` and `#42` lost them.
    """
    cfg = _build(tmp_path, shape)
    files = _source_files(cfg)

    # An empty file set means the fixture never reached the extractor, and every assertion below would
    # then pass vacuously — the exact failure this table exists to catch, one level up.
    assert files, f"{shape.name}: no source files matched {shape.source_paths}"

    runtime = _nonempty(_import_graph(tmp_path, cfg, files))
    type_only = _nonempty(_import_graph(tmp_path, cfg, files, type_only=True))

    assert runtime == shape.runtime, f"runtime graph for {shape.name!r}"
    assert type_only == shape.type_only, f"type-only graph for {shape.name!r}"


@pytest.mark.parametrize("shape", [s for s in SHAPES if s.guessed_root_package],
                         ids=lambda s: s.name)
def test_shape_root_package_guess(tmp_path, shape: Shape):
    """Where the shape is about `init`'s guess rather than the graph.

    A wrong `root_package` scopes every BOUNDARY contract to a module set that does not exist, and
    `check` then reports that all invariants hold having examined none of them.
    """
    from archagent.init import describe_settings
    _build(tmp_path, shape)
    got = {s.key: s.value for s in describe_settings(tmp_path, ["python"], "architecture")}
    assert got["python.root_package"] == shape.guessed_root_package, shape.name


def test_every_shape_explains_why_it_is_here():
    """A cell with no note is a cell nobody can evaluate for removal later."""
    for s in SHAPES:
        assert s.note, f"{s.name} has no note"


def test_the_matrix_and_the_design_document_agree():
    """The design document's table is the checklist; this file is the implementation.

    Keeping them in sync by hand is exactly the scattered-source-of-truth shape the tool looks for, so it
    is asserted instead. A row added to the document without a fixture fails here — which is the point,
    since the document is where a shape gets proposed.
    """
    text = DESIGN.read_text()
    section = text[text.index("## The matrix, as it stands"):text.index("## What this does not replace")]
    documented = set()
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "| status |" in line:
            continue
        cell = line.split("|")[1].strip()
        cell = re.sub(r"\*\*(.*?)\*\*", r"\1", cell).strip()
        if cell and cell.lower() != "shape":
            documented.add(cell)

    implemented = {s.name for s in SHAPES}
    missing = documented - implemented
    extra = implemented - documented
    assert not missing, f"documented in the design with no fixture here: {sorted(missing)}"
    assert not extra, f"fixtures here with no row in the design: {sorted(extra)}"


def test_the_table_is_cheap_enough_to_be_the_default_instrument():
    """Not a performance test — a design constraint. The matrix earns its place by being runnable on
    every change, which the corpus is not: litellm alone is 132 MiB and a ~90-second git walk. If a cell
    ever needs a clone or a network call, it belongs in the corpus instead.
    """
    for s in SHAPES:
        assert all(len(v.splitlines()) < 15 for v in s.files.values()), f"{s.name} has a large fixture"
        assert len(s.files) <= 8, f"{s.name} has {len(s.files)} files; keep a cell small"

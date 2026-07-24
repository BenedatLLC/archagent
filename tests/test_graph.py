"""archagent graph — Mermaid system map generated from subsystem metadata."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.graph import (
    GRAPH_END,
    GRAPH_START,
    Subsystem,
    build_mermaid,
    collect_subsystems,
    graph_block,
    write_to_index,
)


def _cfg(tmp):
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(source_paths=["src"]), ts=TSConfig())


def _sub(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / name).write_text(text)


def test_build_mermaid_nodes_and_typed_edges():
    subs = [
        Subsystem("web", "ui", {"domain": "sync-call"}),
        Subsystem("domain", "domain", {"queue": "async-event"}),
        Subsystem("queue", "infra", {}),
    ]
    out = build_mermaid(subs)
    assert out.startswith("flowchart LR")
    assert 'web["web<br/><i>ui</i>"]' in out          # tier shown in label
    assert "web -->|sync-call| domain" in out         # solid arrow for sync coupling
    assert "domain -.->|async-event| queue" in out    # dotted for async


def test_edges_to_non_subsystems_skipped():
    subs = [Subsystem("web", None, {"stripe": "sync-call"})]  # stripe is not a documented subsystem
    out = build_mermaid(subs)
    assert "stripe" not in out


def test_collect_reads_docs(tmp_path):
    cfg = _cfg(tmp_path)
    _sub(cfg, "web.md", "# Web\n\n**Connects:** domain via sync-call\n**Tier:** ui\n")
    _sub(cfg, "domain.md", "# Domain\n\n**Tier:** domain\n")
    _sub(cfg, "_TEMPLATE.md", "# T\n\n**Connects:** x via import\n")  # skipped
    subs = {s.name: s for s in collect_subsystems(cfg)}
    assert set(subs) == {"web", "domain"}
    assert subs["web"].connectors == {"domain": "sync-call"}
    assert subs["web"].tier == "ui"


def test_write_to_index_replaces_between_markers_idempotently(tmp_path):
    cfg = _cfg(tmp_path)
    _sub(cfg, "web.md", "# Web\n\n**Connects:** domain via sync-call\n")
    _sub(cfg, "domain.md", "# Domain\n")
    index = cfg.architecture_dir / "index.md"
    index.write_text(f"# Index\n\n## System map\n{GRAPH_START}\n_placeholder_\n{GRAPH_END}\n\n## Subsystems\n")

    assert write_to_index(cfg, graph_block(cfg)) == "updated"
    once = index.read_text()
    assert "flowchart LR" in once
    assert "_placeholder_" not in once
    assert once.count(GRAPH_START) == 1 and once.count(GRAPH_END) == 1

    write_to_index(cfg, graph_block(cfg))   # re-run: still exactly one block
    twice = index.read_text()
    assert twice.count(GRAPH_START) == 1 and twice.count("flowchart LR") == 1


def test_write_to_index_inserts_section_when_no_markers(tmp_path):
    cfg = _cfg(tmp_path)
    _sub(cfg, "web.md", "# Web\n")
    index = cfg.architecture_dir / "index.md"
    index.write_text("# Architecture Index\n\n## Subsystems\n- web\n")
    assert write_to_index(cfg, graph_block(cfg)) == "inserted"
    text = index.read_text()
    assert GRAPH_START in text and "## System map" in text
    assert text.startswith("# Architecture Index")   # title kept first

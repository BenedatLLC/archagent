"""archagent lint-docs — the Mermaid diagram linter (docscan)."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.docscan import extract_mermaid_blocks, lint_docs, lint_text

GOOD = """# Doc

```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Active : starts
    Active --> [*]
```
"""

BAD_COLON = """# Doc

```mermaid
stateDiagram-v2
    Idle --> Running : on :5300
```
"""


def test_extract_finds_blocks_and_line():
    blocks = extract_mermaid_blocks(GOOD)
    assert len(blocks) == 1
    assert blocks[0].start_line == 3  # the ```mermaid fence line (1-based)
    assert blocks[0].terminated is True
    assert any("stateDiagram" in ln for ln in blocks[0].lines)


def test_good_diagram_has_no_issues():
    assert lint_text(GOOD) == []


def test_second_colon_in_state_label_is_flagged():
    issues = lint_text(BAD_COLON, doc="a.md")
    assert [i.code for i in issues] == ["state-label-colon"]
    assert issues[0].doc == "a.md"
    assert issues[0].line == 5  # the transition line


def test_colon_ok_in_sequence_diagram():
    # sequence-diagram messages are free text; a colon there is fine and must NOT be flagged
    txt = "```mermaid\nsequenceDiagram\n    A->>B: fetch http://x:8080/y\n```\n"
    assert lint_text(txt) == []


def test_empty_block_flagged():
    assert [i.code for i in lint_text("```mermaid\n```\n")] == ["empty-block"]


def test_unterminated_block_flagged():
    issues = lint_text("```mermaid\nflowchart LR\n    A --> B\n")
    assert [i.code for i in issues] == ["unterminated-block"]


def test_unknown_diagram_directive_flagged():
    issues = lint_text("```mermaid\nstateDiagramv2\n    A --> B\n```\n")  # missing hyphen
    assert [i.code for i in issues] == ["unknown-diagram"]


def test_non_mermaid_fences_ignored():
    assert lint_text("```python\nx = 1  # A --> B : a : b\n```\n") == []


def test_lint_docs_skips_template(tmp_path):
    arch = tmp_path / "architecture" / "subsystems"
    arch.mkdir(parents=True)
    (arch / "_TEMPLATE.md").write_text(BAD_COLON)   # template is not linted
    (arch / "svc.md").write_text(BAD_COLON)         # real doc is
    cfg = Config(project_root=tmp_path, languages=["python"],
                 python=PythonConfig(source_paths=["src"]), ts=TSConfig())
    issues = lint_docs(cfg)
    assert {i.doc for i in issues} == {"architecture/subsystems/svc.md"}

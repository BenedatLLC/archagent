"""`history-profile` must not learn archagent's own scaffolding as the project's vocabulary (#39).

From user test round 2. The profile's "domain terms" for httpx included `Columns` and `Record every
invariant as a row` — prose from archagent's shipped `invariants.md` template, which the tool had
scaffolded into the repository moments earlier and then read back as evidence about the target.

This is a feedback loop rather than a noisy heuristic, which is the reason it earns a test: it
strengthens as more scaffolding is present, `--write` caches the result, and it is invisible in the
output because the terms read as plausible.
"""

from pathlib import Path

from archagent.history import _domain_terms, _scaffold_terms

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "archagent" / "templates"


def test_the_shipped_templates_are_the_source_and_are_recognised():
    """A guard on the mechanism: if the templates stop using the `**Bold** —` style the exclusion set
    silently empties, and the contamination returns with nothing to notice it."""
    assert len(_scaffold_terms()) >= 5
    assert "Columns" in _scaffold_terms()


def test_scaffolded_prose_is_not_reported_as_project_vocabulary(tmp_path):
    """The reported case, reproduced by scaffolding the real template and reading it back."""
    arch = tmp_path / "architecture"
    (arch / "subsystems").mkdir(parents=True)
    (arch / "invariants.md").write_text((TEMPLATES / "architecture" / "invariants.md").read_text())
    (arch / "subsystems" / "transports.md").write_text("# transports\n")

    terms = _domain_terms(arch)
    assert "Columns" not in terms
    assert not any("Record every invariant" in t for t in terms)
    assert "transports" in terms, "the project's own subsystem names must survive"


def test_an_edited_template_is_still_recognised(tmp_path):
    """Subtracting terms rather than skipping whole files is the point. A user who edits `invariants.md`
    and leaves its preamble is the normal case, and a file-identity check would stop recognising it the
    moment they touched it."""
    arch = tmp_path / "architecture"
    arch.mkdir(parents=True)
    text = (TEMPLATES / "architecture" / "invariants.md").read_text()
    (arch / "invariants.md").write_text(text + "\n**Payment mode** — how a charge is captured.\n")

    terms = _domain_terms(arch)
    assert "Columns" not in terms, "still excluded although the file was edited"
    assert "Payment mode" in terms, "the author's own addition must survive"


def test_a_project_term_that_collides_with_a_template_term_is_accepted_as_lost(tmp_path):
    """Recorded rather than fixed. A project whose real glossary defines `Columns` loses that term. The
    alternative — trusting a term because the file was edited — restores the feedback loop, and a missing
    hint is cheaper than a cached fiction about the target's vocabulary."""
    arch = tmp_path / "architecture"
    arch.mkdir(parents=True)
    (arch / "glossary.md").write_text("**Columns** — a display concept in this product.\n")
    assert "Columns" not in _domain_terms(arch)

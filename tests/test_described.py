"""Assigned-but-undescribed modules — the completeness half of coverage.

The reason this exists at all: every accuracy instrument the project has is saturated. Fresh artifacts
score 0.88–1.00 on per-item checklists across three targets, so nothing measures the dimension where they
visibly fall short. The failures are silences, and a silence is exactly what a mention check finds.

The risk it carries is the one that has sunk two checks already: firing on prose that is fine. A module
described as part of a group, a small glue file, a generated migration — none of those is a finding, and a
list that is mostly noise gets switched off. Most of what follows tests the not-firing.
"""

from pathlib import Path

import pytest

from archagent.config import Config, PythonConfig, TSConfig
from archagent.described import MIN_LINES, described


def _project(tmp_path, docs: dict[str, str], code: dict[str, int | str]):
    arch = tmp_path / "architecture"
    (arch / "subsystems").mkdir(parents=True)
    for name, text in docs.items():
        (arch / name).write_text(text)
    for rel, body in code.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body if isinstance(body, str) else "x = 1\n" * body)
    cfg = Config(project_root=tmp_path, languages=["python"],
                 python=PythonConfig(root_package="app", source_paths=["src"]), ts=TSConfig())
    return cfg, set(code)


# --- what it must find ------------------------------------------------------------------------------

def test_a_substantial_module_no_document_names_is_reported(tmp_path):
    """Round 4's finding, reduced. `db_cache.py` sat inside a `**Covers:**` glob, contributed to a
    100%-coverage figure, and `grep -r cachalot architecture/` returned nothing."""
    cfg, files = _project(tmp_path,
                          {"index.md": "The platform subsystem holds settings and the database session."},
                          {"src/app/db_cache.py": 120, "src/app/settings.py": 200})
    r = described(cfg, files)
    assert [u.path for u in r.undescribed] == ["src/app/db_cache.py"]
    assert r.considered == 2 and r.mentioned == 1


def test_findings_are_grouped_by_package_not_ranked_by_size(tmp_path):
    """Size is a bad proxy for significance and the ranking said otherwise.

    Round 4's most important completeness gap was a 17-line module wiring a whole-ORM read cache; the
    largest unmentioned files were Angular form components the artifact describes as a group. So the
    report groups rather than ranks, and a reader judges the list.
    """
    cfg, files = _project(tmp_path, {"index.md": "Nothing named here."},
                          {"src/app/small.py": 50, "src/app/huge.py": 900, "web/ui/a.py": 200})
    groups = described(cfg, files).by_package()
    assert list(groups) == ["src/app", "web/ui"]
    assert len(groups["src/app"]) == 2


def test_a_test_suite_no_document_discusses_is_one_finding(tmp_path):
    """137 undescribed test files is one gap, not 137. Round 4 counted them toward 100% coverage while no
    document described the test architecture."""
    code = {f"src/app/tests/test_{i}.py": 80 for i in range(20)}
    code["src/app/core.py"] = 100
    cfg, files = _project(tmp_path, {"index.md": "The core module does the work."}, code)
    r = described(cfg, files)
    assert r.test_files == 20 and r.tests_described is False
    assert not [u for u in r.undescribed if "test" in u.path], "tests are counted separately, not listed"


def test_a_described_test_suite_is_not_a_finding(tmp_path):
    cfg, files = _project(
        tmp_path,
        {"index.md": "The core module does the work.",
         "subsystems/t.md": "The pytest suite layers conftest fixtures over a factory module."},
        {"src/app/tests/test_a.py": 80, "src/app/core.py": 100})
    assert described(cfg, files).tests_described is True


# --- what it must not fire on -----------------------------------------------------------------------

def test_a_module_named_by_its_stem_alone_counts_as_described(tmp_path):
    """"the `db_cache` key generators" describes the module. Demanding a full path would fire on prose
    that is doing its job."""
    cfg, files = _project(tmp_path, {"index.md": "The `db_cache` key generators live under platform."},
                          {"src/app/db_cache.py": 120})
    assert described(cfg, files).undescribed == []


def test_a_module_named_by_its_dotted_path_counts(tmp_path):
    cfg, files = _project(tmp_path, {"index.md": "`app.db_cache` supplies the key generators."},
                          {"src/app/db_cache.py": 120})
    assert described(cfg, files).undescribed == []


def test_glue_below_the_size_bar_is_not_required_to_be_named(tmp_path):
    """An `__init__` or a one-line re-export is not a subject. Requiring a mention would push `describe`
    toward writing inventories, which is the failure mode the whole prose half of the rubric fights."""
    cfg, files = _project(tmp_path, {"index.md": "Nothing named here."},
                          {"src/app/__init__.py": 3, "src/app/shim.py": MIN_LINES - 1})
    r = described(cfg, files)
    assert r.considered == 0 and r.undescribed == []


def test_generated_and_data_directories_are_skipped(tmp_path):
    """Migrations are generated and locales are data; neither is described module by module in any
    artifact worth reading."""
    cfg, files = _project(tmp_path, {"index.md": "Nothing named here."},
                          {"src/app/migrations/0001_initial.py": 300,
                           "src/app/locale/de/messages.py": 400})
    assert described(cfg, files).considered == 0


def test_an_init_is_matched_by_its_directory_name(tmp_path):
    """A package's `__init__` is named by the package. `settings/__init__.py` is described by prose about
    `settings`, and holding it to its own stem would flag every package in the tree."""
    cfg, files = _project(tmp_path, {"index.md": "Configuration lives in `settings`."},
                          {"src/app/settings/__init__.py": 300})
    assert described(cfg, files).undescribed == []


def test_the_percentage_is_none_of_the_story_when_nothing_qualifies(tmp_path):
    cfg, files = _project(tmp_path, {"index.md": "x"}, {"src/app/__init__.py": 2})
    r = described(cfg, files)
    assert r.considered == 0 and r.pct == 0


def test_the_claiming_subsystem_is_carried_when_known(tmp_path):
    """The finding a reader acts on is "this document claims this file and never mentions it", which needs
    both halves."""
    cfg, files = _project(tmp_path, {"index.md": "nothing"}, {"src/app/db_cache.py": 120})
    r = described(cfg, files, claimed_by={"src/app/db_cache.py": "platform.md"})
    assert r.undescribed[0].subsystem == "platform.md"
    assert "platform.md" in str(r.undescribed[0])


def test_build_configuration_is_not_a_subject(tmp_path):
    """`tailwind.config.js` is 109 lines of code by extension and sits inside a `**Covers:**` glob. No
    artifact worth reading writes a paragraph about it, and demanding one pushes `describe` toward the
    inventories the prose criterion penalises."""
    cfg, files = _project(tmp_path, {"index.md": "Nothing named here."},
                          {"src/app/tailwind.config.js": 109, "src/app/vite.config.ts": 60,
                           "src/app/real.ts": 120})
    r = described(cfg, files)
    assert [u.path for u in r.undescribed] == ["src/app/real.ts"]

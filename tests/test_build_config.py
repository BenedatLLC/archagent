"""Build configuration is not production code (#50).

`_mistiered` reports a subsystem covering only non-production code while claiming a place on the layer
ladder — the #26 pattern, where a test package tiered `infra` makes everything it imports read as an
upward dependency. It could not fire on wardrowbe's `frontend-tests`, which covers 12 tests and 5 build
configuration files, so the subsystem kept a tier it should never have had and produced a false
`layer-inversion` finding on the signal whose precision is currently 43%.

`described` already had this predicate privately. A second copy would have been a second behaviour, which
is #32's shape, so it moved to `configscan` beside `is_test_path` and both callers use it.
"""

from pathlib import Path

from archagent.configscan import is_build_config
from archagent.described import described
from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import _mistiered, _source_files


def test_the_shapes_that_blocked_the_check():
    """The five wardrowbe files, exactly."""
    for rel in ("frontend/next.config.js", "frontend/postcss.config.js", "frontend/tailwind.config.js",
                "frontend/vitest.config.ts", "frontend/next-env.d.ts"):
        assert is_build_config(rel), rel


def test_application_code_is_not_build_config():
    """The predicate has to stay narrow, or `_mistiered` starts calling production subsystems
    non-production and the check inverts into a new false-positive source."""
    for rel in ("app/config.py", "src/configuration.ts", "app/settings/config/loader.py",
                "src/lib/config/index.ts", "app/main.py"):
        assert not is_build_config(rel), rel


def test_a_test_subsystem_that_sweeps_up_its_own_config_is_mistiered():
    """The reported case. A test subsystem almost always covers the config that runs the tests —
    `vitest.config.ts` beside the suite it configures — and requiring *every* covered file to be a test
    meant the check could not fire on the shape it was written for."""
    covered = {"frontend/tests/a.test.ts", "frontend/tests/b.test.ts", "frontend/vitest.config.ts",
               "frontend/next-env.d.ts"}
    assert _mistiered(covered, "infra") == "infra"


def test_a_subsystem_holding_real_code_beside_its_tests_is_not_mistiered():
    """The strictness that was already there and must survive: a subsystem holding production code beside
    its tests is a production subsystem, and flagging it would relocate the false positives rather than
    remove them."""
    covered = {"src/app/service.py", "tests/test_service.py", "vitest.config.ts"}
    assert _mistiered(covered, "domain") == ""


def test_a_non_layered_tier_is_still_left_alone():
    """Nothing to correct when the author already said the subsystem is off the ladder."""
    covered = {"frontend/tests/a.test.ts", "frontend/vitest.config.ts"}
    assert _mistiered(covered, "test") == ""


def test_described_and_mistiered_share_one_definition(tmp_path):
    """#32's shape, avoided rather than repeated. `described` skipping a file and `_mistiered` counting
    it as production would be two answers to one question, and the disagreement would be invisible."""
    import inspect
    from archagent import described as d, drift
    assert "is_build_config" in inspect.getsource(d)
    assert "is_build_config" in inspect.getsource(drift._mistiered)
    assert "_BUILD_CONFIG" not in inspect.getsource(d), "the private copy should be gone"


def test_build_config_is_still_skipped_when_counting_described_modules(tmp_path):
    """The behaviour `described` had before the move, unchanged: no artifact worth reading writes a
    paragraph about `tailwind.config.js`, and demanding one pushes `describe` toward inventories."""
    (tmp_path / "architecture" / "subsystems").mkdir(parents=True)
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "real.py").write_text("\n".join(f"v{i} = {i}" for i in range(20)))
    (tmp_path / "src" / "vite.config.ts").write_text("\n".join(f"const v{i} = {i};" for i in range(20)))
    (tmp_path / "architecture" / "subsystems" / "a.md").write_text(
        "# A\n\n**Covers:** `src/**`\n\nThe `real` module does the work.\n")
    cfg = Config(project_root=tmp_path, languages=["python", "ts"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]),
                 ts=TSConfig(source_paths=["src"]))
    res = described(cfg, _source_files(cfg))
    assert not any("vite.config" in u.module for u in res.undescribed), \
        "build config must not be demanded of an artifact"

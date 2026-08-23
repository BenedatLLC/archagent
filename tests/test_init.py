"""init / upgrade: detection, file ownership, top-level wiring, artifact location."""

from archagent.cli import _resolve_arch_dir
from archagent.config import load_config
from archagent.init import detect_agents, detect_languages, init_project, upgrade_project


def _pyrepo(tmp):
    (tmp / "src" / "pkg").mkdir(parents=True)
    (tmp / "src" / "pkg" / "__init__.py").write_text("")
    (tmp / "pyproject.toml").write_text("[project]\n")
    return tmp


def test_detect_languages(tmp_path):
    _pyrepo(tmp_path)
    assert "python" in detect_languages(tmp_path)
    (tmp_path / "package.json").write_text("{}")
    assert "ts" in detect_languages(tmp_path)


def test_detect_agents(tmp_path):
    assert detect_agents(tmp_path) == []
    (tmp_path / ".claude").mkdir()
    assert detect_agents(tmp_path) == ["claude"]


def test_init_no_agents_creates_artifact_but_no_toplevel(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=[])
    assert (tmp_path / "archagent.toml").exists()
    assert (tmp_path / "architecture" / "AGENTS.md").exists()   # full instructions live here
    assert not (tmp_path / "CLAUDE.md").exists()                # never touches top level
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".claude").exists()                 # no skills when no agent


def test_init_installs_selected_agent_skills(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"])
    for phase in ("describe", "check", "invariant"):
        assert (tmp_path / ".claude" / "skills" / f"archagent-{phase}" / "SKILL.md").exists()


# --- configurable architecture location ---------------------------------------------------

def test_default_arch_dir_recorded_in_toml(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=[])
    toml = (tmp_path / "archagent.toml").read_text()
    assert 'architecture_dir = "architecture"' in toml
    assert load_config(tmp_path).arch_dir == "architecture"


def test_custom_arch_dir_scaffolds_and_retargets(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"], wire=True, arch_dir="docs/architecture")
    # artifact scaffolded under the custom dir, not the default
    assert (tmp_path / "docs" / "architecture" / "invariants.md").exists()
    assert not (tmp_path / "architecture").exists()
    # config records it and load_config reads it
    assert 'architecture_dir = "docs/architecture"' in (tmp_path / "archagent.toml").read_text()
    assert load_config(tmp_path).arch_dir == "docs/architecture"
    # archagent-owned files land under the custom dir and are retargeted to it
    agents_md = (tmp_path / "docs" / "architecture" / "AGENTS.md").read_text()
    assert "docs/architecture/" in agents_md and "\narchitecture/" not in agents_md
    skill = (tmp_path / ".claude" / "skills" / "archagent-describe" / "SKILL.md").read_text()
    assert "docs/architecture/" in skill
    # wiring points at the custom location
    claude = (tmp_path / "CLAUDE.md").read_text()
    assert "docs/architecture/AGENTS.md" in claude


def test_upgrade_uses_recorded_arch_dir(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"], arch_dir="docs/architecture")
    cfg = load_config(tmp_path)
    upgrade_project(tmp_path, agents=["claude"], arch_dir=cfg.arch_dir)
    assert (tmp_path / "docs" / "architecture" / "AGENTS.md").exists()


def test_resolve_arch_dir_explicit_and_noninteractive(tmp_path):
    assert _resolve_arch_dir(tmp_path, "docs/architecture", yes=False) == "docs/architecture"
    assert _resolve_arch_dir(tmp_path, "  design/arch/ ", yes=False) == "design/arch"
    assert _resolve_arch_dir(tmp_path, "", yes=True) == "architecture"   # non-interactive falls back


def test_ownership_user_files_preserved_owned_refreshed(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"])
    edited = tmp_path / "architecture" / "invariants.md"
    edited.write_text("MY INVARIANTS")

    res = init_project(tmp_path, agents=["claude"])  # re-run (no --force)
    assert edited.read_text() == "MY INVARIANTS"                      # user-owned untouched
    assert any(p.name == "invariants.md" for p in res.skipped)
    assert any(p.name == "AGENTS.md" for p in res.updated)           # archagent-owned refreshed


def test_upgrade_refreshes_prompts_only(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"])
    (tmp_path / "archagent.toml").unlink()  # user removed it

    res = upgrade_project(tmp_path)  # auto-detects installed = claude
    assert not (tmp_path / "archagent.toml").exists()               # upgrade does NOT scaffold user files
    assert any(p.name == "AGENTS.md" for p in res.updated)
    assert res.agents == ["claude"]


def test_upgrade_replaces_stale_prompts_but_keeps_user_content(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"])
    skill = tmp_path / ".claude" / "skills" / "archagent-describe" / "SKILL.md"
    agents_md = tmp_path / "architecture" / "AGENTS.md"
    invariants = tmp_path / "architecture" / "invariants.md"
    # simulate a stale install (old prompt text) + user-authored architecture content
    skill.write_text("STALE")
    agents_md.write_text("STALE")
    invariants.write_text("MY INVARIANTS")

    upgrade_project(tmp_path)

    # archagent-owned prompts are refreshed to the latest (stale content replaced)
    assert skill.read_text() != "STALE" and "archagent-describe" in skill.read_text()
    assert agents_md.read_text() != "STALE"
    # user-owned architecture content is preserved
    assert invariants.read_text() == "MY INVARIANTS"


def test_wire_is_additive_and_idempotent(tmp_path):
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["claude"], wire=True)
    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.exists() and "architecture/AGENTS.md" in claude_md.read_text()

    init_project(tmp_path, agents=["claude"], wire=True)  # again
    assert claude_md.read_text().count("archagent:start") == 1       # no duplicate pointer


# --- Codex (issue #23) -------------------------------------------------------------------------------

_PHASES = ("describe", "check", "invariant", "evaluate", "help")


def _codex_skill(root, phase):
    return root / ".agents" / "skills" / f"archagent-{phase}" / "SKILL.md"


def test_codex_init_writes_skills_under_dot_agents(tmp_path):
    """`.agents/`, not `.codex/`. `~/.codex/` is the user-level config home; the repo-level skills path is
    the vendor-neutral `.agents/skills/`, and getting it wrong writes files no agent ever reads."""
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["codex"])
    written = [p for p in _PHASES if _codex_skill(tmp_path, p).is_file()]
    assert written, "no codex skills written"
    for phase in written:
        text = _codex_skill(tmp_path, phase).read_text()
        assert text.startswith("---\n"), phase
        assert f"name: archagent-{phase}" in text
        assert "description:" in text
    assert not (tmp_path / ".codex").exists(), "must not write to the user-level config dir name"


def test_codex_upgrade_refreshes_the_skills(tmp_path):
    """Proves `detect_installed_agents` sees codex — it probes via `_agent_target`, so codex falls out for
    free once the target exists."""
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["codex"])
    target = next(_codex_skill(tmp_path, p) for p in _PHASES if _codex_skill(tmp_path, p).is_file())
    target.write_text("clobbered\n")
    upgrade_project(tmp_path)
    assert target.read_text() != "clobbered\n"


def test_codex_wire_writes_the_agents_pointer_and_is_idempotent(tmp_path):
    """Codex reads `AGENTS.md` from the repo root down to the working directory, so the pointer is the
    right mechanism and needs no new template."""
    _pyrepo(tmp_path)
    init_project(tmp_path, agents=["codex"], wire=True)
    first = (tmp_path / "AGENTS.md").read_text()
    assert "architecture/AGENTS.md" in first
    init_project(tmp_path, agents=["codex"], wire=True)
    assert (tmp_path / "AGENTS.md").read_text() == first


def test_codex_is_never_auto_detected(tmp_path):
    """**This test pins a decision.**

    Codex is repo-clean by construction: a full session leaves `git status` untouched and all state lives
    under `~/.codex/`. The two candidate signals both fail on precision — `.agents/skills/` is
    vendor-neutral, and a root `AGENTS.md` is read by Codex, Cursor and others. Without this test, keying
    detection off either could be reintroduced by accident and nothing would fail.
    """
    _pyrepo(tmp_path)
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Agent instructions\n")
    assert detect_agents(tmp_path) == []


def test_the_advisory_names_codex_and_says_why_it_is_not_detected(tmp_path):
    """The highest-leverage line in codex support: it is what turns an undetectable agent into a
    discoverable one, which is what makes opt-in acceptable rather than merely defensible."""
    from archagent.cli import _resolve_agents
    selected, advisory = _resolve_agents(tmp_path, "auto", detect_agents)
    assert selected == []
    assert "codex" in advisory and "auto-detect" in advisory


def test_codex_is_a_known_agent(tmp_path):
    """`--agents codex` used to be a silent no-op that reported success."""
    from archagent.init import KNOWN_AGENTS
    assert "codex" in KNOWN_AGENTS
    from archagent.cli import _resolve_agents
    selected, advisory = _resolve_agents(tmp_path, "codex", detect_agents)
    assert selected == ["codex"] and not advisory


# --- what init tells you about its own guesses (issue #27) ------------------------------------------

from archagent.init import describe_settings


def _s(settings, key):
    return next(s for s in settings if s.key == key)


def test_a_source_path_holding_no_matching_files_is_flagged(tmp_path):
    """The layout miss this exists to catch: `source_paths` is a fixed default of `src`, so a project
    keeping its TypeScript under `web/src` gets a config that scopes every structural rule to nothing —
    and `check` then reports that all invariants hold, having examined none of them."""
    (tmp_path / "web" / "src").mkdir(parents=True)
    (tmp_path / "web" / "src" / "a.ts").write_text("export const a = 1\n")
    s = _s(describe_settings(tmp_path, ["ts"], "architecture"), "ts.source_paths")
    assert s.problem and "web/ looks likelier" in s.problem


def test_a_source_path_that_holds_files_is_not_flagged(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    assert not _s(describe_settings(tmp_path, ["python"], "architecture"), "python.source_paths").problem


def test_an_unguessable_root_package_is_flagged_rather_than_left_blank(tmp_path):
    """A `root_package` naming nothing scopes every BOUNDARY contract to an empty module set. Commenting
    it out in the generated file said so only to a reader who opened the file."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "loose.py").write_text("x = 1\n")     # no package, so nothing to guess
    s = _s(describe_settings(tmp_path, ["python"], "architecture"), "python.root_package")
    assert s.value == "(unset)" and "BOUNDARY" in s.problem


def test_a_guessed_root_package_is_reported_as_guessed(tmp_path):
    """Provenance per value: a reader checks a guess differently from something detected."""
    pkg = tmp_path / "src" / "myapp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    s = _s(describe_settings(tmp_path, ["python"], "architecture"), "python.root_package")
    assert s.value == "myapp" and s.origin == "guessed" and not s.problem


def test_vendored_directories_do_not_win_the_likeliest_guess(tmp_path):
    """`node_modules` holds more JavaScript than any project directory, and suggesting it would be worse
    than suggesting nothing."""
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    for i in range(5):
        (tmp_path / "node_modules" / "dep" / f"m{i}.js").write_text("x\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.ts").write_text("export const a = 1\n")
    s = _s(describe_settings(tmp_path, ["ts"], "architecture"), "ts.source_paths")
    assert "app/ looks likelier" in s.problem


def test_init_reports_its_settings(tmp_path):
    """The list must reach the caller — this is what the CLI renders."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    result = init_project(tmp_path, agents=[])
    assert [s.key for s in result.settings][:2] == ["project.languages", "project.architecture_dir"]

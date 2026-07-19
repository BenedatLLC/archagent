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

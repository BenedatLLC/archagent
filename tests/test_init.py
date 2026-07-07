"""init / upgrade: detection, file ownership, top-level wiring."""

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

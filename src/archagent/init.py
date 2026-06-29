"""`archagent init` — scaffold archagent into a target repo (run from outside it).

Writes:
  - archagent.toml (with detected languages)
  - architecture/ templates (the artifact)
  - per-agent skill/command files + a shared AGENTS.md (the delivery layer)

One neutral source of phase prompts is rendered into each agent's convention
(Spec-Kit model). Existing files are left alone unless ``force`` is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"
ARCH_TEMPLATES = TEMPLATES / "architecture"
AGENT_TEMPLATES = TEMPLATES / "agent"

KNOWN_AGENTS = ("claude", "cursor", "openhands")


@dataclass
class Phase:
    name: str
    description: str


PHASES = [
    Phase("describe", "Build or update the architecture artifact for this repo (trust-but-verify)."),
    Phase("check", "Run archagent check and resolve architecture violations."),
    Phase("invariant", "Add or change a checkable architectural invariant and verify it."),
]


@dataclass
class InitResult:
    created: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)


def init_project(project_root: Path, agents: list[str] | None = None, force: bool = False) -> InitResult:
    agents = list(KNOWN_AGENTS) if agents is None else agents
    result = InitResult(languages=detect_languages(project_root), agents=agents)

    _write(project_root / "archagent.toml", _render_toml(result.languages, project_root), force, result)

    for src_file in sorted(ARCH_TEMPLATES.rglob("*")):
        if src_file.is_file():
            dest = project_root / "architecture" / src_file.relative_to(ARCH_TEMPLATES)
            _write(dest, src_file.read_text(), force, result)

    if agents:
        _deliver_agents(project_root, agents, force, result)

    return result


def _deliver_agents(root: Path, agents: list[str], force: bool, result: InitResult) -> None:
    for agent in agents:
        for phase in PHASES:
            body = (AGENT_TEMPLATES / "phases" / f"{phase.name}.md").read_text()
            dest, frontmatter = _agent_target(root, agent, phase)
            if dest is None:
                continue
            _write(dest, frontmatter + body, force, result)
        if agent == "claude":
            _write(
                root / "CLAUDE.md",
                "# Project guidance for Claude Code\n\n"
                "See [AGENTS.md](AGENTS.md) for how to work in this repo with archagent.\n",
                force,
                result,
            )
    # Shared context file, read by Cursor and OpenHands natively (Claude via CLAUDE.md).
    _write(root / "AGENTS.md", (AGENT_TEMPLATES / "AGENTS.md").read_text(), force, result)


def _agent_target(root: Path, agent: str, phase: Phase) -> tuple[Path | None, str]:
    if agent in ("claude", "cursor"):
        base = ".claude" if agent == "claude" else ".cursor"
        frontmatter = f"---\nname: archagent-{phase.name}\ndescription: {phase.description}\n---\n\n"
        return root / base / "skills" / f"archagent-{phase.name}" / "SKILL.md", frontmatter
    if agent == "openhands":
        frontmatter = (
            f"---\nname: archagent-{phase.name}\ntype: knowledge\n"
            f"triggers:\n  - archagent {phase.name}\n  - /archagent-{phase.name}\n---\n\n"
        )
        return root / ".openhands" / "microagents" / f"archagent-{phase.name}.md", frontmatter
    return None, ""


def _write(dest: Path, content: str, force: bool, result: InitResult) -> None:
    if dest.exists() and not force:
        result.skipped.append(dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    result.created.append(dest)


def detect_languages(root: Path) -> list[str]:
    langs: list[str] = []
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "setup.cfg").exists() \
            or any(root.rglob("*.py")):
        langs.append("python")
    if (root / "package.json").exists() or any(root.glob("**/tsconfig*.json")):
        langs.append("ts")
    return langs or ["python"]


def _guess_python_root(root: Path) -> str | None:
    src = root / "src"
    if src.is_dir():
        pkgs = [p.name for p in src.iterdir() if p.is_dir() and (p / "__init__.py").exists()]
        if len(pkgs) == 1:
            return pkgs[0]
    for p in sorted(root.iterdir()):
        if p.is_dir() and (p / "__init__.py").exists() and p.name not in {"tests", "test", "docs"}:
            return p.name
    return None


def _render_toml(languages: list[str], root: Path) -> str:
    lang_list = ", ".join(f'"{lang}"' for lang in languages)
    lines = ["[project]", f"languages = [{lang_list}]", ""]
    if "python" in languages:
        pkg = _guess_python_root(root)
        pkg_line = f'root_package = "{pkg}"' if pkg else '# root_package = "your_package"  # REQUIRED for BOUNDARY/python'
        lines += ["[python]", pkg_line, 'source_paths = ["src"]', ""]
    if "ts" in languages:
        lines += ["[ts]", 'source_paths = ["src"]', ""]
    return "\n".join(lines)

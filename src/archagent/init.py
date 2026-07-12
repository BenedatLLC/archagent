"""`archagent init` / `archagent upgrade` — scaffold and refresh archagent in a repo.

Two file classes:
- **user-owned** — `archagent.toml` and everything under `architecture/` *except* `AGENTS.md`.
  Created once; never overwritten by an upgrade (only with `--force`).
- **archagent-owned** — `architecture/AGENTS.md` and the per-agent skill files. Generated from
  archagent's templates; always refreshed to the latest so `upgrade` can pick up new prompts.

`init` never creates or overwrites the repo's top-level `CLAUDE.md` / `AGENTS.md`. With `--wire` it
appends a small additive pointer to them (idempotent); otherwise the coding agent can wire them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"
ARCH_TEMPLATES = TEMPLATES / "architecture"
AGENT_TEMPLATES = TEMPLATES / "agent"

KNOWN_AGENTS = ("claude", "cursor", "openhands")

_POINTER_START = "<!-- archagent:start -->"
_POINTER_END = "<!-- archagent:end -->"
_POINTER_BODY = (
    "## Architecture (archagent)\n\n"
    "This repo's architecture is described and enforced by **archagent**. See "
    "[architecture/AGENTS.md](architecture/AGENTS.md) for how to work with it "
    "(describe / check / invariants)."
)


@dataclass
class Phase:
    name: str
    description: str


PHASES = [
    Phase("describe", "Build or update the architecture artifact for this repo (trust-but-verify)."),
    Phase("check", "Run archagent check and resolve architecture violations."),
    Phase("invariant", "Add or change a checkable architectural invariant and verify it."),
    Phase("evaluate", "Evaluate the architecture for system-level smells and recommend fixes."),
]


@dataclass
class InitResult:
    created: list[Path] = field(default_factory=list)   # new files
    updated: list[Path] = field(default_factory=list)   # archagent-owned files refreshed
    skipped: list[Path] = field(default_factory=list)   # user-owned files left as-is
    wired: list[Path] = field(default_factory=list)     # top-level files given a pointer
    languages: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)


# --- detection -----------------------------------------------------------

def detect_agents(root: Path) -> list[str]:
    """Which agents are already set up in this repo (by their config dirs)."""
    found = []
    if (root / ".claude").exists():
        found.append("claude")
    if (root / ".cursor").exists():
        found.append("cursor")
    if (root / ".openhands").exists():
        found.append("openhands")
    return found


def detect_installed_agents(root: Path) -> list[str]:
    """Which agents already have archagent skills installed (for `upgrade`)."""
    found = []
    for agent in KNOWN_AGENTS:
        probe, _ = _agent_target(root, agent, PHASES[0])
        if probe is not None and probe.exists():
            found.append(agent)
    return found


def detect_languages(root: Path) -> list[str]:
    langs: list[str] = []
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "setup.cfg").exists() \
            or any(root.rglob("*.py")):
        langs.append("python")
    if (root / "package.json").exists() or any(root.glob("**/tsconfig*.json")):
        langs.append("ts")
    return langs or ["python"]


# --- init / upgrade ------------------------------------------------------

def init_project(project_root: Path, agents: list[str], force: bool = False, wire: bool = False) -> InitResult:
    result = InitResult(languages=detect_languages(project_root), agents=agents)

    # user-owned: config + architecture templates (create once)
    _write_user(project_root / "archagent.toml", _render_toml(result.languages, project_root), force, result)
    for src_file in sorted(ARCH_TEMPLATES.rglob("*")):
        if src_file.is_file():
            dest = project_root / "architecture" / src_file.relative_to(ARCH_TEMPLATES)
            _write_user(dest, src_file.read_text(), force, result)

    # archagent-owned: always refreshed to latest
    _write_owned_agent_files(project_root, agents, result)

    if wire:
        _wire_top_level(project_root, agents, result)
    return result


def upgrade_project(project_root: Path, agents: list[str] | None = None) -> InitResult:
    """Refresh only the archagent-owned files (prompts) to the latest; never touch user content."""
    agents = agents if agents is not None else detect_installed_agents(project_root)
    result = InitResult(agents=agents)
    _write_owned_agent_files(project_root, agents, result)
    return result


def _write_owned_agent_files(root: Path, agents: list[str], result: InitResult) -> None:
    # The full instructions live here (archagent-owned), not at the repo top level.
    _write_owned(root / "architecture" / "AGENTS.md", (AGENT_TEMPLATES / "AGENTS.md").read_text(), result)
    for agent in agents:
        for phase in PHASES:
            dest, frontmatter = _agent_target(root, agent, phase)
            if dest is None:
                continue
            body = (AGENT_TEMPLATES / "phases" / f"{phase.name}.md").read_text()
            _write_owned(dest, frontmatter + body, result)


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


# --- top-level pointer (opt-in, additive, idempotent) --------------------

def _wire_top_level(root: Path, agents: list[str], result: InitResult) -> None:
    targets: set[str] = set()
    if "claude" in agents:
        targets.add("CLAUDE.md")
    if "cursor" in agents or "openhands" in agents:
        targets.add("AGENTS.md")
    block = f"\n{_POINTER_START}\n{_POINTER_BODY}\n{_POINTER_END}\n"
    for name in sorted(targets):
        path = root / name
        existing = path.read_text() if path.exists() else ""
        if _POINTER_START in existing or "architecture/AGENTS.md" in existing:
            continue  # already wired
        path.write_text((existing.rstrip() + "\n" if existing else "") + block)
        result.wired.append(path)


# --- helpers -------------------------------------------------------------

def _write_user(dest: Path, content: str, force: bool, result: InitResult) -> None:
    if dest.exists() and not force:
        result.skipped.append(dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    result.created.append(dest)


def _write_owned(dest: Path, content: str, result: InitResult) -> None:
    existed = dest.exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    (result.updated if existed else result.created).append(dest)


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

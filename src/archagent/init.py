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

KNOWN_AGENTS = ("claude", "cursor", "codex", "openhands")

_POINTER_START = "<!-- archagent:start -->"
_POINTER_END = "<!-- archagent:end -->"


def _pointer_body(arch_dir: str) -> str:
    p = f"{arch_dir}/AGENTS.md"
    return (
        "## Architecture (archagent)\n\n"
        "This repo's architecture is described and enforced by **archagent**. See "
        f"[{p}]({p}) for how to work with it (describe / check / invariants)."
    )


def _apply_arch_dir(content: str, arch_dir: str) -> str:
    """Retarget archagent-owned content (skills, AGENTS.md) at the configured artifact location. Owned
    content refers to the artifact by its path (`architecture/…`); user files use relative links and move
    unchanged. Only the `architecture/` *path* prefix is rewritten, never the bare word."""
    if arch_dir == "architecture":
        return content
    return content.replace("architecture/", arch_dir.rstrip("/") + "/")


@dataclass
class Phase:
    name: str
    description: str


PHASES = [
    Phase("describe", "Build or update the architecture artifact for this repo (trust-but-verify)."),
    Phase("check", "Run archagent check and resolve architecture violations."),
    Phase("invariant", "Add or change a checkable architectural invariant and verify it."),
    Phase("evaluate", "Evaluate the architecture for system-level smells and recommend fixes."),
    Phase("help", "Overview of the archagent lifecycle and the command/skill for each step."),
]


@dataclass
class InitResult:
    created: list[Path] = field(default_factory=list)   # new files
    updated: list[Path] = field(default_factory=list)   # archagent-owned files refreshed
    skipped: list[Path] = field(default_factory=list)   # user-owned files left as-is
    wired: list[Path] = field(default_factory=list)     # top-level files given a pointer
    languages: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    #: What went into `archagent.toml`, and how sure we are of each value (issue #27).
    settings: list["Setting"] = field(default_factory=list)


@dataclass
class Setting:
    """One line of the generated config, with its provenance and whether it looks right.

    `init` guesses, and it guesses from very little. Telling a reader in the README to "check
    archagent.toml" puts the burden in the wrong place: the tool knows which values it detected, which it
    defaulted, and — for a source path — whether any matching file actually lives there. Printing that is
    the difference between a check a user performs and one they mean to.

    The failure being guarded is silent and total. A `root_package` naming nothing scopes every BOUNDARY
    contract to an empty module set, and a `source_paths` pointing at the wrong directory scopes every
    structural rule to no files — in both cases `check` reports that all invariants hold, having examined
    nothing. That is this project's recurring defect wearing a configuration hat.
    """
    key: str                 # "python.root_package"
    value: str
    origin: str              # "detected" | "guessed" | "default"
    problem: str = ""        # non-empty when the value looks wrong


#: Extensions that make a directory a plausible source root for each language.
_LANG_EXTS = {"python": (".py",), "ts": (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")}
_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".archagent"}


def describe_settings(root: Path, languages: list[str], arch_dir: str) -> list[Setting]:
    """The generated configuration, annotated for a reader to check.

    A source path is verified by counting files of the right kind under it, which catches the common
    layout miss — TypeScript under `web/src` while the default says `src` — without pretending to infer
    the right answer. Where nothing matches, the message names a directory that does.
    """
    out = [Setting("project.languages", ", ".join(languages), "detected"),
           Setting("project.architecture_dir", arch_dir, "default" if arch_dir == "architecture" else "chosen")]
    for lang in languages:
        exts = _LANG_EXTS.get(lang, ())
        if lang == "python":
            pkg = _guess_python_root(root)
            out.append(Setting("python.root_package", pkg or "(unset)",
                               "guessed" if pkg else "default",
                               "" if pkg else "no importable package found — BOUNDARY rules for Python "
                                             "cannot be scoped until this is set"))
        n = sum(1 for _ in _files_under(root / "src", exts))
        problem = ""
        if not n:
            # The directory *containing* the package beats the directory with the most files. Counting
            # files picks `tests/` on any repository whose package sits at the root — httpx, dspy,
            # requests — and `tests/` is not on the import path, so following the hint reproduces the
            # exact miss it was written to prevent.
            alt = (_containing_dir(root, pkg, exts) if lang == "python" and pkg else "") \
                or _likeliest_dir(root, exts)
            problem = (f"no {'/'.join(exts)} files under src/"
                       + (f" — {alt}/ looks likelier" if alt else ""))
        out.append(Setting(f"{lang}.source_paths", "src", "default", problem))
    return out


def _containing_dir(root: Path, pkg: str, exts: tuple[str, ...]) -> str:
    """The directory that holds `pkg`, expressed as a source path — `.` when it sits at the root.

    `source_paths` names what is on the import path, which is the *parent* of the package, and getting
    that distinction wrong is the failure `docs/CONFIGURATION.md` opens with. Since `root_package` has
    already been guessed by the time the source path is checked, the answer is usually available rather
    than needing to be inferred from file counts.
    """
    if not pkg or ".py" not in exts:
        return ""
    for marker in (root / pkg / "__init__.py", root / pkg / "__main__.py"):
        if marker.is_file():
            return "."
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name not in _SKIP):
        if (d / pkg / "__init__.py").is_file():
            return d.name
    return ""


def _files_under(d: Path, exts: tuple[str, ...]):
    if not d.is_dir() or not exts:
        return
    for p in d.rglob("*"):
        if p.is_file() and p.suffix in exts and not (set(p.parts) & _SKIP):
            yield p


def _likeliest_dir(root: Path, exts: tuple[str, ...]) -> str:
    """The top-level directory holding the most files of this kind, or "".

    A hint, never a value written into the config. Naming a candidate turns "this is wrong" into
    something the reader can act on in one edit; choosing for them would replace a visible bad guess with
    an invisible one.
    """
    best, best_n = "", 0
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name not in _SKIP):
        n = sum(1 for _ in _files_under(d, exts))
        if n > best_n:
            best, best_n = d.name, n
    return best


# --- detection -----------------------------------------------------------

def detect_agents(root: Path) -> list[str]:
    """Which agents are already set up in this repo (by their config dirs).

    **Codex is deliberately absent, and cannot be added.** This function's contract is "an unambiguous,
    agent-specific directory exists in this repo". Claude, Cursor and OpenHands each satisfy it. Codex is
    repo-clean by construction — a full session leaves `git status` untouched, and all per-machine state
    lives under `~/.codex/`, which says nothing about *this* repo. The two candidate signals both fail on
    precision: `.agents/skills/` is vendor-neutral and belongs to no single agent, and a root `AGENTS.md`
    is read by Codex, Cursor and several others.

    Widening the contract to "a directory exists that Codex *might* use" would weaken detection for the
    three agents that satisfy it strictly, in exchange for a guess. Codex is opt-in via `--agents codex`,
    and the advisory in `cli._resolve_agents` is what makes that discoverable.
    """
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

def init_project(project_root: Path, agents: list[str], force: bool = False, wire: bool = False,
                 arch_dir: str = "architecture") -> InitResult:
    arch_dir = arch_dir.strip("/") or "architecture"
    result = InitResult(languages=detect_languages(project_root), agents=agents)
    result.settings = describe_settings(project_root, result.languages, arch_dir)

    # user-owned: config + architecture templates (create once)
    _write_user(project_root / "archagent.toml", _render_toml(result.languages, project_root, arch_dir), force, result)
    for src_file in sorted(ARCH_TEMPLATES.rglob("*")):
        if src_file.is_file():
            dest = project_root / arch_dir / src_file.relative_to(ARCH_TEMPLATES)
            _write_user(dest, src_file.read_text(), force, result)

    # archagent-owned: always refreshed to latest
    _write_owned_agent_files(project_root, agents, result, arch_dir)

    if wire:
        _wire_top_level(project_root, agents, result, arch_dir)
    return result


def upgrade_project(project_root: Path, agents: list[str] | None = None,
                    arch_dir: str = "architecture") -> InitResult:
    """Refresh only the archagent-owned files (prompts) to the latest; never touch user content."""
    arch_dir = arch_dir.strip("/") or "architecture"
    agents = agents if agents is not None else detect_installed_agents(project_root)
    result = InitResult(agents=agents)
    _write_owned_agent_files(project_root, agents, result, arch_dir)
    return result


def _write_owned_agent_files(root: Path, agents: list[str], result: InitResult, arch_dir: str = "architecture") -> None:
    # The full instructions live here (archagent-owned), not at the repo top level.
    agents_md = _apply_arch_dir((AGENT_TEMPLATES / "AGENTS.md").read_text(), arch_dir)
    _write_owned(root / arch_dir / "AGENTS.md", agents_md, result)
    for agent in agents:
        for phase in PHASES:
            dest, frontmatter = _agent_target(root, agent, phase)
            if dest is None:
                continue
            body = (AGENT_TEMPLATES / "phases" / f"{phase.name}.md").read_text()
            _write_owned(dest, _apply_arch_dir(frontmatter + body, arch_dir), result)


#: Agents whose repo-level skills are a directory per skill holding `SKILL.md` with `name`/`description`
#: frontmatter — the same shape for all three, so they share a branch below.
#:
#: Codex's directory is `.agents/`, **not** `.codex/`. `~/.codex/` is the user-level config home; the
#: repo-level skills path is the vendor-neutral `.agents/skills/`. Getting this wrong writes files no
#: agent ever reads.
_SKILL_DIR_AGENTS = {"claude": ".claude", "cursor": ".cursor", "codex": ".agents"}


def _agent_target(root: Path, agent: str, phase: Phase) -> tuple[Path | None, str]:
    if agent in _SKILL_DIR_AGENTS:
        base = _SKILL_DIR_AGENTS[agent]
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

def _wire_top_level(root: Path, agents: list[str], result: InitResult, arch_dir: str = "architecture") -> None:
    targets: set[str] = set()
    if "claude" in agents:
        targets.add("CLAUDE.md")
    if any(a in agents for a in ("cursor", "codex", "openhands")):
        # Codex reads `AGENTS.md` from the repo root down to the working directory, so the pointer is
        # exactly the right mechanism for it and needs no new template.
        targets.add("AGENTS.md")
    block = f"\n{_POINTER_START}\n{_pointer_body(arch_dir)}\n{_POINTER_END}\n"
    for name in sorted(targets):
        path = root / name
        existing = path.read_text() if path.exists() else ""
        if _POINTER_START in existing or f"{arch_dir}/AGENTS.md" in existing:
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
    # One level deeper, for the `backend/app/` shape `docs/CONFIGURATION.md` documents. Only reached when
    # neither `src/<pkg>` nor a root-level package exists, and only when the answer is unambiguous — two
    # candidates mean a guess, and a wrong `root_package` scopes every BOUNDARY contract to a module set
    # that does not exist, which reports as all invariants holding.
    nested = sorted({
        child.name
        for p in sorted(root.iterdir()) if p.is_dir() and p.name not in _SKIP | {"tests", "test", "docs"}
        for child in sorted(p.iterdir()) if child.is_dir() and (child / "__init__.py").exists()
    })
    return nested[0] if len(nested) == 1 else None


def _render_toml(languages: list[str], root: Path, arch_dir: str = "architecture") -> str:
    lang_list = ", ".join(f'"{lang}"' for lang in languages)
    lines = ["[project]", f"languages = [{lang_list}]", f'architecture_dir = "{arch_dir}"', ""]
    if "python" in languages:
        pkg = _guess_python_root(root)
        pkg_line = f'root_package = "{pkg}"' if pkg else '# root_package = "your_package"  # REQUIRED for BOUNDARY/python'
        lines += ["[python]", pkg_line, 'source_paths = ["src"]', ""]
    if "ts" in languages:
        lines += ["[ts]", 'source_paths = ["src"]', ""]
    return "\n".join(lines)

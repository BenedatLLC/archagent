"""Project-level configuration for archagent (``archagent.toml``).

Per-language source locations; for Python also the root package name (import-linter
analyses by module path). Kept small on purpose.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_TS_ALIASES = ("ts", "tsx", "typescript", "js", "javascript")


@dataclass
class PythonConfig:
    root_package: str | None = None
    source_paths: list[str] = field(default_factory=lambda: ["src"])
    # Command to run property tests in the TARGET's environment (pbt tier executes
    # the project's code, unlike the static structural checkers). e.g. "uv run pytest".
    test_command: str = "pytest"


@dataclass
class TSConfig:
    source_paths: list[str] = field(default_factory=lambda: ["src"])


@dataclass
class Config:
    project_root: Path
    languages: list[str] = field(default_factory=lambda: ["python"])
    python: PythonConfig = field(default_factory=PythonConfig)
    ts: TSConfig = field(default_factory=TSConfig)

    @property
    def invariants_path(self) -> Path:
        return self.project_root / "architecture" / "invariants.md"

    @property
    def generated_dir(self) -> Path:
        return self.project_root / ".archagent" / "generated"

    @property
    def uses_python(self) -> bool:
        return "python" in self.languages

    @property
    def uses_ts(self) -> bool:
        return any(lang in self.languages for lang in _TS_ALIASES)

    def all_source_paths(self) -> list[str]:
        """Paths for ast-grep to scan (it matches each rule only against its language)."""
        paths: list[str] = []
        if self.uses_python:
            paths += self.python.source_paths
        if self.uses_ts:
            paths += self.ts.source_paths
        seen: list[str] = []
        for p in paths:
            if p not in seen:
                seen.append(p)
        return seen


def load_config(project_root: Path) -> Config:
    cfg_path = project_root / "archagent.toml"
    data: dict = tomllib.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    proj = data.get("project", {})
    py = data.get("python", {})
    ts = data.get("ts") or data.get("typescript") or data.get("js") or {}
    return Config(
        project_root=project_root,
        languages=proj.get("languages", ["python"]),
        python=PythonConfig(
            root_package=py.get("root_package"),
            source_paths=py.get("source_paths", ["src"]),
            test_command=py.get("test_command", "pytest"),
        ),
        ts=TSConfig(source_paths=ts.get("source_paths", ["src"])),
    )

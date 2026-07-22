"""Install a native git pre-commit hook that runs `archagent check` (Phase 3, initial version).

Writes a marker-delimited block into `.git/hooks/pre-commit` so it's idempotent (re-running updates the
block, e.g. to toggle `--skip-pbt`) and composes with an existing hook (the block is appended, not
clobbered). Deterministic file scaffolding — a CLI subcommand, not a skill.

This is the *native* hook (local to the developer's clone, not committed/shared). The team-shared
`pre-commit`-framework path and a `test_architecture.py` generator are on the roadmap.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

_START = "# >>> archagent >>>"
_END = "# <<< archagent <<<"


def _block(skip_pbt: bool) -> str:
    cmd = "archagent check --skip-pbt" if skip_pbt else "archagent check"
    return (
        f"{_START}\n"
        "# Architecture check (managed by archagent — re-run `archagent install-hook` to change,\n"
        "# or delete this block to disable).\n"
        "if ! command -v archagent >/dev/null 2>&1; then\n"
        '  echo "archagent: not on PATH — run \'uv tool install archagent\', or remove this hook block" >&2\n'
        "  exit 1\n"
        "fi\n"
        f"{cmd} || exit 1\n"
        f"{_END}\n"
    )


@dataclass
class HookResult:
    path: Path
    action: str          # "created" | "updated" | "appended"
    skip_pbt: bool


def install_hook(root: Path, skip_pbt: bool = False) -> HookResult:
    """Install / update the archagent block in `.git/hooks/pre-commit`. Raises ValueError if `root` isn't
    a standard git repository."""
    git = root / ".git"
    if not git.is_dir():  # a worktree/submodule uses a `.git` file; unsupported in this initial version
        raise ValueError(f"{root} is not a git repository (no .git/ directory)")
    hooks_dir = git / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-commit"
    block = _block(skip_pbt)

    if not hook.exists():
        content, action = "#!/bin/sh\n" + block, "created"
    else:
        existing = hook.read_text()
        if _START in existing:
            content, action = _replace_block(existing, block), "updated"
        else:  # keep the user's hook; append ours
            sep = "" if existing.endswith("\n") else "\n"
            content, action = existing + sep + "\n" + block, "appended"

    hook.write_text(content)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return HookResult(hook, action, skip_pbt)


def _replace_block(text: str, block: str) -> str:
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if line.strip() == _START:
            skipping = True
            out.append(block)  # substitute the fresh block once
            continue
        if line.strip() == _END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "".join(out)

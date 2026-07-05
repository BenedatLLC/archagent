"""archagent CLI.

  archagent init    scaffold archagent.toml + architecture/ templates into a repo
  archagent gen     parse architecture/invariants.md -> generate checker configs
  archagent check   regenerate, run the checkers, report pass/fail per invariant
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .check import run_checks
from .config import load_config
from .generate import generate
from .init import KNOWN_AGENTS, detect_agents, init_project, upgrade_project
from .invariants import parse_invariants

app = typer.Typer(add_completion=False, help="Keep code adherent to a described architecture.")
console = Console()


def _resolve_agents(root: Path, agents_opt: str, detected_when_auto) -> tuple[list[str], str | None]:
    """Resolve the --agents value to a concrete list, with an optional advisory message."""
    val = agents_opt.strip().lower()
    if val == "none":
        return [], None
    if val == "all":
        return list(KNOWN_AGENTS), None
    if val in ("auto", ""):
        found = detected_when_auto(root)
        if found:
            return found, None
        return [], ("no coding agent detected (.claude/.cursor/.openhands) — "
                    "re-run with --agents claude,cursor,openhands to add skills")
    selected = [a.strip() for a in agents_opt.split(",") if a.strip()]
    unknown = [a for a in selected if a not in KNOWN_AGENTS]
    msg = f"unknown agent(s) ignored: {', '.join(unknown)}" if unknown else None
    return [a for a in selected if a in KNOWN_AGENTS], msg


def _report(result, root: Path) -> None:
    if result.languages:
        console.print(f"Detected languages: [bold]{', '.join(result.languages)}[/]")
    if result.agents:
        console.print(f"Agents: [bold]{', '.join(result.agents)}[/]")
    for p in result.created:
        console.print(f"  [green]created[/] {p.relative_to(root)}")
    for p in result.updated:
        console.print(f"  [cyan]updated[/] {p.relative_to(root)}")
    for p in result.wired:
        console.print(f"  [magenta]wired[/]   {p.relative_to(root)}  (added architecture/AGENTS.md pointer)")
    for p in result.skipped:
        console.print(f"  [yellow]exists, skipped[/] {p.relative_to(root)}  (use --force)")


@app.command()
def init(
    project: Path = typer.Argument(Path("."), help="Target repo to scaffold into"),
    agents: str = typer.Option("auto", help="Agents: 'auto' (detect), 'all', 'none', or e.g. 'claude,cursor'"),
    wire: bool = typer.Option(False, "--wire", help="Also add an additive pointer to the repo's top-level CLAUDE.md / AGENTS.md"),
    force: bool = typer.Option(False, "--force", help="Overwrite user-owned files too (re-scaffold — clobbers your edits)"),
) -> None:
    """Scaffold archagent.toml, the architecture/ templates, and per-agent skills into a repo."""
    root = project.resolve()
    selected, advisory = _resolve_agents(root, agents, detect_agents)
    if advisory:
        console.print(f"[yellow]{advisory}[/]")
    result = init_project(root, agents=selected, force=force, wire=wire)
    _report(result, root)
    if selected and not wire:
        console.print("\nTip: wire archagent into your agent's top-level instructions with [bold]--wire[/], "
                      "or have the agent add a pointer to [bold]architecture/AGENTS.md[/].")
    console.print("\nNext: run [bold]/archagent-describe[/] (or edit architecture/invariants.md), then [bold]archagent check[/].")


@app.command()
def upgrade(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    agents: str = typer.Option("auto", help="Agents to refresh: 'auto' (installed), 'all', or e.g. 'claude'"),
) -> None:
    """Refresh archagent-owned prompts (skills + architecture/AGENTS.md); leaves your config and architecture content untouched."""
    root = project.resolve()
    val = agents.strip().lower()
    if val in ("auto", ""):
        selected = None  # upgrade_project detects installed agents
    elif val == "all":
        selected = list(KNOWN_AGENTS)
    else:
        selected = [a.strip() for a in agents.split(",") if a.strip() in KNOWN_AGENTS]
    result = upgrade_project(root, agents=selected)
    _report(result, root)
    console.print("[green]Prompts refreshed.[/]")


@app.command()
def gen(project: Path = typer.Option(Path("."), help="Target repo root")) -> None:
    """Generate checker configs from architecture/invariants.md."""
    config = load_config(project.resolve())
    invariants = parse_invariants(config.invariants_path)
    result = generate(invariants, config)
    console.print(f"Parsed [bold]{len(invariants)}[/] invariant(s) from {config.invariants_path}")
    for path in result.written:
        console.print(f"  wrote {path.relative_to(config.project_root)}")
    for label, ids in (("import-linter", result.importlinter_ids),
                       ("dependency-cruiser", result.depcruiser_ids),
                       ("ast-grep", result.astgrep_ids),
                       ("pbt", result.pbt_ids)):
        if ids:
            console.print(f"  {label}: {', '.join(ids)}")
    for inv_id, reason in result.skipped:
        console.print(f"  [yellow]skipped[/] {inv_id}: {reason}")


@app.command()
def check(project: Path = typer.Option(Path("."), help="Target repo root")) -> None:
    """Run the checkers and report adherence per invariant (exit 1 on error-severity failure)."""
    config = load_config(project.resolve())
    invariants = parse_invariants(config.invariants_path)
    gen_result = generate(invariants, config)
    results = run_checks(
        invariants, config,
        gen_result.importlinter_ids, gen_result.depcruiser_ids, gen_result.astgrep_ids,
        gen_result.pbt_ids,
    )

    table = Table(title="archagent check")
    table.add_column("Invariant")
    table.add_column("Checker")
    table.add_column("Result")
    table.add_column("Detail")
    failed = 0
    for r in sorted(results, key=lambda x: x.invariant_id):
        if r.skipped_reason:
            mark, detail = "[yellow]SKIP[/]", r.skipped_reason
        elif r.passed:
            mark, detail = "[green]PASS[/]", ""
        else:
            mark = "[red]FAIL[/]" if r.severity == "error" else "[yellow]WARN[/]"
            shown = r.findings[:3]
            parts = [(f"{f.detail} ({f.file}:{f.line})" if f.file else f.detail) for f in shown]
            if len(r.findings) > len(shown):
                parts.append(f"(+{len(r.findings) - len(shown)} more)")
            detail = "; ".join(parts)
            if r.severity == "error":
                failed += 1
        table.add_row(r.invariant_id, r.checker, mark, detail)
    console.print(table)

    if failed:
        console.print(f"[red]{failed} invariant(s) violated.[/]")
        raise typer.Exit(code=1)
    console.print("[green]All invariants hold.[/]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

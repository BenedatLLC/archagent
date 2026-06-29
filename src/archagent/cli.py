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
from .init import KNOWN_AGENTS, init_project
from .invariants import parse_invariants

app = typer.Typer(add_completion=False, help="Keep code adherent to a described architecture.")
console = Console()


@app.command()
def init(
    project: Path = typer.Argument(Path("."), help="Target repo to scaffold into"),
    agents: str = typer.Option(
        ",".join(KNOWN_AGENTS), help="Comma-separated agents to set up (claude,cursor,openhands), or 'none'"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Scaffold archagent.toml, the architecture/ templates, and per-agent skills into a repo."""
    root = project.resolve()
    selected = [] if agents.strip().lower() in ("", "none") else [a.strip() for a in agents.split(",") if a.strip()]
    unknown = [a for a in selected if a not in KNOWN_AGENTS]
    if unknown:
        console.print(f"[yellow]unknown agent(s) ignored: {', '.join(unknown)}[/] (known: {', '.join(KNOWN_AGENTS)})")
    selected = [a for a in selected if a in KNOWN_AGENTS]

    result = init_project(root, agents=selected, force=force)
    console.print(f"Detected languages: [bold]{', '.join(result.languages)}[/]")
    if selected:
        console.print(f"Agents: [bold]{', '.join(selected)}[/]")
    for path in result.created:
        console.print(f"  [green]created[/] {path.relative_to(root)}")
    for path in result.skipped:
        console.print(f"  [yellow]exists, skipped[/] {path.relative_to(root)}  (use --force)")
    console.print("\nNext: edit [bold]architecture/invariants.md[/], then run [bold]archagent check[/].")


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
                       ("ast-grep", result.astgrep_ids)):
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
            detail = "; ".join(f"{f.detail} ({f.file}:{f.line})" if f.file else f.detail for f in r.findings)
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

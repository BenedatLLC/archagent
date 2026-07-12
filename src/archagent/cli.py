"""archagent CLI.

  archagent init    scaffold archagent.toml + architecture/ templates into a repo
  archagent gen     parse architecture/invariants.md -> generate checker configs
  archagent check   regenerate, run the checkers, report pass/fail per invariant
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .check import run_checks
from .config import load_config
from .drift import find_drift
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


@app.command()
def drift(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    exit_code: bool = typer.Option(False, "--exit-code", help="Exit 1 if any drift is found (for CI)"),
    as_json: bool = typer.Option(False, "--json", help="Emit the drift report as JSON (for tooling / agents)"),
) -> None:
    """Reflexion-diff: report where the architecture/ docs and the code have drifted (informational)."""
    config = load_config(project.resolve())
    result = find_drift(config)

    if as_json:
        print(json.dumps({
            "dangling": [{"doc": d, "ref": r} for d, r in result.dangling],
            "stale": [{"doc": d, "detail": x} for d, x in result.stale],
            "undocumented": result.undocumented,
            "undeclared_deps": [{"subsystem": s, "imports": t} for s, t in result.undeclared_deps],
            "stale_deps": [{"subsystem": s, "declares": t} for s, t in result.stale_deps],
            "undocumented_entrypoints": [{"name": n, "target": t} for n, t in result.undocumented_entrypoints],
            "undocumented_routes": [{"method": m, "path": p} for m, p in result.undocumented_routes],
            "dangling_routes": [{"method": m, "path": p} for m, p in result.dangling_routes],
            "undocumented_config": result.undocumented_config,
            "dangling_config": result.dangling_config,
            "undocumented_services": result.undocumented_services,
            "dangling_services": result.dangling_services,
            "openapi_spec": result.openapi_spec,
            "git_available": result.git_available,
            "covers_declared": result.covers_declared,
        }, indent=2))
        if exit_code and result.any:
            raise typer.Exit(code=1)
        return

    console.print("[bold]Architecture drift[/] — architecture/ vs code\n")
    if result.dangling:
        console.print(f"[red]Dangling references ({len(result.dangling)})[/] — a doc names code that no longer exists:")
        for doc, ref in result.dangling:
            console.print(f"  {doc} → {ref}")
        console.print("")
    if result.stale:
        console.print(f"[yellow]Possibly stale ({len(result.stale)})[/] — code changed after the doc (git):")
        for doc, detail in result.stale:
            console.print(f"  {doc} — {detail}")
        console.print("")
    if result.undocumented:
        shown = result.undocumented[:10]
        console.print(f"[cyan]Undocumented modules ({len(result.undocumented)})[/] — code owned by no subsystem's Covers:")
        for f in shown:
            console.print(f"  {f}")
        if len(result.undocumented) > len(shown):
            console.print(f"  (+{len(result.undocumented) - len(shown)} more)")
        console.print("")
    if result.undeclared_deps:
        console.print(f"[red]Undeclared dependencies ({len(result.undeclared_deps)})[/] — a subsystem imports another it doesn't declare (Depends-on):")
        for s, t in result.undeclared_deps:
            console.print(f"  {s} → {t}")
        console.print("")
    if result.stale_deps:
        console.print(f"[yellow]Stale declared dependencies ({len(result.stale_deps)})[/] — declared Depends-on with no matching import:")
        for s, t in result.stale_deps:
            console.print(f"  {s} → {t}")
        console.print("")
    if result.undocumented_entrypoints:
        console.print(f"[cyan]Undocumented entry points ({len(result.undocumented_entrypoints)})[/] — declared but not in any doc:")
        for n, t in result.undocumented_entrypoints:
            console.print(f"  {n} = {t}")
        console.print("")
    if result.undocumented_routes:
        intended = f"the OpenAPI spec ({result.openapi_spec})" if result.openapi_spec else "any doc"
        console.print(f"[red]Undocumented routes ({len(result.undocumented_routes)})[/] — a web route not in {intended}:")
        for m, p in result.undocumented_routes:
            console.print(f"  {m} {p}")
        console.print("")
    if result.dangling_routes:
        console.print(f"[yellow]Dangling routes ({len(result.dangling_routes)})[/] — in the OpenAPI spec, not in code:")
        for m, p in result.dangling_routes:
            console.print(f"  {m} {p}")
        console.print("")
    if result.undocumented_config:
        console.print(f"[red]Undocumented config ({len(result.undocumented_config)})[/] — env keys read in code, not in the manifest:")
        for k in result.undocumented_config:
            console.print(f"  {k}")
        console.print("")
    if result.dangling_config:
        console.print(f"[yellow]Dangling config ({len(result.dangling_config)})[/] — declared but not read in code:")
        for k in result.dangling_config:
            console.print(f"  {k}")
        console.print("")
    if result.undocumented_services:
        console.print(f"[red]Undocumented services ({len(result.undocumented_services)})[/] — in IaC, not in the deployment view:")
        for s in result.undocumented_services:
            console.print(f"  {s}")
        console.print("")
    if result.dangling_services:
        console.print(f"[yellow]Dangling services ({len(result.dangling_services)})[/] — declared but not found in IaC:")
        for s in result.dangling_services:
            console.print(f"  {s}")
        console.print("")

    if not result.git_available:
        console.print("[dim](git not available — stale-doc check skipped)[/]")
    if not result.covers_declared:
        console.print("[dim](no **Covers:** in subsystem docs — undocumented-code check skipped)[/]")
    if not result.any:
        console.print("[green]No drift found.[/]")
        return
    console.print("[dim]Reconcile via /archagent-describe (update mode).[/]")
    if exit_code:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

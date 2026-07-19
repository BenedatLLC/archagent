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
from .evaluate import evaluate as run_evaluate
from .generate import generate
from .invscan import scan_invariants
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


@app.command(name="help")
def help_command() -> None:
    """Concise overview of the archagent lifecycle and the command/skill for each step."""
    console.print(
        "\n[bold]archagent[/] runs a reflexion loop over your architecture:\n"
        "  [bold]describe[/] the intended design → [bold]check[/] & [bold]diff[/] against the code → "
        "[bold]evaluate[/] its health → [bold]update[/].\n"
        "Set up once, then cycle at design-review time and per-commit.\n"
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("Step")
    table.add_column("Run")
    table.add_column("What it does")
    for step, run, what in (
        ("Set up", "archagent init", "scaffold architecture/ + install the agent skills"),
        ("1. Describe", "/archagent-describe", "document the architecture — build first, update after"),
        ("2. Add rules", "/archagent-invariant", "add a checkable invariant (or edit invariants.md)"),
        ("3. Enforce", "archagent check · /archagent-check", "run the checkers, report pass/fail per invariant"),
        ("4. Diff", "archagent drift", "where docs and code diverged — the update work-list"),
        ("5. Evaluate", "archagent evaluate · /archagent-evaluate", "system-level architecture smells + fixes"),
        ("6. Update", "/archagent-describe", "reconcile the artifact from drift + evaluate; add ADRs"),
        ("Maintain", "archagent upgrade", "refresh the installed skills/prompts to the latest"),
    ):
        table.add_row(step, run, what)
    console.print(table)
    console.print(
        "\n[dim]Cadence: check on every commit; describe + evaluate at design-review and periodically.\n"
        "`archagent gen` regenerates checker configs (check does this for you). Run any command with "
        "[bold]--help[/] for its options.\n"
        "Format spec: docs/ADL-SPEC.md  ·  planned work: docs/ROADMAP.md[/]\n"
    )


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
            "missing_deploy_edges": [{"service": a, "depends_on": b} for a, b in result.missing_deploy_edges],
            "extra_deploy_edges": [{"service": a, "depends_on": b} for a, b in result.extra_deploy_edges],
            "connector_mismatches": [{"subsystem": s, "target": t, "declared": d, "observed": o}
                                     for s, t, d, o in result.connector_mismatches],
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
        console.print(f"[red]Undeclared dependencies ({len(result.undeclared_deps)})[/] — a subsystem imports another it doesn't declare (Connects):")
        for s, t in result.undeclared_deps:
            console.print(f"  {s} → {t}")
        console.print("")
    if result.stale_deps:
        console.print(f"[yellow]Stale declared dependencies ({len(result.stale_deps)})[/] — declared Connects import-edge with no matching import:")
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
    if result.missing_deploy_edges:
        console.print(f"[red]Missing deployment edges ({len(result.missing_deploy_edges)})[/] — the code depends across services the deployment doesn't wire (depends_on):")
        for a, b in result.missing_deploy_edges:
            console.print(f"  {a} → {b}")
        console.print("")
    if result.extra_deploy_edges:
        console.print(f"[yellow]Extra deployment edges ({len(result.extra_deploy_edges)})[/] — depends_on with no matching code dependency:")
        for a, b in result.extra_deploy_edges:
            console.print(f"  {a} → {b}")
        console.print("")
    if result.connector_mismatches:
        console.print(f"[red]Connector-kind mismatches ({len(result.connector_mismatches)})[/] — the code contradicts a declared connector kind:")
        for s, t, d, o in result.connector_mismatches:
            console.print(f"  {s} → {t}: declared [bold]{d}[/], code does [bold]{o}[/]")
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


_GROUP_TITLES = {
    "A": "Data & source-of-truth",
    "B": "Wrong boundaries / abstractions",
    "C": "Static structural",
    "D": "Lifecycle support",
}
_SEV_STYLE = {"high": "red", "med": "yellow", "low": "cyan"}


@app.command()
def evaluate(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    group: str = typer.Option("", help="Limit to one group: A, B, C, or D"),
    min_severity: str = typer.Option("low", help="Only show findings at/above this severity: low|med|high"),
    no_history: bool = typer.Option(False, "--no-history", help="Skip git co-change mining (regime A only, offline)"),
    since: str = typer.Option("", help="Co-change window as a git date, e.g. '12.months' or '2025-01-01'"),
    as_json: bool = typer.Option(False, "--json", help="Emit findings as JSON (for the skill / tooling)"),
    exit_code: bool = typer.Option(False, "--exit-code", help="Exit 1 if any shown finding remains (opt-in CI gate)"),
) -> None:
    """Judge the architecture for system-level smells (candidate signals for /archagent-evaluate)."""
    config = load_config(project.resolve())
    result = run_evaluate(config, history=not no_history, since=since or None)

    sev_floor = {"low": 0, "med": 1, "high": 2}.get(min_severity.lower(), 0)
    order = {"low": 0, "med": 1, "high": 2}
    want_group = group.strip().upper()
    findings = [
        f for f in result.findings
        if order[f.severity] >= sev_floor and (not want_group or f.group == want_group)
    ]

    if as_json:
        print(json.dumps({
            "findings": [{
                "sign": f.sign, "group": f.group, "severity": f.severity, "title": f.title,
                "subjects": f.subjects, "detail": f.detail, "recommendation": f.recommendation,
                "regime": f.regime, "confidence": f.confidence,
            } for f in findings],
            "tier_declared": result.tier_declared,
            "git_available": result.git_available,
            "history_analyzed": result.history_analyzed,
        }, indent=2))
        if exit_code and findings:
            raise typer.Exit(code=1)
        return

    console.print("[bold]Architecture evaluation[/] — system-level smell candidates\n")
    grouped: dict[str, list] = {}
    for f in sorted(findings, key=lambda x: order[x.severity], reverse=True):
        grouped.setdefault(f.group, []).append(f)
    for g in ("A", "B", "C", "D"):
        items = grouped.get(g)
        if not items:
            continue
        console.print(f"[bold]{g} — {_GROUP_TITLES[g]}[/] ({len(items)})")
        for f in items:
            style = _SEV_STYLE[f.severity]
            subj = ", ".join(f.subjects[:4]) + (f" (+{len(f.subjects) - 4} more)" if len(f.subjects) > 4 else "")
            console.print(f"  [{style}]{f.severity.upper():4}[/] {f.title} — {subj}")
            console.print(f"       {f.detail}")
            console.print(f"       [dim]→ {f.recommendation} ({f.confidence} confidence, {f.regime})[/]")
        console.print("")

    if not result.tier_declared:
        console.print("[dim](no **Tier:** in subsystem docs — leaky-abstraction / layering check skipped)[/]")
    if no_history:
        console.print("[dim](--no-history — co-change smells skipped)[/]")
    elif not result.git_available:
        console.print("[dim](git not available — co-change smells skipped)[/]")
    if not findings:
        console.print("[green]No system-level smells found.[/]")
        return
    console.print("[dim]These are candidates — run /archagent-evaluate to judge, cluster, and prioritize.[/]")
    if exit_code:
        raise typer.Exit(code=1)


@app.command(name="scan-invariants")
def scan_invariants_cmd(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    markers_only: bool = typer.Option(False, "--markers-only", help="Only high-confidence markers (skip noisy modal language)"),
    as_json: bool = typer.Option(False, "--json", help="Emit candidates as JSON (for the describe skill / tooling)"),
) -> None:
    """Scan docs + code for stated invariants — candidates for /archagent-describe to lift into invariants.md."""
    config = load_config(project.resolve())
    candidates = scan_invariants(config)
    if markers_only:
        candidates = [c for c in candidates if c.kind == "marker"]

    if as_json:
        print(json.dumps({
            "candidates": [
                {"source": c.source, "text": c.text, "kind": c.kind, "confidence": c.confidence, "guess": c.guess}
                for c in candidates
            ],
        }, indent=2))
        return

    console.print("[bold]Stated-invariant candidates[/] — for /archagent-describe to classify, verify, and curate\n")
    if not candidates:
        console.print("[green]No invariant statements found in docs or code.[/]")
        return
    markers = [c for c in candidates if c.kind == "marker"]
    modal = [c for c in candidates if c.kind == "modal"]
    if markers:
        console.print(f"[bold]Explicit markers ({len(markers)})[/] — high confidence:")
        for c in markers:
            console.print(f"  [cyan]{c.guess:10}[/] {c.source}\n       {c.text}")
        console.print("")
    if modal:
        console.print(f"[bold]Modal language ({len(modal)})[/] — candidates, judge each:")
        for c in modal:
            console.print(f"  [dim]{c.guess:10}[/] {c.source}\n       {c.text}")
        console.print("")
    console.print("[dim]Each is a candidate: classify into the DSL, verify with `check` (+ non-vacuous), and\n"
                  "capture as a prose row (source cited) — promote to an active rule only on a passing check.[/]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

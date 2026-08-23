"""archagent CLI.

  archagent init    scaffold archagent.toml + architecture/ templates into a repo
  archagent gen     parse architecture/invariants.md -> generate checker configs
  archagent check   regenerate, run the checkers, report pass/fail per invariant
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .check import run_checks
from .config import load_config
from .docscan import lint_docs
from .drift import find_drift, module_map
from .evaluate import evaluate as run_evaluate
from .generate import generate
from .graph import collect_subsystems, graph_block, write_to_index
from .cochange import resolve_as_of
from .history import PROFILE_PATH, gather_evidence, history_profile, save_profile
from .hooks import install_hook
from .invscan import scan_invariants
from .investigations import RATINGS, record as _record_inv
from .init import KNOWN_AGENTS, detect_agents, init_project, upgrade_project
from .invariants import parse_invariants
from .status import status as run_status

#: a `path.ext:line` or `path.ext` citation, the evidence a verified prose rule should carry
_CITES = re.compile(r"[\w/.-]+\.[A-Za-z]{1,5}(?::\d+)?")

app = typer.Typer(add_completion=False, help="Keep code adherent to a described architecture.")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        from . import __version__
        # Plain `print`, not `console.print`: rich highlights a bare version as a number and emits colour
        # codes, and the first consumer of this is a script pinning what produced a scorecard.
        print(__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Print the archagent version and exit."),
) -> None:
    """Keep code adherent to a described architecture."""


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
        # The highest-leverage line in the codex support: Codex keeps no per-repo directory, so it can
        # never be auto-detected (see `init.detect_agents`). Naming it here is what turns an undetectable
        # agent into a discoverable one, and it is what makes opt-in acceptable rather than merely
        # defensible.
        return [], ("no coding agent detected (.claude/.cursor/.openhands) — re-run with "
                    "--agents claude,cursor,openhands, or --agents codex "
                    "(Codex keeps no per-repo directory, so it cannot be auto-detected)")
    selected = [a.strip() for a in agents_opt.split(",") if a.strip()]
    unknown = [a for a in selected if a not in KNOWN_AGENTS]
    msg = f"unknown agent(s) ignored: {', '.join(unknown)}" if unknown else None
    return [a for a in selected if a in KNOWN_AGENTS], msg


def _report_settings(result) -> None:
    """Show what went into `archagent.toml` and ask for it to be checked here, not in the README.

    Issue #27. The README used to say "open archagent.toml and check root_package and source_paths",
    which is a check a reader means to perform and does not. The tool knows which values it detected,
    which it defaulted, and whether a source path holds any matching files at all — printing that turns an
    instruction into a decision in front of them.

    Worth the space because the failure is silent and total: a `root_package` naming nothing scopes every
    BOUNDARY contract to an empty module set, and `check` then reports that all invariants hold, having
    examined none of them.
    """
    if not result.settings:
        return
    console.print("\n[bold]Configuration written to archagent.toml[/] — check these before continuing:\n")
    for s in result.settings:
        mark = "[red]![/]" if s.problem else " "
        console.print(f"  {mark} [cyan]{s.key:24}[/] {s.value:22} [dim]({s.origin})[/]")
        if s.problem:
            console.print(f"      [red]{s.problem}[/]")
    if any(s.problem for s in result.settings):
        console.print("\n  [yellow]Fix the flagged values in archagent.toml before running "
                      "`archagent check`.[/]\n  A path that matches no files scopes every rule to "
                      "nothing, and the run then reports\n  that all invariants hold, having checked "
                      "none of them.")


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
        "Describe helpers: status (coverage) · graph --write (system map) · lint-docs (Mermaid) · modules.\n"
        "Evaluate helper: history-profile (how this repo words its bug-fix commits, learned not hard-coded).\n"
        "`archagent gen` regenerates checker configs (check does this for you). Run any command with "
        "[bold]--help[/] for its options.\n"
        "Format spec (ADL-SPEC) + roadmap: https://github.com/BenedatLLC/archagent[/]\n"
    )


@app.command()
def init(
    project: Path = typer.Argument(Path("."), help="Target repo to scaffold into"),
    agents: str = typer.Option("auto", help="Agents: 'auto' (detect), 'all', 'none', or e.g. 'claude,cursor'"),
    arch_dir: str = typer.Option("", "--arch-dir", help="Where the architecture docs live, relative to the repo (e.g. docs/architecture). Skips the prompt."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: don't prompt; use defaults (architecture/) where an option isn't given."),
    wire: bool = typer.Option(False, "--wire", help="Also add an additive pointer to the repo's top-level CLAUDE.md / AGENTS.md"),
    force: bool = typer.Option(False, "--force", help="Overwrite user-owned files too (re-scaffold — clobbers your edits)"),
) -> None:
    """Scaffold archagent.toml, the architecture/ templates, and per-agent skills into a repo."""
    root = project.resolve()
    selected, advisory = _resolve_agents(root, agents, detect_agents)
    if advisory:
        console.print(f"[yellow]{advisory}[/]")
    location = _resolve_arch_dir(root, arch_dir, yes)
    result = init_project(root, agents=selected, force=force, wire=wire, arch_dir=location)
    _report(result, root)
    _report_settings(result)
    console.print(f"\nArchitecture docs: [bold]{location}/[/]")
    if selected and not wire:
        console.print("Tip: wire archagent into your agent's top-level instructions with [bold]--wire[/], "
                      f"or have the agent add a pointer to [bold]{location}/AGENTS.md[/].")
    console.print(f"\nNext: run [bold]/archagent-describe[/] (or edit {location}/invariants.md), then [bold]archagent check[/].")


_DOC_DIR_CANDIDATES = ("docs", "doc", "design", "designs", "specs", "spec")


def _resolve_arch_dir(root: Path, arch_dir_opt: str, yes: bool) -> str:
    """Resolve where the architecture artifact goes: an explicit --arch-dir wins; --yes / non-interactive
    falls back to the default; otherwise suggest the default + combos with any doc dirs found, or custom."""
    if arch_dir_opt.strip():
        return arch_dir_opt.strip().strip("/")
    default = "architecture"
    found = [d for d in _DOC_DIR_CANDIDATES if (root / d).is_dir()]
    options = [default] + [f"{d}/architecture" for d in found]
    if yes or not sys.stdin.isatty():
        return default
    console.print("\n[bold]Where should the architecture docs live?[/] (relative to the repo root)")
    for i, opt in enumerate(options, 1):
        tag = "  [dim](default)[/]" if i == 1 else ""
        console.print(f"  [bold]{i}[/]) {opt}/{tag}")
    console.print(f"  [bold]{len(options) + 1}[/]) custom…")
    choice = typer.prompt("Select", default="1").strip()
    if choice == str(len(options) + 1) or choice.lower() == "custom":
        return typer.prompt("Path (relative to repo root)", default=default).strip().strip("/") or default
    if choice.isdigit() and 1 <= int(choice) <= len(options):
        return options[int(choice) - 1]
    return choice.strip("/") or default  # treat a free-typed value as a custom path


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
    arch_dir = load_config(root).arch_dir  # honor the location recorded at init time
    result = upgrade_project(root, agents=selected, arch_dir=arch_dir)
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
def check(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    skip_pbt: bool = typer.Option(False, "--skip-pbt", help="Skip the property-based-test tier (run the fast static tiers only)"),
) -> None:
    """Run the checkers and report adherence per invariant (exit 1 on error-severity failure)."""
    config = load_config(project.resolve())
    invariants = parse_invariants(config.invariants_path)
    gen_result = generate(invariants, config)
    results = run_checks(
        invariants, config,
        gen_result.importlinter_ids, gen_result.depcruiser_ids, gen_result.astgrep_ids,
        gen_result.pbt_ids, skip_pbt=skip_pbt,
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

    # Rules nothing checked must not be invisible. An artifact whose invariants are all `prose` tier
    # produced an empty table and "All invariants hold." — while two of its eight rules were false. That
    # is the silent-failure shape ADR 0002 exists to forbid: "nothing was checked" rendering exactly like
    # "everything passed". A prose row is a claim asserted by a person; the tool has verified nothing
    # about it and must say so.
    if gen_result.skipped:
        console.print(f"\n[yellow]Not checked ({len(gen_result.skipped)})[/] — asserted in "
                      f"invariants.md, verified by nobody:")
        for inv_id, why in gen_result.skipped:
            console.print(f"  [yellow]{inv_id}[/]  {why}")

    # A prose rule with a stated `Verification` is in a materially different state from one nobody has
    # ever checked, and without the column they look identical. Calibration round 4 had 52 of 56 rows at
    # tier `prose`, several backed by a real test the row did not mention, and no way to tell which.
    verified = [i for i in invariants if i.is_prose and i.verification]
    unverified = [i for i in invariants if i.unverified]
    if verified or unverified:
        console.print(f"\n[bold]Prose rules[/] — {len(verified)} state how they are verified, "
                      f"{len(unverified)} do not")
        for i in verified[:6]:
            console.print(f"  [green]{i.id}[/]  {i.verification[:76]}")
        for i in unverified[:6]:
            grad = f"  [dim]→ {i.graduation[:50]}[/]" if i.graduation else ""
            console.print(f"  [yellow]{i.id}[/]  no Verification recorded{grad}")
        if len(verified) > 6 or len(unverified) > 6:
            console.print("  [dim]…[/]")
        if unverified:
            console.print("  [dim]`prose` means this tool cannot generate a checker, not that nobody "
                          "checks it. Name the test, the\n  command or the audit that confirms the rule "
                          "— or say plainly that nothing does.[/]")

    # A prose row marked `active` says the rule is in force while nothing can confirm it. Twice now a
    # rule in that state was simply false — and in both cases the `Why` column held rationale with no
    # evidence, so "does Why cite anything?" separates a verified assertion from an unverified one.
    unevidenced = [i for i in invariants
                   if i.tier == "prose" and i.status == "active" and not _CITES.search(i.why or "")]
    if unevidenced:
        console.print(f"\n[yellow]Asserted active with no recorded evidence ({len(unevidenced)})[/] — a "
                      f"prose rule cannot be checked,\nso `active` is a claim someone made. Cite the "
                      f"path:line you verified it at, or mark it `proposed`:")
        for i in unevidenced:
            console.print(f"  [yellow]{i.id}[/]  {(i.why or '(no why)')[:70]}")

    if failed:
        console.print(f"[red]{failed} invariant(s) violated.[/]")
        raise typer.Exit(code=1)
    if not results:
        console.print(f"[yellow]No invariant was checked[/] — "
                      f"{len(gen_result.skipped)} rule(s) present, none enforceable. "
                      f"This is not a passing run.")
        return
    console.print(f"[green]All {len(results)} checked invariant(s) hold.[/]"
                  + (f" [yellow]{len(gen_result.skipped)} not checked.[/]" if gen_result.skipped else ""))


@app.command()
def drift(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    until: str = typer.Option("", help="Ignore commits after this git date — bounds the staleness check"),
    as_of: str = typer.Option("", "--as-of", help="Set --until from a revision's own date (e.g. a tag). Does NOT check anything out."),
    exit_code: bool = typer.Option(False, "--exit-code", help="Exit 1 if any drift is found (for CI)"),
    as_json: bool = typer.Option(False, "--json", help="Emit the drift report as JSON (for tooling / agents)"),
) -> None:
    """Reflexion-diff: report where the architecture/ docs and the code have drifted (informational)."""
    config = load_config(project.resolve())
    result = find_drift(config, until=(resolve_as_of(project.resolve(), as_of) if as_of else (until or None)))

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
            "mistiered": [{"subsystem": s, "tier": tr} for s, tr in result.mistiered],
            "openapi_spec": result.openapi_spec,
            "git_available": result.git_available,
            "covers_declared": result.covers_declared,
        }, indent=2))
        if exit_code and result.any:
            raise typer.Exit(code=1)
        return

    # the configured directory, not the default name: this header claimed `architecture/` on a repo whose
    # artifact is at `docs/architecture/`, naming a path the reader could not find
    console.print(f"[bold]Architecture drift[/] — {config.arch_dir}/ vs code\n")
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
    if result.mistiered:
        console.print(f"[yellow]Mis-tiered subsystems ({len(result.mistiered)})[/] — covers only test or "
                      f"migration code but claims a place on the layer ladder:")
        for sub, tier in result.mistiered:
            console.print(f"  {sub} (**Tier:** {tier}) — tests and migrations are not a layer beneath the "
                          f"code they exercise; use a non-layered tier such as `test` or `migration`")
        console.print("")
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
    "E": "Maintainability (change history)",
    "F": "Single source of truth (code duplication)",
}
_GROUPS = tuple(_GROUP_TITLES)
_SEV_STYLE = {"high": "red", "med": "yellow", "low": "cyan"}


@app.command()
def evaluate(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    group: str = typer.Option("", help="Limit to one group: A, B, C, D, E, or F"),
    min_severity: str = typer.Option("low", help="Only show findings at/above this severity: low|med|high"),
    no_history: bool = typer.Option(False, "--no-history", help="Skip git co-change mining (regime A only, offline)"),
    since: str = typer.Option("", help="Co-change window as a git date, e.g. '12.months' or '2025-01-01'"),
    until: str = typer.Option("", help="Ignore commits after this git date — bounds the history window"),
    as_of: str = typer.Option("", "--as-of", help="Set --until from a revision's own date (e.g. a tag). Does NOT check anything out: check out the same revision yourself, or the run reads present-day code against past history."),
    as_json: bool = typer.Option(False, "--json", help="Emit findings as JSON (for the skill / tooling)"),
    exit_code: bool = typer.Option(False, "--exit-code", help="Exit 1 if any shown finding remains (opt-in CI gate)"),
) -> None:
    """Judge the architecture for system-level smells (candidate signals for /archagent-evaluate)."""
    config = load_config(project.resolve())
    window = resolve_as_of(project.resolve(), as_of) if as_of else (until or None)
    result = run_evaluate(config, history=not no_history, since=since or None, until=window)

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
                "id": f.id,
                "sign": f.sign, "group": f.group, "severity": f.severity, "title": f.title,
                "subjects": f.subjects, "detail": f.detail, "recommendation": f.recommendation,
                "regime": f.regime, "confidence": f.confidence, "values": f.values,
                "investigate": f.investigate, "triage_reason": f.triage_reason,
                "investigation": f.investigation,
            } for f in findings],
            "tier_declared": result.tier_declared,
            "git_available": result.git_available,
            "history_analyzed": result.history_analyzed,
            "inactive": [{"family": i.family, "reason": i.reason, "signs": list(i.signs)}
                         for i in result.inactive],
            "truncated": [{"family": fam, "shown": n, "found": m} for fam, n, m in result.truncated],
            "history": {
                "ran": result.history_ran,
                "commits_seen": result.commits_seen,
                "commits_analyzed": result.history_analyzed,
                "bulk_skipped": result.bulk_skipped,
                "conventional_pct": result.conventional_pct,
                "cautions": result.history_cautions,
                "profile": result.history_profile.to_dict() if result.history_profile else None,
            },
        }, indent=2))
        if exit_code and findings:
            raise typer.Exit(code=1)
        return

    console.print("[bold]Architecture evaluation[/] — system-level smell candidates\n")
    grouped: dict[str, list] = {}
    for f in sorted(findings, key=lambda x: order[x.severity], reverse=True):
        grouped.setdefault(f.group, []).append(f)
    for g in _GROUPS:
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
            if f.investigation:
                inv = f.investigation
                stale = " [yellow](stale)[/]" if inv["stale"] else ""
                console.print(f"       [bold]investigated: {inv['rating'].upper()}[/]{stale} — "
                              f"{inv['by']}, {inv['dated']}  [dim]{inv['path']}[/]")
            elif f.investigate:
                console.print(f"       [bold yellow]?[/] worth investigating — {f.triage_reason}")
                console.print(f"         [dim]archagent investigate {f.id}[/]")
        console.print("")

    if result.history_ran:
        console.print(f"[bold]History[/] — {result.history_analyzed} of {result.commits_seen} commit(s) mined "
                      f"({result.conventional_pct}% conventional, {result.bulk_skipped} bulk skipped)")
        prof = result.history_profile
        if prof:
            console.print(f"  [dim]bug-fix wording learned for this repo: {prof.style} "
                          f"({prof.fix_matched}/{prof.subjects_sampled} subjects, {prof.source})[/]")
        for c in result.history_cautions:
            console.print(f"  [yellow]caution:[/] {c}")
        console.print("")
    if result.truncated:
        console.print("[bold]Truncated[/] — these lists are the highest-ranked, not everything found:")
        for fam, shown, found in result.truncated:
            console.print(f"  [dim]{fam}[/] — showing {shown} of {found}")
        console.print("")
    if result.inactive:
        console.print("[bold]Inactive signals[/] — produced no findings for lack of metadata (not proof of "
                      "health here):")
        for fam, why, _signs in result.inactive:
            console.print(f"  [dim]{fam}[/] — {why}")
        console.print("")

    if not findings:
        console.print("[green]No system-level smells found in the active signals.[/]")
        return
    # The caveat belongs to the severities, not to the triage block. It used to live inside `if flagged`,
    # so a run where nothing was marked for investigation printed 65 findings with HIGH and MED severities
    # and never said what those words mean. Round 5's reviewer scored `finding_restraint` 2 of 5 and named
    # exactly this: "the body gives HIGH/MED severity without saying it is mechanical".
    console.print("[dim]Severity above is mechanical — it counts files and commits, never consequences. A "
                  "finding is\nonly minor, moderate or critical once someone has read the code.[/]\n")
    flagged = [f for f in findings if f.investigate]
    if flagged:
        console.print(f"[bold]{len(flagged)} finding(s) marked for investigation.[/] To find out whether "
                      "one of these actually breaks something, run:")
        console.print(f"  [bold]archagent investigate {flagged[0].id}[/]")
        console.print("[dim]  …which prints a brief for you or your agent to work through.[/]\n")
    console.print("[dim]These are candidates — run /archagent-evaluate to judge, cluster, and prioritize.[/]")
    if exit_code:
        raise typer.Exit(code=1)


@app.command(name="install-hook")
def install_hook_cmd(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    skip_pbt: bool = typer.Option(False, "--skip-pbt", help="Hook runs the static tiers only (skip property-based tests, which your test suite already covers)"),
) -> None:
    """Install a git pre-commit hook that runs `archagent check` on every commit."""
    root = project.resolve()
    try:
        result = install_hook(root, skip_pbt=skip_pbt)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1)
    runs = "archagent check --skip-pbt" if result.skip_pbt else "archagent check"
    console.print(f"[green]{result.action}[/] {result.path.relative_to(root)} — runs [bold]{runs}[/] on commit.")
    console.print("[dim]Requires `archagent` on PATH (uv tool install archagent). "
                  "Delete the archagent block in that file to disable.[/]")


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


@app.command()
def investigate(
    finding: str = typer.Argument(..., help="A finding id from `archagent evaluate` (sign:owner:hash)"),
    project: Path = typer.Option(Path("."), help="Target repo root"),
    until: str = typer.Option("", help="Ignore commits after this git date (match the run that found it)"),
    record: Path = typer.Option(None, "--record", help="Markdown file holding a completed investigation to store"),
    rating: str = typer.Option("", help=f"Consequence rating when recording: {'|'.join(RATINGS)}"),
    by: str = typer.Option("", help="Who did the investigation"),
) -> None:
    """Print an investigation brief for one finding — the questions that turn a candidate into a verdict.

    `evaluate`'s severity is mechanical: it counts files and commits. Whether a finding is minor, moderate
    or critical depends on what it *causes*, which only reading the code can establish. This command does
    not answer that; it states the questions precisely enough that a person or a coding agent can, and
    names the files to start from.
    """
    config = load_config(project.resolve())
    result = run_evaluate(config, until=until or None)
    match = next((f for f in result.findings if f.id == finding), None)
    if match is None:
        console.print(f"[red]No finding with id[/] {finding}")
        marked = [f for f in result.findings if f.investigate]
        if marked:
            console.print("\nFindings currently marked for investigation:")
            for f in marked[:10]:
                console.print(f"  [dim]{f.id}[/]  {f.title} — {f.subjects[0]}")
        raise typer.Exit(code=1)

    if record is not None:
        if rating not in RATINGS:
            console.print(f"[red]--rating must be one of[/] {', '.join(RATINGS)}")
            console.print("[dim]The rating is a claim about consequence, not about how much duplication "
                          "there is: minor = nothing depends on it or a typo fails loudly; moderate = the "
                          "copies can drift and nothing would catch it; critical = it already misbehaves, "
                          "or a plausible edit makes it misbehave silently.[/]")
            raise typer.Exit(code=1)
        if not record.is_file():
            console.print(f"[red]No such file:[/] {record}")
            raise typer.Exit(code=1)
        dest = _record_investigation(config.architecture_dir, match, rating, record.read_text(), by)
        console.print(f"[green]Recorded[/] {rating} investigation of {match.id}")
        console.print(f"  {dest.relative_to(config.project_root)}")
        console.print("[dim]  Commit it: the next run reports this verdict instead of re-inviting the "
                      "investigation, and the next person starts from your write-up.[/]")
        return

    if match.investigation:
        inv = match.investigation
        flag = " [yellow](STALE — the finding's evidence has moved since)[/]" if inv["stale"] else ""
        console.print(f"\n[bold]Already investigated[/] — rated [bold]{inv['rating']}[/] by "
                      f"{inv['by']} on {inv['dated']}{flag}")
        console.print(f"  {inv['path']}\n  [dim]{inv['summary']}[/]\n")
        if not inv["stale"]:
            console.print("[dim]Re-record with --record to supersede it.[/]\n")

    console.print(f"\n[bold]Investigation brief[/] — {match.title}")
    console.print(f"[dim]{match.id}[/]\n")
    console.print(f"[bold]What the scan found[/]\n  {match.detail}\n")
    if match.triage_reason:
        console.print(f"[bold]Why it was flagged for investigation[/]\n  {match.triage_reason}\n")
    console.print("[bold]Files to start from[/]")
    for s in match.subjects[:12]:
        console.print(f"  {s}")
    if len(match.subjects) > 12:
        console.print(f"  … and {len(match.subjects) - 12} more")
    console.print("")
    for n, q in enumerate(_BRIEF_QUESTIONS, 1):
        console.print(f"[bold]{n}. {q[0]}[/]")
        console.print(f"   [dim]{q[1]}[/]")
    console.print("\n[bold]Then rate it[/] — and the rating must follow from what you found, not from the "
                  "counts above:")
    for level, meaning in _RATINGS:
        console.print(f"   [bold]{level:9}[/] {meaning}")
    console.print("\n[dim]Write the answer as prose with file:line citations. A finding whose "
                  "investigation cannot point at a consequence is minor by definition.[/]\n")


def _record_investigation(arch_dir: Path, match, rating: str, body: str, by: str) -> Path:
    return _record_inv(arch_dir, match.id, rating, body, by, match.subjects, match.values)


_BRIEF_QUESTIONS = [
    ("What is this, in the system's own terms?",
     "Name the concept a reader would recognise — a call type, a provider, a deploy mode — not the value "
     "set. If you cannot say what decision it drives, that is itself the answer."),
    ("Where is it declared, and how many times?",
     "Find every declaration of the same domain: enums, Literal types, TypedDict fields, inline lists. "
     "Count them. One concept declared four times is the finding."),
    ("Has it drifted?",
     "Compare the declarations member by member. Report the counts both ways — values in one and not the "
     "other. Drift is what turns duplication from untidy into dangerous."),
    ("Is there a code path where the mismatch changes behaviour?",
     "This is the question that decides the rating. Trace one concrete path: a value that reaches a "
     "comparison it can never satisfy, a branch that is unreachable, a default that silently applies. "
     "Quote the code and cite file:line."),
    ("If it does misbehave, how does it fail?",
     "Loudly or silently? A wrong answer an operator sees is far less serious than one that reports "
     "success — the worst case found so far was a security hook that returned 'clean' having scanned "
     "nothing."),
    ("Why was it not caught already?",
     "Types, tests, linting, review. If a type checker should have caught it, find out why it did not — "
     "suppressions, `Any`, a config that disables the rule. That explains how it survived and whether "
     "the fix will hold."),
    ("Is it one problem or several?",
     "Value sets can conflate concepts. Say which parts are one decision and which merely share strings; "
     "a finding that is two-thirds real should be reported as such."),
]

_RATINGS = [
    ("minor", "untidy; no behaviour depends on the duplication, or a typo fails loudly"),
    ("moderate", "a real maintenance hazard — the vocabularies can drift and nothing would catch it"),
    ("critical", "it already misbehaves, or a plausible edit makes it misbehave silently"),
]


@app.command(name="history-profile")
def history_profile_cmd(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    write: bool = typer.Option(False, "--write", help=f"Cache the inferred profile to {PROFILE_PATH}"),
    evidence: bool = typer.Option(False, "--evidence",
                                  help="Emit the gathered evidence as JSON for an agent to judge"),
) -> None:
    """Learn how *this* project words its bug-fix commits (the recognizer the history checks use).

    With no options it prints what it inferred. `--evidence` dumps the raw facts — commit guidelines,
    leading-word frequencies, how well each candidate pattern matches — so an agent can judge them and
    write a sharper recognizer to the cache file itself. A cached profile always wins over inference.
    """
    root = project.resolve()
    config = load_config(root)
    if evidence:
        ev = gather_evidence(root, config.architecture_dir)
        ev.pop("_subjects", None)  # the full sample would swamp the useful part
        print(json.dumps(ev, indent=2))
        return

    profile = history_profile(root, config.architecture_dir, use_cache=not write)
    console.print(f"[bold]Commit-wording profile[/] — style [bold]{profile.style}[/] ({profile.source})")
    console.print(f"  {profile.fix_matched} of {profile.subjects_sampled} sampled subject(s) read as "
                  f"fix-labeled ({profile.fix_share:.0%})")
    for p in profile.fix_patterns:
        console.print(f"  [dim]pattern:[/] {p}")
    if profile.guideline_sources:
        console.print(f"  [dim]convention documented in: {', '.join(profile.guideline_sources)}[/]")
    if profile.domain_terms:
        shown = ", ".join(profile.domain_terms[:12])
        more = f" (+{len(profile.domain_terms) - 12} more)" if len(profile.domain_terms) > 12 else ""
        console.print(f"  [dim]domain terms: {shown}{more}[/]")
    for c in profile.cautions:
        console.print(f"  [yellow]caution:[/] {c}")
    if write:
        path = save_profile(root, profile)
        console.print(f"\n[green]Wrote[/] {path.relative_to(root)}")
    else:
        console.print("\n[dim]Inferred, not cached — pass --write to persist it, or --evidence to let an "
                      "agent judge the raw facts.[/]")


@app.command()
def status(project: Path = typer.Option(Path("."), help="Target repo root")) -> None:
    """Repo-scale + coverage snapshot: per top-level package, how much a subsystem's Covers claims."""
    config = load_config(project.resolve())
    report = run_status(config)
    if not report.packages:
        console.print("[yellow]No source files found[/] — check `source_paths` in archagent.toml.")
        return

    table = Table(title="archagent status — coverage by package")
    table.add_column("Package")
    table.add_column("Files", justify="right")
    table.add_column("Documented", justify="right")
    table.add_column("Coverage", justify="right")
    for p in report.packages:
        style = "green" if p.pct >= 80 else "yellow" if p.pct >= 40 else "red"
        bar = "█" * (p.pct // 10) + "░" * (10 - p.pct // 10)
        table.add_row(p.name, str(p.total), f"{p.covered}/{p.total}", f"[{style}]{bar} {p.pct:3}%[/]")
    console.print(table)

    thin = report.thin
    undiagrammed = [d for d in report.depth if d.wants_a_diagram]
    if thin or undiagrammed:
        console.print("\n[bold]Subsystem depth[/] — coverage says a file is described; this says whether "
                      "the description is usable")
        t2 = Table(show_header=True, header_style="bold")
        t2.add_column("Subsystem", no_wrap=True)
        for col in ("Files", "Words", "Per file", "Diag", "Types"):
            t2.add_column(col, justify="right")
        t2.add_column("")
        for d in sorted(report.depth, key=lambda x: x.words_per_file):
            note = "[yellow]thin[/]" if d in thin else (
                "[yellow]no diagram[/]" if d.wants_a_diagram else "")
            t2.add_row(d.name, str(d.files), str(d.words), f"{d.words_per_file:.1f}",
                       str(d.diagrams), str(d.types), note)
        console.print(t2)
        if thin:
            # No hard-wrapped newlines here: rich wraps to the real terminal width, and a manual break
            # lands mid-sentence on any width but the one it was written for.
            console.print("  [yellow]thin[/] — under half the density of the median document here. A terse "
                          "house style is fine; one document far below its siblings is usually a "
                          "subsystem nobody has written up yet.")
        if undiagrammed:
            console.print("  [yellow]no diagram[/] — covers five or more type or table declarations and "
                          "draws nothing. A document whose subject is a set of relationships is "
                          "where prose about directionality loses the reader.")

    # Assignment is not description. A `**Covers:**` glob proves a file is claimed; it says nothing about
    # whether the claiming document mentions it. Calibration round 4 scored 727/727 assigned and 1.00 on
    # the deterministic rubric with a whole cross-cutting mechanism — a 17-line module wiring an
    # optional ORM read cache — never named anywhere in the artifact.
    from .described import described as run_described
    from .drift import _source_files
    desc = run_described(config, _source_files(config))
    if desc.considered:
        groups = desc.by_package()
        console.print(f"\n[bold]Described[/] — of {desc.considered} modules assigned to a subsystem, "
                      f"[bold]{desc.mentioned}[/] ({desc.pct}%) are named in some document"
                      + (f", {desc.grouped} of them only as part of a described directory" if desc.grouped
                         else ""))
        if groups:
            for pkg, us in groups.items():
                console.print(f"  [yellow]{len(us):3}[/] unnamed under [bold]{pkg}[/]"
                              f"  ({sum(u.lines for u in us)} lines)")
            worst = next(iter(groups.values()))
            for u in worst[:4]:
                console.print(f"        {u.path}  [dim]{u.lines} lines[/]")
            console.print("  [dim]A module no document names is assigned, not described. A large count "
                          "under one package is often a\n  deliberate choice to describe a tree "
                          "collectively — read the list rather than the number.[/]")
        if not desc.tests_described and desc.test_files:
            console.print(f"  [yellow]{desc.test_files} test files[/] counted in coverage, and no document "
                          f"discusses the test suite.")

    console.print(
        f"\n[bold]{report.documented_packages} of {len(report.packages)} packages[/] have documented code · "
        f"[bold]{report.pct}%[/] of {report.total} source files covered · "
        f"[bold]{report.subsystem_docs}[/] subsystem doc(s)."
    )
    if not report.covers_declared:
        console.print("[dim](no **Covers:** declared yet — run /archagent-describe to document subsystems)[/]")


@app.command(name="lint-docs")
def lint_docs_cmd(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    as_json: bool = typer.Option(False, "--json", help="Emit issues as JSON (for the describe skill / tooling)"),
    exit_code: bool = typer.Option(False, "--exit-code", help="Exit 1 if any issue is found (for CI / hooks)"),
) -> None:
    """Lint the architecture docs: Mermaid syntax (no Node required) + invariant IDs cited in prose."""
    config = load_config(project.resolve())
    issues = lint_docs(config)
    if as_json:
        print(json.dumps({"issues": [
            {"doc": i.doc, "line": i.line, "code": i.code, "message": i.message} for i in issues
        ]}, indent=2))
        if exit_code and issues:
            raise typer.Exit(code=1)
        return

    if not issues:
        # Naming both checks: this command also validates invariant-ID citations, and a message that
        # mentions only Mermaid reads as "the ID check did not run".
        console.print("[green]No problems found — diagrams parse and every cited invariant ID exists.[/]")
        return
    console.print(f"[bold]Mermaid issues[/] ({len(issues)}) — malformed diagrams in the architecture docs\n")
    by_doc: dict[str, list] = {}
    for i in issues:
        by_doc.setdefault(i.doc, []).append(i)
    for doc, items in by_doc.items():
        console.print(f"[bold]{doc}[/]")
        for i in items:
            console.print(f"  [red]{i.line}[/]: [yellow]{i.code}[/] — {i.message}")
        console.print("")
    if exit_code:
        raise typer.Exit(code=1)


@app.command()
def graph(
    project: Path = typer.Option(Path("."), help="Target repo root"),
    write: bool = typer.Option(False, "--write", help="Splice the diagram into the artifact's README.md (between the archagent:graph markers)"),
) -> None:
    """Generate a Mermaid system map from the subsystems' Connects/Tier metadata."""
    config = load_config(project.resolve())
    subs = collect_subsystems(config)
    if not subs:
        console.print("[yellow]No subsystem docs found[/] — run /archagent-describe first.")
        raise typer.Exit(code=0)
    if write:
        action = write_to_index(config, graph_block(config))
        console.print(f"[green]{action}[/] the system map in "
                      f"{(config.architecture_dir / 'README.md').relative_to(config.project_root)} "
                      f"({len(subs)} subsystem(s)).")
        return
    print(graph_block(config))


@app.command()
def modules(project: Path = typer.Option(Path("."), help="Target repo root")) -> None:
    """Diagnostic: how each Python source file resolves to an import module (flags name collisions)."""
    config = load_config(project.resolve())
    mapping = module_map(config)
    if not mapping:
        console.print("[yellow]No Python modules resolved[/] — check `[python] source_paths` in archagent.toml.")
        return
    collisions = {m: files for m, files in mapping.items() if len(files) > 1}
    if collisions:
        console.print(f"[red]Module name collisions ({len(collisions)})[/] — these break import-linter scoping:\n")
        for m, files in sorted(collisions.items()):
            console.print(f"  [bold]{m}[/] ← {', '.join(files)}")
        console.print("")
    table = Table(title="archagent modules — file → import module")
    table.add_column("Module")
    table.add_column("File")
    for m, files in sorted(mapping.items()):
        for f in files:
            mark = " [red](collision)[/]" if len(files) > 1 else ""
            table.add_row(m + mark, f)
    console.print(table)
    console.print(f"\n[bold]{len(mapping)}[/] module(s) from {sum(len(f) for f in mapping.values())} file(s).")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

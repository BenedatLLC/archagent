"""Run the generated checkers and map their results back to invariant IDs.

The LLM proposes invariants; these deterministic tools are the trusted checkers.
A unified report is produced so a violation always points at a specific invariant.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .invariants import Invariant
from .rules import parse_property


@dataclass
class Finding:
    file: str
    line: int
    detail: str


@dataclass
class CheckResult:
    invariant_id: str
    checker: str
    passed: bool
    severity: str = "error"
    skipped_reason: str | None = None
    findings: list[Finding] = field(default_factory=list)


def run_checks(
    invariants: list[Invariant],
    config: Config,
    il_ids: list[str],
    dc_ids: list[str],
    sg_ids: list[str],
    pbt_ids: list[str],
) -> list[CheckResult]:
    by_id = {inv.id: inv for inv in invariants}
    results: list[CheckResult] = []
    if il_ids:
        results.extend(_run_import_linter(il_ids, config, by_id))
    if dc_ids:
        results.extend(_run_dependency_cruiser(dc_ids, config, by_id))
    if sg_ids:
        results.extend(_run_ast_grep(sg_ids, config, by_id))
    if pbt_ids:
        results.extend(_run_pbt(pbt_ids, config, by_id))
    return results


# --- import-linter -------------------------------------------------------

def _run_import_linter(ids, config, by_id) -> list[CheckResult]:
    il_config = config.generated_dir / ".importlinter"
    tool = _tool_path("lint-imports")
    env = dict(os.environ)
    src = os.pathsep.join(str((config.project_root / p).resolve()) for p in config.python.source_paths)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        [tool, "--config", str(il_config)],
        cwd=config.project_root, env=env, capture_output=True, text=True,
    )
    out = proc.stdout + "\n" + proc.stderr
    statuses = dict(re.findall(r"^(\S+)\s+(KEPT|BROKEN)\s*$", out, re.MULTILINE))
    if not statuses:  # import-linter errored before checking (e.g. an invalid contract)
        lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not set(ln.strip()) <= set("╔╗╚╝║═╠╣╩╦╬▶◀│└┐┘┌ ")]
        reason = (lines[-1] if lines else "import-linter produced no results")[:100]
        return [CheckResult(i, "import-linter", True, by_id[i].severity, skipped_reason=reason) for i in ids]
    details = _parse_broken_details(out)
    return [
        CheckResult(
            invariant_id=i, checker="import-linter",
            passed=statuses.get(i) == "KEPT", severity=by_id[i].severity,
            findings=details.get(i, []),
        )
        for i in ids
    ]


def _parse_broken_details(out: str) -> dict[str, list[Finding]]:
    details: dict[str, list[Finding]] = {}
    current: str | None = None
    in_broken = False
    for line in out.splitlines():
        if line.strip() == "Broken contracts":
            in_broken = True
            continue
        if not in_broken:
            continue
        stripped = line.strip()
        if re.fullmatch(r"\S+", stripped) and not stripped.startswith("-"):
            current = stripped
            details.setdefault(current, [])
        elif stripped.startswith("- ") and current:
            m = re.search(r"\(l\.(\d+)\)", stripped)
            details[current].append(Finding("", int(m.group(1)) if m else 0, stripped[2:]))
    return {k: v for k, v in details.items() if v}


# --- dependency-cruiser --------------------------------------------------

def _run_dependency_cruiser(ids, config, by_id) -> list[CheckResult]:
    cfg = config.generated_dir / ".dependency-cruiser.cjs"
    npx = _tool_path("npx", required=False)
    if not npx:
        return [CheckResult(i, "dependency-cruiser", True, by_id[i].severity,
                            skipped_reason="npx/node not found") for i in ids]
    cmd = [npx, "--yes", "--package=dependency-cruiser", "--package=typescript",
           "depcruise", "--config", str(cfg), "--output-type", "json", *config.ts.source_paths]
    proc = subprocess.run(cmd, cwd=config.project_root, capture_output=True, text=True, timeout=180)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        reason = (proc.stderr or proc.stdout or "depcruise produced no JSON").strip().splitlines()[-1:][0:1]
        return [CheckResult(i, "dependency-cruiser", True, by_id[i].severity,
                            skipped_reason=(reason[0] if reason else "depcruise error")[:80]) for i in ids]
    by: dict[str, list[Finding]] = {i: [] for i in ids}
    for v in data.get("summary", {}).get("violations", []):
        name = v.get("rule", {}).get("name")
        if name in by:
            by[name].append(Finding(v.get("from", ""), 0, f'{v.get("from")} -> {v.get("to")}'))
    return [CheckResult(i, "dependency-cruiser", not by[i], by_id[i].severity, findings=by[i]) for i in ids]


# --- ast-grep ------------------------------------------------------------

def _run_ast_grep(ids, config, by_id) -> list[CheckResult]:
    sgconfig = config.generated_dir / "sgconfig.yml"
    tool = _tool_path("ast-grep")
    paths = [p for p in config.all_source_paths() if (config.project_root / p).exists()]
    proc = subprocess.run(
        [tool, "scan", "-c", str(sgconfig), "--json", *paths],
        cwd=config.project_root, capture_output=True, text=True,
    )
    by: dict[str, list[Finding]] = {i: [] for i in ids}
    try:
        matches = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        matches = []
    for m in matches:
        rid = m.get("ruleId")
        if rid in by:
            start = m.get("range", {}).get("start", {})
            by[rid].append(Finding(
                _rel(m.get("file", ""), config.project_root),
                int(start.get("line", 0)) + 1,
                (m.get("text", "") or "").splitlines()[0][:80],
            ))
    return [CheckResult(i, "ast-grep", not by[i], by_id[i].severity, findings=by[i]) for i in ids]


# --- property-based tests (pbt) ------------------------------------------

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _run_pbt(ids, config, by_id) -> list[CheckResult]:
    # Behavioral properties execute the project's code, so they run in the TARGET's
    # environment (the language's test_command), not archagent's venv.
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)  # let the target's runner pick its own env
    results = []
    for i in ids:
        target = parse_property(by_id[i].rule).target
        rel = target.split("::", 1)[0]
        if rel.endswith(_JS_EXTS):
            results.append(_run_pbt_js(i, target, rel, config, by_id, env))
        else:
            results.append(_run_pbt_py(i, target, config, by_id, env))
    return results


def _run_pbt_py(i, target, config, by_id, env) -> CheckResult:
    test_cmd = shlex.split(config.python.test_command)  # e.g. "uv run pytest"
    try:
        proc = subprocess.run(
            [*test_cmd, target, "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=config.project_root, env=env, capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        return CheckResult(i, "pbt", True, by_id[i].severity, skipped_reason=f"test runner not found: {test_cmd[0]}")
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode == 0:
        return CheckResult(i, "pbt", True, by_id[i].severity)
    if proc.returncode == 5:  # pytest: no tests collected
        return CheckResult(i, "pbt", True, by_id[i].severity, skipped_reason=f"property not found: {target}")
    return CheckResult(i, "pbt", False, by_id[i].severity, findings=[Finding("", 0, _pbt_failure(out))])


def _run_pbt_js(i, target, rel, config, by_id, env) -> CheckResult:
    test_cmd = shlex.split(config.ts.test_command)  # e.g. "npx vitest run"
    name = target.split("::", 1)[1] if "::" in target else None
    cmd = [*test_cmd, rel, *(["-t", name] if name else [])]  # vitest & jest both accept -t <name>
    try:
        proc = subprocess.run(cmd, cwd=config.project_root, env=env, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        return CheckResult(i, "pbt", True, by_id[i].severity, skipped_reason=f"test runner not found: {test_cmd[0]}")
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode == 0:
        return CheckResult(i, "pbt", True, by_id[i].severity)
    return CheckResult(i, "pbt", False, by_id[i].severity, findings=[Finding("", 0, _pbt_failure(out))])


def _pbt_failure(out: str) -> str:
    for line in out.splitlines():
        if "Falsifying example" in line or "Counterexample" in line:  # Hypothesis / fast-check
            return line.strip()[:120]
    for line in reversed(out.splitlines()):
        s = line.strip()
        if s.startswith(("E ", "assert", "FAILED")) or "Error" in s or "Property failed" in s:
            return s[:120]
    return "property failed"


# --- helpers -------------------------------------------------------------

def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def _tool_path(name: str, required: bool = True) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(sys.executable).parent / name
    if candidate.exists():
        return str(candidate)
    if required:
        raise FileNotFoundError(f"Could not find '{name}' on PATH or next to the interpreter")
    return None

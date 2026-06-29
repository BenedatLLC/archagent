"""Generate checker configs from the invariant table (single source -> generate).

Capability matrix (v1):
  BOUNDARY + python   -> import-linter ``forbidden`` contract
  BOUNDARY + ts/js    -> dependency-cruiser ``forbidden`` rule
  STRUCTURAL (pattern)-> ast-grep rule (any language)

Each generated artifact carries the invariant ID so check results map back 1:1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .invariants import Invariant
from .rules import RuleError, parse_boundary, parse_pattern

_TS_TOKENS = ("ts", "tsx", "typescript", "js", "javascript")


@dataclass
class GenResult:
    written: list[Path] = field(default_factory=list)
    importlinter_ids: list[str] = field(default_factory=list)
    depcruiser_ids: list[str] = field(default_factory=list)
    astgrep_ids: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def generate(invariants: list[Invariant], config: Config) -> GenResult:
    result = GenResult()
    out = config.generated_dir
    out.mkdir(parents=True, exist_ok=True)

    il_contracts: list[str] = []
    dc_rules: list[str] = []
    active = [i for i in invariants if i.status != "deprecated"]

    for inv in active:
        try:
            if inv.type == "BOUNDARY" and inv.tier == "structural":
                if "python" in inv.applies_to:
                    il_contracts.append(_importlinter_contract(inv))
                    result.importlinter_ids.append(inv.id)
                elif any(tok in inv.applies_to for tok in _TS_TOKENS):
                    dc_rules.append(_depcruiser_rule(inv))
                    result.depcruiser_ids.append(inv.id)
                else:
                    result.skipped.append((inv.id, f"BOUNDARY: no generator for '{inv.applies_to}'"))
            elif inv.type == "STRUCTURAL" and inv.rule.startswith("forbid-pattern"):
                result.written.append(_write_astgrep_rule(inv, out / "sgrules"))
                result.astgrep_ids.append(inv.id)
            else:
                result.skipped.append((inv.id, f"no v1 generator for {inv.type}/{inv.tier}/{inv.applies_to}"))
        except RuleError as exc:
            result.skipped.append((inv.id, str(exc)))

    if il_contracts:
        if not config.python.root_package:
            raise ValueError("python.root_package must be set in archagent.toml for BOUNDARY/python invariants")
        path = out / ".importlinter"
        header = (
            "[importlinter]\n"
            f"root_package = {config.python.root_package}\n"
            "include_external_packages = True\n\n"  # required to forbid external deps (rich, chromadb, ...)
        )
        path.write_text(header + "\n".join(il_contracts) + "\n")
        result.written.append(path)

    if dc_rules:
        path = out / ".dependency-cruiser.cjs"
        path.write_text("module.exports = {\n  forbidden: [\n" + ",\n".join(f"    {r}" for r in dc_rules) + "\n  ],\n  options: { doNotFollow: { path: \"node_modules\" } }\n};\n")
        result.written.append(path)

    if result.astgrep_ids:
        path = out / "sgconfig.yml"
        path.write_text("ruleDirs:\n  - sgrules\n")
        result.written.append(path)

    return result


# --- import-linter -------------------------------------------------------

def _importlinter_contract(inv: Invariant) -> str:
    rule = parse_boundary(inv.rule)
    return "\n".join([
        f"[importlinter:contract:{inv.id.lower()}]",
        f"name = {inv.id}",
        "type = forbidden",
        # BOUNDARY means "must not import DIRECTLY"; transitive paths through a legitimate
        # mediating layer (e.g. domain -> ui-adapter -> rich) are how layering works.
        "allow_indirect_imports = True",
        "source_modules =",
        *(f"    {s}" for s in rule.sources),
        "forbidden_modules =",
        *(f"    {t}" for t in rule.targets),
        "",
    ])


# --- dependency-cruiser --------------------------------------------------

def _depcruiser_rule(inv: Invariant) -> str:
    rule = parse_boundary(inv.rule)
    severity = "error" if inv.severity == "error" else "warn"
    from_path = _path_regex_alt(rule.sources)
    to_path = _path_regex_alt(rule.targets)
    return (
        f'{{ name: "{inv.id}", severity: "{severity}", '
        f'from: {{ path: "{from_path}" }}, to: {{ path: "{to_path}" }} }}'
    )


def _path_regex_alt(operands: list[str]) -> str:
    parts = ["^" + re.escape(op) for op in operands]
    return "(" + "|".join(parts) + ")" if len(parts) > 1 else parts[0]


# --- ast-grep ------------------------------------------------------------

def _write_astgrep_rule(inv: Invariant, sgrules_dir: Path) -> Path:
    rule = parse_pattern(inv.rule)
    sgrules_dir.mkdir(parents=True, exist_ok=True)
    language = _astgrep_language(inv.applies_to)
    pattern = rule.pattern.replace("'", "''")  # YAML single-quote escaping
    content = (
        f"id: {inv.id}\n"
        f"language: {language}\n"
        f"severity: {'error' if inv.severity == 'error' else 'warning'}\n"
        f"message: '{inv.id}: forbidden pattern'\n"
        "rule:\n"
        f"  pattern: '{pattern}'\n"
    )
    path = sgrules_dir / f"{inv.id}.yml"
    path.write_text(content)
    return path


def _astgrep_language(applies_to: str) -> str:
    mapping = {
        "python": "python", "py": "python",
        "ts": "typescript", "typescript": "typescript", "tsx": "tsx",
        "js": "javascript", "javascript": "javascript",
    }
    for token in applies_to.replace(",", " ").split():
        if token in mapping:
            return mapping[token]
    return "python"

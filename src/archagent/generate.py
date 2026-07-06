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
from .rules import RuleError, parse_boundary, parse_pattern, parse_property

_TS_TOKENS = ("ts", "tsx", "typescript", "js", "javascript")


@dataclass
class GenResult:
    written: list[Path] = field(default_factory=list)
    importlinter_ids: list[str] = field(default_factory=list)
    depcruiser_ids: list[str] = field(default_factory=list)
    astgrep_ids: list[str] = field(default_factory=list)
    pbt_ids: list[str] = field(default_factory=list)
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
                result.written.append(_write_astgrep_rule(inv, out / "sgrules", config))
                result.astgrep_ids.append(inv.id)
            elif inv.rule.startswith("property"):
                scaffolded = _scaffold_property(inv, config)
                if scaffolded is not None:
                    result.written.append(scaffolded)
                result.pbt_ids.append(inv.id)
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

def _write_astgrep_rule(inv: Invariant, sgrules_dir: Path, config: Config) -> Path:
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
    if rule.scope_mode != "all" and rule.scope:
        # `in` -> only these files; `outside` -> all files except these.
        key = "files" if rule.scope_mode == "in" else "ignores"
        globs = _scope_to_globs(rule.scope, inv, config)
        content += f"{key}:\n" + "".join(f"  - '{g}'\n" for g in globs)
    path = sgrules_dir / f"{inv.id}.yml"
    path.write_text(content)
    return path


def _scope_to_globs(scope: str, inv: Invariant, config: Config) -> list[str]:
    """Turn an `in`/`outside` scope (path/glob or dotted module) into ast-grep globs."""
    if "/" in scope or "*" in scope or scope.endswith((".py", ".ts", ".tsx", ".js")):
        s = scope.rstrip("/")
        if "*" in s or s.endswith((".py", ".ts", ".tsx", ".js")):
            return [s]
        return [s, f"{s}/**"]  # a directory
    # dotted/bare module -> candidate paths under each source root for this language
    slug = scope.replace(".", "/")
    if "python" in inv.applies_to:
        exts, src_paths = [".py"], config.python.source_paths
    else:
        exts, src_paths = [".ts", ".tsx", ".js"], config.ts.source_paths
    globs: list[str] = []
    for sp in src_paths:
        base = f"{sp}/{slug}"
        globs += [f"{base}{ext}" for ext in exts]
        globs.append(f"{base}/**")
    return globs


# --- property-based tests (pbt) ----------------------------------------

_PBT_HEADER = (
    '"""archagent property tests (Hypothesis).\n\n'
    "Each stub is generated from a `property` invariant in architecture/invariants.md.\n"
    "Fill in the generator/rules and assertions, then run `archagent check`.\n"
    '"""\n\n'
    "from hypothesis import given, strategies as st\n"
    "from hypothesis.stateful import RuleBasedStateMachine, invariant, rule\n"
)


def _pbt_stub(inv: Invariant, func: str) -> str:
    why = inv.why or "see the linked ADR"
    return (
        f"\n\n@given(st.data())\n"
        f"def {func}(data):\n"
        f"    # archagent: property for {inv.id} -- {why}\n"
        f"    # TODO: generate inputs, drive the system, and assert invariant {inv.id}.\n"
        f'    raise NotImplementedError("archagent: implement property {inv.id}")\n'
    )


def _pbt_stateful_stub(inv: Invariant, name: str) -> str:
    core = name[4:] if name.startswith("Test") else name
    machine = core if core.endswith("Machine") else core + "Machine"
    why = inv.why or "see the linked ADR"
    return (
        f"\n\nclass {machine}(RuleBasedStateMachine):\n"
        f'    """archagent property for {inv.id} -- {why}\n\n'
        f"    Model the system's operations as @rule methods (Hypothesis composes them into\n"
        f"    random sequences) and assert what must always hold as @invariant methods.\n"
        f"    TODO: replace this scaffold.\n"
        f'    """\n\n'
        f"    def __init__(self):\n"
        f"        super().__init__()\n"
        f"        # TODO: construct the system under test (store / state machine / ...).\n\n"
        f"    @rule()\n"
        f"    def step(self):\n"
        f"        # TODO: drive one operation on the system.\n"
        f'        raise NotImplementedError("archagent: implement property {inv.id}")\n\n'
        f"    @invariant()\n"
        f"    def holds(self):\n"
        f"        # TODO: assert invariant {inv.id} holds after every step.\n"
        f"        pass\n\n\n"
        f"{name} = {machine}.TestCase\n"
    )


def _scaffold_property(inv: Invariant, config: Config) -> Path | None:
    """Ensure a Hypothesis stub exists for a `property [stateful] <path::name>` rule.

    Only scaffolds (the property logic needs system knowledge — the agent/human writes it).
    Plain rules get a `@given` stub (name should start with `test_`); `stateful` rules get a
    `RuleBasedStateMachine` + `<name> = <Machine>.TestCase`. Returns the file path if it
    created the file or appended a stub, else None.
    """
    rule = parse_property(inv.rule)
    rel, _, name = rule.target.partition("::")
    file_path = config.project_root / rel
    changed = False
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_PBT_HEADER)
        changed = True
    if name:
        text = file_path.read_text()
        present = (f"{name} = " in text) if rule.stateful else (f"def {name}(" in text)
        if not present:
            stub = _pbt_stateful_stub(inv, name) if rule.stateful else _pbt_stub(inv, name)
            file_path.write_text(text + stub)
            changed = True
    return file_path if changed else None


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

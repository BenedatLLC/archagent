"""Generate checker configs from the invariant table (single source -> generate).

Capability matrix (v1):
  BOUNDARY + python   -> import-linter ``forbidden`` contract
  BOUNDARY + ts/js    -> dependency-cruiser ``forbidden`` rule
  STRUCTURAL (pattern)-> ast-grep rule (any language)

Each generated artifact carries the invariant ID so check results map back 1:1.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

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
    # A row is enforced iff it has a real rule AND isn't marked non-enforceable. `Tier: prose` means
    # "recorded as documentation, not generated" — honour it uniformly for BOUNDARY and STRUCTURAL, so
    # the describe/invariant guidance ("mark Tier prose") actually holds (issue #2).
    active: list[Invariant] = []
    for i in invariants:
        if i.status == "deprecated":
            continue
        if i.tier == "prose":
            result.skipped.append((i.id, "tier 'prose': recorded as documentation, not enforced"))
            continue
        active.append(i)

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
                # A scoped rule whose globs match no file enforces nothing, and until #46 it reported a
                # PASS for doing so. That is the worst outcome this tool can produce — measured on dspy,
                # where a scope generated `./dspy/**`, ast-grep silently ignored it, the rule matched 0 of
                # 154 `print(` sites, and `check` said the invariant held (#44).
                #
                # Reported as skipped rather than failed: the rule is not violated, it is unenforceable,
                # and `check` already renders those differently. What must never happen is passing.
                empty = _empty_scope(inv, config)
                if empty:
                    result.skipped.append((inv.id, empty))
                else:
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


def _empty_scope(inv: Invariant, config: Config) -> str:
    """Why this rule's scope matches nothing, or "" when it matches something.

    The precondition for a scoped structural rule: the globs it compiles to must select at least one file.
    Checked here rather than after the run, because once ast-grep returns no violations there is nothing
    left to distinguish "no violations" from "nothing examined" — which is exactly how #44 reported a
    passing check over 154 unexamined call sites.
    """
    from .drift import _glob_files
    rule = parse_pattern(inv.rule)
    if getattr(rule, "scope_mode", "all") == "all" or not getattr(rule, "scope", ""):
        return ""
    globs = _scope_to_globs(rule.scope, inv, config)
    if any(_glob_files(config.project_root, g) for g in globs):
        return ""
    shown = ", ".join(f"`{g}`" for g in globs[:3])
    return (f"scope '{rule.scope}' matches no files (globs: {shown}) — the rule would enforce nothing, "
            f"so it is not generated rather than passing vacuously")


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
        # `posixpath.join`-free normalisation, because a source path of "." (a package at the repository
        # root: dspy/, requests/, flask/) would otherwise produce "./dspy/**" — and **ast-grep silently
        # ignores any glob with a `./` prefix**. The rule then matches nothing and `check` reports PASS.
        #
        # Measured on dspy at 4ed377ee9: `forbid-pattern print($$$) in dspy` generated `./dspy/**`,
        # matched 0 of 154 `print(` sites, and passed. A scoped structural rule that enforces nothing
        # while reporting a pass is the failure this tool exists to prevent, arriving through its own
        # code generator.
        prefix = sp.strip().removeprefix("./").strip("/")
        base = f"{prefix}/{slug}" if prefix and prefix != "." else slug
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
    """Ensure a property-test stub exists for a `property [stateful] <path::name>` rule.

    The target's file extension picks the framework: `.py` -> Hypothesis (`@given`, or a
    `RuleBasedStateMachine`); a JS/TS extension -> fast-check (`fc.property`, or `fc.commands`
    model-based testing). Only scaffolds — the property logic needs system knowledge. Returns
    the file path if it created the file or appended a stub, else None.
    """
    rule = parse_property(inv.rule)
    rel, _, name = rule.target.partition("::")
    file_path = config.project_root / rel
    is_js = rel.endswith(_JS_EXTS)
    changed = False
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_pbt_js_header(config) if is_js else _PBT_HEADER)
        changed = True
    if name:
        text = file_path.read_text()
        if is_js:
            present = f'"{name}"' in text or f"'{name}'" in text
            stub = _pbt_js_stateful_stub(inv, name) if rule.stateful else _pbt_js_stub(inv, name)
        else:
            present = (f"{name} = " in text) if rule.stateful else (f"def {name}(" in text)
            stub = _pbt_stateful_stub(inv, name) if rule.stateful else _pbt_stub(inv, name)
        if not present:
            file_path.write_text(text + stub)
            changed = True
    return file_path if changed else None


# --- fast-check (JS/TS) --------------------------------------------------

def _pbt_js_header(config: Config) -> str:
    return (
        "// archagent property tests (fast-check).\n"
        "// Generated from `property` invariants in architecture/invariants.md; fill in the property.\n\n"
        + _js_test_import(config)
        + 'import fc from "fast-check";\n'
    )


def _js_test_import(config: Config) -> str:
    """The `test` import line for the detected runner (jest exposes `test` as a global)."""
    pj = config.project_root / "package.json"
    deps = ""
    if pj.exists():
        try:
            data = json.loads(pj.read_text())
            deps = " ".join([*(data.get("devDependencies") or {}), *(data.get("dependencies") or {})])
        except (OSError, ValueError):
            deps = ""
    if "jest" in deps and "vitest" not in deps:
        return ""  # jest provides `test` globally
    return 'import { test } from "vitest";\n'


def _pbt_js_stub(inv: Invariant, name: str) -> str:
    why = inv.why or "see the linked ADR"
    return (
        f'\n\ntest("{name}", () => {{\n'
        f"  // archagent: property for {inv.id} -- {why}\n"
        f"  fc.assert(\n"
        f"    fc.property(fc.anything(), (input) => {{\n"
        f"      // TODO: drive the system and assert invariant {inv.id}.\n"
        f'      throw new Error("archagent: implement property {inv.id}");\n'
        f"    }}),\n"
        f"  );\n"
        f"}});\n"
    )


def _pbt_js_stateful_stub(inv: Invariant, name: str) -> str:
    why = inv.why or "see the linked ADR"
    return (
        f'\n\ntest("{name}", () => {{\n'
        f"  // archagent: stateful property for {inv.id} -- {why}\n"
        f"  // Model the system as fast-check Commands (model-based testing); assert invariants after each.\n"
        f"  const allCommands = [\n"
        f"    // TODO: e.g. fc.constant(new SomeCommand()),\n"
        f"  ];\n"
        f"  fc.assert(\n"
        f"    fc.property(fc.commands(allCommands), (cmds) => {{\n"
        f'      throw new Error("archagent: implement property {inv.id}");\n'
        f"      // fc.modelRun(() => ({{ model: {{}}, real: {{}} }}), cmds);\n"
        f"    }}),\n"
        f"  );\n"
        f"}});\n"
    )


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

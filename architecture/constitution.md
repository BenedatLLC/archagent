# Constitution

How this repository works, and the few rules that hold it together. Always loaded — kept terse on purpose.

## What archagent is

A tool that keeps a codebase adherent to a described architecture. The architecture is markdown in the
target repo; archagent compiles the checkable parts into configs for existing tools (import-linter,
dependency-cruiser, ast-grep), runs them, and reports adherence per invariant. **The checkers are
deterministic; a language model only ever proposes.**

## The rule that shapes the code

**Deterministic code gathers facts; a model judges them.** Every module here extracts something
verifiable — imports, commit counts, branch literals, env keys — and stops. Nothing in `src/` calls a
model. The judgement lives in the prompts under `templates/agent/phases/`, which ship as package data.

A consequence worth stating: when a scan cannot answer a question, it must say so rather than guess. The
failure mode this codebase has hit repeatedly is a check that returns *empty* when it meant *failed* —
a timed-out `git log` read as a repository with no commits. See ADR 0002.

## Layering

    cli  ->  evaluate / drift / check / init  ->  scanners  ->  config, mdutil

`cli.py` is the only module that prints. `config.py` and `mdutil.py` import nothing internal. Nothing
imports `cli` except the package entry point.

## Conventions

- **Design docs live in `docs/designs/`**, one per feature, with `status:` frontmatter. A design is
  written before the code and updated when the code teaches you something — several here carry
  corrections recorded in place rather than edited away.
- **`docs/ROADMAP.md`** is the checkable list; **`docs/ADL-SPEC.md`** specifies the artifact format this
  tool reads and writes.
- **Evaluation results live in `evaluations/`** and are permanent, including the runs that said nothing.
- Tests are pytest; `pytest -m corpus` runs the opt-in regression against real repositories.
- Thresholds carry a comment saying what evidence set them. An unexplained constant is a bug.

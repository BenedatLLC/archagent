# Deployment and configuration

**Services:** none. archagent is a single command-line program, installed once per machine
(`uv tool install archagent`) and run inside a target repository. There is no server, no database, and no
network access at runtime — every check reads the filesystem and `git`.

## Runtime dependencies

| Dependency | Used for | Where |
|---|---|---|
| `git` (executable) | history mining and staleness | `drift.py`, exclusively |
| `import-linter` | Python boundary invariants | invoked by `check.py` |
| `dependency-cruiser` | JS/TS boundary invariants | invoked by `check.py` |
| `ast-grep` | structural invariants, any language | invoked by `check.py` |

The external checkers are the point rather than an implementation detail: archagent compiles an invariant
table into their configs instead of reimplementing boundary analysis.

**Config:** none required. Behaviour comes from `archagent.toml` in the target repo (see
`subsystems/config.md`); the tool itself reads no environment variables.

It does *set* two for the checkers it launches: `NO_COLOR=1` on, `FORCE_COLOR` and `CLICOLOR_FORCE` off.
That is not configuration but a correctness measure. `FORCE_COLOR` is set in plenty of developer shells
and CI images, several of these tools honour it, and `check` parses their output — so an inherited
environment variable made a pattern stop matching, and a pattern that matches nothing reports no
violations, which is indistinguishable from a passing run.

## What it writes into a target repository

- `<arch-dir>/` — the artifact, authored by a person or an agent, committed.
- `<arch-dir>/investigations/` — recorded analyses of findings, committed.
- `.archagent/generated/` — checker configs, derived and regenerated on every `check`; gitignored.
- `.archagent/history-profile.json` — the learned bug-fix commit wording; small, and worth committing so
  history-based results reproduce on another machine.

# `archagent.toml`

One file at the repository root tells archagent where your code is. `archagent init` writes it and prints
every value it chose, marking each **detected**, **guessed** or **defaulted**, and flagging any that look
wrong. Read that output — it is faster than reading this page, and it is specific to your repo.

This is the reference for when you need to change something.

## The whole file

```toml
[project]
languages = ["python", "ts"]        # which analysers run
architecture_dir = "architecture"   # where the artifact lives

[python]
root_package = "app"                # the importable top-level package
source_paths = ["src"]              # directories that are ON the import path
test_command = "pytest"             # how to run property-based tests

[ts]
source_paths = ["src"]
test_command = "npx vitest run"
```

Everything has a default except `python.root_package`, which cannot be guessed reliably and has no
sensible fallback.

## `[project]`

### `languages`

Default `["python"]`. Which analysers run. `"python"` enables import-linter and the `ast` import graph;
any of `"ts"`, `"typescript"`, `"js"` enables dependency-cruiser and the JS/TS regex scan.

A language not listed here is invisible to the structural checks. That is not silent: `evaluate` reports
a coverage entry when the dependency graph is empty, and `check` reports an invariant it could not compile
as *skipped* rather than passing.

### `architecture_dir`

Default `"architecture"`. Where the artifact lives, relative to the repository root. Set at `init` time —
`--arch-dir docs/architecture` — and read by every command, so the artifact moves as a unit.

## `[python]`

### `root_package` — the one to get right

The importable top-level package name: `app`, `archagent`, `dspy`. It is what import-linter scopes its
contracts to.

**If this is wrong, every BOUNDARY invariant passes vacuously.** A contract scoped to a module set that
does not exist finds no violations, and `check` reports that all invariants hold having examined nothing.
`archagent modules` is the one-command diagnostic: it shows how each source file resolves to a module and
flags top-level name collisions.

`init` guesses it from the package layout and says so when it cannot.

### `source_paths`

Default `["src"]`. The directories that are **on the import path** — not the directories your code is in.

The distinction is the thing people get wrong, and it decides how module names are derived:

| Layout | `source_paths` | `src/app/api/deps.py` resolves as |
|---|---|---|
| package under `src/` | `["src"]` | `app.api.deps` ✓ |
| package under `src/` | `["src/app"]` | `api.deps` ✗ — the code imports `app.api.deps` |
| package at the repo root | `["."]` | `app.api.deps` ✓ |

So the rule is: **name the directory that *contains* your package**, not the package itself. `"."` and
`"./src"` and `"src/"` all work and mean what they look like.

This is not inferred — it defaults to `src` regardless of your layout — so `init` verifies it instead, by
counting matching files under the path and naming a likelier directory when it finds none.

### `test_command`

Default `"pytest"`. How to run the property-based tests that back `property` invariants. `check` runs it
in **your project's** environment, not archagent's, and reports the counterexample the framework found.
Only relevant if you have `property` rules; `--skip-pbt` skips them.

## `[ts]`

Also accepted as `[typescript]` or `[js]` — the loader takes whichever it finds first.

`source_paths` defaults to `["src"]` and means the same thing as above. `test_command` defaults to
`"npx vitest run"`.

There is no `root_package` for TS: dependency-cruiser rules name paths (`src/domain`) rather than dotted
modules, so there is nothing to scope.

## Worked examples

**A Python package under `src/`** — archagent's own layout:

```toml
[project]
languages = ["python"]
architecture_dir = "docs/architecture"

[python]
root_package = "archagent"
source_paths = ["src"]
```

**A Python package at the repository root** — dspy, requests, flask:

```toml
[project]
languages = ["python"]

[python]
root_package = "dspy"
source_paths = ["."]        # the root contains dspy/
```

Note that `["."]` puts `tests/`, `docs/` and anything else with source files in scope. That is usually
what you want — `drift` then tells you about undocumented test code, and a test subsystem takes
`**Tier:** test` so it stays off the layer ladder — but it is worth knowing before the first `status` run
surprises you.

**A backend and a frontend in one repository** — fastapi-template:

```toml
[project]
languages = ["python", "ts"]

[python]
root_package = "app"
source_paths = ["backend"]      # backend/, not backend/app — see the table above

[ts]
source_paths = ["frontend/src"]
```

## Checking it

```bash
archagent modules     # how each Python file resolves to a module; flags name collisions
archagent status      # how much of the code the artifact covers — 0% usually means a wrong source path
archagent gen         # what your invariants compile to, and what was skipped and why
```

If `status` reports far fewer files than your repository has, or `modules` reports none, the source path
is wrong. That is the failure worth ruling out first, because everything downstream of it reports a clean
result.

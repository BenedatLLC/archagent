# extraction — the static scanners

**Covers:** `src/archagent/configscan.py`, `src/archagent/deployscan.py`, `src/archagent/webapi.py`, `src/archagent/datamap.py`, `src/archagent/connscan.py`, `src/archagent/obsscan.py`, `src/archagent/invscan.py`, `src/archagent/mdutil.py`
**Tier:** infra
**Connects:** config via import, drift via import

## Purpose

Pull verifiable facts out of a codebase without running it. Each scanner answers one narrow question and
returns data; none of them judges.

| Module | Fact extracted |
|---|---|
| `configscan.py` | environment keys the code reads (`os.getenv`, `process.env`) |
| `deployscan.py` | services declared in docker-compose / k8s / Procfile |
| `webapi.py` | HTTP routes, from the code or an OpenAPI spec |
| `datamap.py` | table definitions and datastore touch points |
| `connscan.py` | outbound calls whose target resolves to a known service |
| `obsscan.py` | tracing / correlation-id instrumentation |
| `invscan.py` | invariants already *stated* in prose or asserts, as candidates |
| `mdutil.py` | markdown helpers (fence stripping, empty-value detection) |

## What a scanner actually returns

"Extracts environment keys" describes a shape, not a result. Three scanners, each shown as the code it
reads and the fact it hands back:

**`configscan`** — given `os.getenv("DATABASE_URL", "sqlite://")` anywhere in the source set,
`read_config_keys` returns the bare set `{"DATABASE_URL", ...}`. Deliberately a set of names and not a
map to locations: its only consumer compares it against `declared_config_keys`, the keys named under
`**Config:**` in `deployment.md`. A key read but never declared is drift; a key declared but never read is
dead configuration.

**`webapi`** — given `@app.get("/orders/{order_id}")`, `extract_routes` returns
`Route(method="GET", path="orders/{}")`, keeping the original string in `raw` and the file in `source`.
The normalisation is the interesting part: parameter names are erased and surrounding slashes stripped
*because* the comparison is against an OpenAPI spec or another framework's spelling of the same route,
and `/orders/{id}` and `/orders/{order_id}` are the same endpoint. Only `method` and `path` take part in
equality (`webapi.py:38-44`).

**`invscan`** — given `assert user.is_authenticated, "only signed-in users may post"`, it returns a
`Candidate` carrying that message, `path:line`, `kind="marker"`, `confidence="high"`, and a coarse guess
at which DSL tier it belongs in. In code it matches only explicit `INVARIANT`/`@invariant` markers and
assertion messages; the noisier `kind="modal"` pass — "must never", "only X may" — runs over documents
only, because modal words in code are too common to be worth surfacing. Even so these are *candidates* a
person classifies and verifies, never facts.

The pattern holds for all eight: a file set in, typed facts out, and the value is in what the fact can be
compared against rather than in the fact itself.

## Key abstractions

**Regex and AST, never execution.** "Static" here means no import of the target code, so scanning a
repository can never run it.

**Conservative by design.** `connscan` drops a call whose target it cannot resolve rather than guessing;
`datamap` requires a real table definition. A scanner that guesses produces findings nobody can act on.

**`invscan` is the odd one out.** It extracts *candidates* for the invariants table rather than facts —
`INVARIANT:` markers, asserts, and modal prose ("must never", "only X may") — which a person then
classifies and verifies before promoting.

## State and tiering

Read-only over the working tree. Most of these are leaves; `invscan.py:24` imports `_source_files` from
`drift`, and that single edge is what closes the `drift ↔ extraction` cycle recorded in ADR 0003.
`connscan` imports `configscan` alone and is not part of it.

## Lifecycles / key flows

None. Each scanner is a pure function from a file set to facts.

## Invariants

None specific. These modules are depended on, so their signatures are the contract.

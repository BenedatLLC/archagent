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

## Key abstractions

**Regex and AST, never execution.** "Static" here means no import of the target code, so scanning a
repository can never run it.

**Conservative by design.** `connscan` drops a call whose target it cannot resolve rather than guessing;
`datamap` requires a real table definition. A scanner that guesses produces findings nobody can act on.

**`invscan` is the odd one out.** It extracts *candidates* for the invariants table rather than facts —
`INVARIANT:` markers, asserts, and modal prose ("must never", "only X may") — which a person then
classifies and verifies before promoting.

## State and tiering

Read-only over the working tree. `mdutil` and `configscan` are leaves; `invscan` and `connscan` import
`drift` for its file-globbing plumbing.

## Lifecycles / key flows

None. Each scanner is a pure function from a file set to facts.

## Invariants

None specific. These modules are depended on, so their signatures are the contract.

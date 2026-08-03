# Constitution — how Observability Studio is put together

Observability Studio is a **local** OpenTelemetry workspace. A developer instruments a service, points its
OTLP exporter at a locally running Observer process, and sees the telemetry — with conformance assessment
attached — in a UI inside their editor. Nothing leaves the machine unless Splunk export is explicitly
configured.

## The four things that ship

| Component | Language | What it is |
|---|---|---|
| `observer/` | Go | one binary: OTLP receiver, in-memory store, validator, REST API, MCP server, web server |
| `observer/client/` | TypeScript / React | the UI, served by the Observer as static files |
| `extension/` | TypeScript | a VS Code-compatible extension that starts the Observer and hosts the UI in a webview |
| `skills/` | Markdown + Python | agent skills (`$otel-audit`, `$otel-instrument`, …) shipped to Codex, Claude Code, Cursor, Kiro |

## Layering, and the one rule that holds it up

The Go service is strictly layered, and the layering is real rather than aspirational — it was read off
the imports, not off a diagram:

```
cmd/obstudio          composition root; the only place that wires anything to anything
   ├── api, mcp, web   edge — speak HTTP, WebSocket, MCP to the outside
   ├── validator       assessment over stored telemetry
   ├── otlp            ingest, and optional forwarding to Splunk
   ├── dashboards      SignalFlow / Terraform generation
   └── store           the leaf — in-memory telemetry, imports no internal package
```

**`store` imports nothing internal, and everything eventually imports `store`.** That is what makes the
graph acyclic. `validator`, `otlp` and `dashboards` each depend only on `store`; `api`, `mcp` and `web`
depend on `store` and `validator`; `cmd` depends on all of them and is depended on by none. There is no
cycle anywhere in `observer/internal/` — verified by reading every `internal/` import at `88aebe8`.

## Telemetry is in memory and is expected to be lost

There is no database. `store` holds spans, metrics and logs in bounded in-memory buffers, and a restart
discards everything. This is deliberate — the tool exists for the minutes during which a developer is
iterating on instrumentation — and it is why the UI has a "clear" action and why the validator has an
invalidation callback rather than a cache-invalidation protocol.

## Configuration is environment variables, read at startup — mostly in one place

`cmd/obstudio` reads `OBSTUDIO_*` variables (and an optional `~/.obstudio/env` file, `main.go:225`) once
in `run()` and passes the values down as parameters. That is what lets the extension embed the Observer on
different ports without any inner package knowing it is embedded.

**Three packages break the pattern and read the environment directly.** This was checked rather than
assumed, and the assumption was wrong:

| Site | Variable |
|---|---|
| `internal/validator/manager.go:509` | `WEAVER_PATH` |
| `internal/validator/manager.go:553` | `OBSTUDIO_VALIDATOR_HEALTH_TIMEOUT` |
| `internal/store/genai.go:1338` | `MAX_FLOW_NODE_SPAN_LIST_SIZE` |

Two of the three are not even named `OBSTUDIO_*`, so they are invisible to anyone grepping for the
project's own prefix, and none of them appear in the startup banner or the `install` flow. This is
recorded as drift between the pattern and the code rather than written up as if the pattern held — see
`invariants.md`, where it is a `proposed` prose row, not an enforced rule.

## What this artifact can and cannot check

**archagent does not analyse Go**, and Go is where the core of this system lives. `archagent.toml`
declares `python` and `typescript`, so 84 of the ~148 product source files are visible to the tooling and
the 64 Go files are not. Concretely:

- `archagent drift` compares `**Covers:**` globs against Python and TypeScript files only. Go globs are
  declared in the subsystem documents and are *not* counted as coverage, so a Go file added tomorrow will
  not be reported as undocumented.
- **Two whole classes of drift finding are false here, and both are confident.** Every `**Connects:**`
  edge between Go subsystems is reported as a *stale declared dependency* — 15 of them at `88aebe8` —
  because the import graph is empty for Go, so no declared edge can be confirmed. And every configuration
  key read only in Go (`OBSTUDIO_OWNER`, `OBSTUDIO_MODE`, `OBSTUDIO_WORKSPACE_ROOT`,
  `OBSTUDIO_DASHBOARDS_PREVIEW`) is reported as *declared but not read in code*. Both read as defects in
  this artifact and are properties of the tool. Do not "fix" them by deleting accurate declarations.
- `archagent check` can enforce boundary invariants for TypeScript (dependency-cruiser) and Python
  (import-linter). **The Go layering described above — the most load-carrying rule in the system — is not
  mechanically enforced by anything in this repo.** `go vet` and the compiler catch cycles within a
  package's imports, but nothing forbids `store` importing `validator` tomorrow.
- `archagent evaluate`'s structural families see the TypeScript and Python graphs only.

This is stated here rather than left for a reader to discover, because an artifact that silently omits its
own blind spot is worse than one with no checks at all.

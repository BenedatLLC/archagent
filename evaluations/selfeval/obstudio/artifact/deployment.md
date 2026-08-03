# Deployment — how Observability Studio runs

## Runtime shape

**One process, on a developer's laptop.** There is no server, no cluster and no database. `obstudio` is a
single Go binary with the React UI embedded in it (`observer/cmd/obstudio/embed.go`); the editor extension
starts that binary as a child process and displays its UI in a webview.

There is deliberately no `**Services:**` declaration below: the system is not a set of deployed services,
and declaring some would be false. The `docker-compose.yml` files in the repository all live under
`evals/*/eval/runtime/` and belong to test fixtures, not to this product.

## Ports

Three, all bound to one host, resolved by `resolveRunConfig` (`main.go:321-328`):

| Port | Serves | Set by | Default |
|---|---|---|---|
| observer HTTP | REST API, WebSocket, the UI, and MCP over HTTP | `--observer-http-port` or `PORT` | 3000 |
| OTLP/HTTP | OTLP/HTTP ingest | `OTLP_HTTP_PORT`, else `OTLP_PORT` | 4318 |
| OTLP/gRPC | OTLP/gRPC ingest | `OTLP_GRPC_PORT` | 4317 |

Host comes from `--host` or `HOST`, defaulting to `127.0.0.1` — local by default, which is the product.

**Only the first of the three has a command-line flag.** `newRootCmd` (`main.go:65-67`) registers exactly
`--host`, `--observer-http-port` and `--env-file`. The OTLP ports are environment-only.

**And the validation error names flags that do not exist.** `validateRunConfig` (`main.go:407-425`) builds
its message from a `flagName` field carrying `--otlp-http-port` and `--otlp-grpc-port`, so a bad value
produces `--otlp-grpc-port must be a valid TCP port between 1 and 65535, got "x"` — naming an option the
binary rejects. The only way to set it is `OTLP_GRPC_PORT`. Small, concrete, and user-visible: the error
tells you to do something impossible.

MCP is also served over stdio on the same process (`main.go:191`), for agents that spawn a subprocess
rather than connect to a URL.

## Configuration

Environment variables, read at startup, optionally from `~/.obstudio/env` (`main.go:225`) or a path given
by `--env-file`.

**Config:** `OBSTUDIO_OWNER`, `OBSTUDIO_MODE`, `OBSTUDIO_WORKSPACE_ROOT`, `OBSTUDIO_DASHBOARDS_PREVIEW`,
`OBSTUDIO_VALIDATOR_HEALTH_TIMEOUT`, `OBSTUDIO_SHARED_OBSERVER_STATE_PATH`, `WEAVER_PATH`,
`MAX_FLOW_NODE_SPAN_LIST_SIZE`, `HOME`, `USERPROFILE`

Plus the unprefixed runtime keys `HOST`, `PORT`, `OTLP_HTTP_PORT`, `OTLP_PORT`, `OTLP_GRPC_PORT`, and
the Splunk keys `OBSTUDIO_SPLUNK_*` / `SPLUNK_REALM` / `SPLUNK_ACCESS_TOKEN` / `SPLUNK_METRICS_EXPORT`.

**The naming is inconsistent in two directions at once.** Several keys carry no `OBSTUDIO_` prefix at all
(`HOST`, `PORT`, `WEAVER_PATH`, `MAX_FLOW_NODE_SPAN_LIST_SIZE`), and several accept *either* the prefixed
or the unprefixed spelling (`OBSTUDIO_SPLUNK_METRICS_EXPORT` or `SPLUNK_METRICS_EXPORT`,
`main.go:336-337`). A developer cannot tell from a variable's name whether it belongs to this tool, and
`grep OBSTUDIO_` does not find its whole configuration surface. `WEAVER_PATH`,
`OBSTUDIO_VALIDATOR_HEALTH_TIMEOUT` and `MAX_FLOW_NODE_SPAN_LIST_SIZE` are additionally read deep inside
packages rather than in `cmd` — see `constitution.md`.

`OBSTUDIO_SHARED_OBSERVER_STATE_PATH` (`extension/src/extension.ts:489`) and the
`HOME`/`USERPROFILE` pair are read by the **extension**, not the Observer — they locate the shared
state file. They were missing from this list until `archagent drift` reported them, which is the
check earning its place.

Splunk export is configured through the exporter's own environment (`splunkMetricsExporterConfigFromEnv`,
`main.go:103`) and is off unless configured.

## External dependencies

| Dependency | Needed for | If absent |
|---|---|---|
| `weaver` | semantic-convention validation | validation reports a failure kind; telemetry capture is unaffected (`main.go:99-101`) |
| Splunk O11y endpoint + token | forwarding metrics and traces | forwarding is off; local workspace unaffected |

Both are optional by design. The product is the local workspace; everything else degrades around it.

## Install

`obstudio install --target=codex,claude-code,cursor,kiro` writes the skill bundle and MCP configuration
into each agent's own location — see the target table in `subsystems/observer-cli.md`. A running Observer
also advertises itself in a shared state file so a second one does not fight for the port.

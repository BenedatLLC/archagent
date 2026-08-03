# Invariants

Rules for Observability Studio. **Almost every row here is `prose` tier, and that is a finding rather than
a style choice.**

The rules worth enforcing in this system are about the Go service — `store` must import nothing internal,
`cmd` must be the only composition point, a failed validation must not render as a clean one. archagent
generates checker configs for Python (import-linter) and TypeScript (dependency-cruiser) and **has no Go
back end at all**, so none of them can be mechanically enforced here. A `prose` row keeps the rule
documented, greppable and in one place; it does not check anything. `constitution.md` states the blind
spot in full.

Each row was verified by reading the code at `88aebe8`. A rule the code does not currently satisfy is
marked `proposed` and called out as drift, not written as if it held.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| GO-001 | BOUNDARY | prose | go | `forbid observer.internal.store -> observer.internal.*` | error | `store` is the leaf every package depends on; an import out of it creates a cycle immediately | active |
| GO-002 | BOUNDARY | prose | go | `forbid observer.internal.* -> observer.cmd` | error | `cmd` is the composition root; nothing below may reach back into it | active |
| GO-003 | BOUNDARY | prose | go | `forbid observer.internal.otlp, observer.internal.dashboards -> observer.internal.validator` | error | ingest and preview must not depend on assessment; keeps the graph acyclic | active |
| GO-004 | STRUCTURAL | prose | go | `forbid-pattern os.Getenv($$$) outside observer/cmd` | error | configuration is resolved once in `cmd` and passed down — **currently violated in 3 places** | proposed |
| VAL-001 | STRUCTURAL | prose | go | a validation run that could not execute must report a failure kind, never an empty result | error | `ServiceErrorKind` (`observer/internal/validator/service.go:22`); "weaver missing" must not render as "instrumentation is clean" | active |
| HTTP-002 | STRUCTURAL | prose | go | the WebSocket and REST read paths must select records the same way | warn | **currently violated**: `web/websocket.go:204-218` hardcodes 100 and no filters; `api/handler.go:76-84` takes both | proposed |
| WEB-002 | STRUCTURAL | prose | typescript | `observer/client/src/api/types.ts` must match the JSON tags in `observer/internal/store/store.go` | error | hand-maintained across a language boundary with nothing checking it | active |
| SKILL-002 | STRUCTURAL | prose | python | a per-skill script under `scripts/` must contain no logic; the implementation lives in `skills/references/scripts/` | warn | keeps eight skill copies from diverging | active |

## Rules deliberately not written as invariants

**"The extension must not grow."** `extension/src/extension.ts` is 1506 lines against 129–252 for its
siblings. Size is a signal, not a rule, and a line-count threshold would be gamed by splitting a file
without splitting the responsibility. Recorded in `subsystems/studio-extension.md` instead.

## What would make these enforceable

A Go back end for archagent's BOUNDARY type — emitting `go-arch-lint` or `depguard` configuration the way
it emits import-linter contracts today — would move GO-001 through GO-004 from `prose` to `structural`
without changing a word of the rules. That is the single highest-value change for this repository, and
GO-004 would fail on the first run, which is the point.

# <Subsystem name>

**Covers:** `src/<area>/**`
<!-- Glob(s) of the SOURCE CODE this subsystem owns (`.py`, `.ts`, …). `archagent drift` uses this to flag
     when the code changed but this doc didn't. Matches code files only — data files (prompt `.md`, fixtures,
     SQL, config) can't be Covered; describe those in prose. Optional — if omitted, drift falls back to the
     file refs below. -->


**Connects:** other-subsystem via sync-call, another-subsystem via async-event, a-third
<!-- Other subsystems (by doc name) this one connects to, each optionally typed by connector kind:
     `import` (in-process code dependency — the default if `via <kind>` is omitted), `sync-call` (blocking
     request/response — HTTP/gRPC/RPC), `async-event` (pub/sub, message queue), `shared-data` (both read/
     write a shared store), `pipe` (one-way stream). `archagent drift` checks `import` edges against the
     actual import graph; `archagent evaluate` uses the kinds to tell tight coupling (a synchronous service
     cycle = distributed monolith) from loose (an event-coupled cycle is usually fine). Optional —
     OMIT this whole line if the subsystem has no outgoing edges (a leaf/base). Never write a value like
     "none" or a sentence; it gets tokenised into fake edges.
     DIRECTION self-check: `Connects` is OUTGOING. It must read as an active sentence — "THIS subsystem
     imports/calls X" — never "X imports this". If you'd say "X depends on me", that edge belongs on X's doc,
     not here.
     Legacy alias: `**Depends-on:** a, b` == `**Connects:** a via import, b via import`. -->

**Service:** <deployment-service-name>
<!-- The deployment service this subsystem runs as (a name from deployment.md's **Services:**). When set,
     `archagent drift` checks the code's cross-service dependencies against docker-compose depends_on.
     Optional — OMIT for a single-process app (no distinct services). Don't write a placeholder value. -->

**Tier:** <ui | domain | infra>
<!-- The architectural layer this subsystem lives in (e.g. ui / app / domain / infra / data). When set on
     related subsystems, `archagent evaluate` flags leaky abstractions: a lower tier depending up on a
     higher one, or a tier reaching past its neighbor to a distant one. Optional. -->


> **Purpose.** One short paragraph: what this subsystem is for and why it exists.
> A new engineer should understand it here without opening other files.

## Topology & components
What the pieces are and how they connect. Reference real files (`path/to/file.py`).

## Key abstractions & patterns
The few abstractions/patterns this subsystem relies on, each with one concrete example.

## State & tiering
What state lives here, where (in-memory / durable / cache), and how it's scoped.

## Lifecycles
```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Active
    Active --> [*]
```
_Caption: one plain-language sentence on what this lifecycle shows and the key takeaway._
<!-- Mermaid gotcha: in a `stateDiagram-v2` transition label (`A --> B : text`), everything after the FIRST
     colon is the label, and a SECOND colon breaks the parser — write "port 5300", not "on :5300". Run
     `archagent lint-docs` to catch this and other Mermaid syntax errors before committing. -->

## Key flows
```mermaid
sequenceDiagram
    Caller->>Subsystem: request
    Subsystem-->>Caller: response
```
_Caption: one plain-language sentence on what this flow shows._

## Invariants
Which rows in [`../invariants.md`](../invariants.md) apply here, and why they matter.

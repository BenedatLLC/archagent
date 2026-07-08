# <Subsystem name>

**Covers:** `src/<area>/**`
<!-- Glob(s) of the code this subsystem owns. `archagent drift` uses this to flag when the code
     changed but this doc didn't. Optional — if omitted, drift falls back to the file refs below. -->

**Depends-on:** other-subsystem, another-subsystem
<!-- Other subsystems (by doc name) this one is allowed to import. `archagent drift` compares this to
     the actual import graph and flags undeclared couplings + stale declarations. Optional. -->

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

## Key flows
```mermaid
sequenceDiagram
    Caller->>Subsystem: request
    Subsystem-->>Caller: response
```
_Caption: one plain-language sentence on what this flow shows._

## Invariants
Which rows in [`../invariants.md`](../invariants.md) apply here, and why they matter.

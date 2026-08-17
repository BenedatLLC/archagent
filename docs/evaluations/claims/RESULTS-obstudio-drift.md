# obstudio drift test — results (2026-08-16)

Pre-registered in `PREREGISTRATION-obstudio-drift.md`. Real history: `88aebe8` → `17797b9`, two commits,
three files, 32 insertions — *"feat: add Windsurf install target"*.

**All four predictions confirmed. On a repository archagent cannot analyse statically, the claims file
caught a real documentation staleness that `drift` structurally cannot reach.**

## The result

| | before `17797b9` | after |
|---|---|---|
| `drift` output | 22 findings | **byte-identical** |
| claims diverging | 6 of 16 | **7 of 16** |

The one new divergence:

```
C-016  [set]  the agents `obstudio install` can target
      not in the artifact: windsurf
      asserted in:   observer-cli.md:36-39, deployment.md:76, constitution.md:15
```

The artifact is stale in **three places** — a table of install targets, a command line
(`obstudio install --target=codex,claude-code,cursor,kiro`), and a sentence in the constitution. The claim
names the missing member and the three documents to revise.

`drift`'s output did not change by a single byte, because the modified file is Go and `archagent.toml`
declares `python` and `typescript`.

## The coverage number, which does not depend on the change

**`drift` can check 0 of the 16 Go closed collections the artifact asserts.** Not few — none. The install
targets, the MCP tool surface, the state-changing routes, the `Store` locks, the environment reads outside
`cmd`, the `go:embed` directives, the CLI flags, the default ports: all in Go, all invisible.

Worse than absent, its 22 findings are **all false positives, and the artifact says so itself**. The 15
"stale declared dependencies" are every declared Go subsystem edge — the artifact's constitution predicts
exactly this, *"15 of them at `88aebe8`"*, because the Go import graph is empty so no declared edge can be
confirmed. The 7 "dangling config" findings are Go-only environment keys.

So on this target `drift` currently produces 22 findings that a reader must learn to ignore and 0 that
matter. **A claims file is not an improvement on `drift` here; it is the only mechanical check that
functions at all.**

## Against the predictions

| prediction | outcome |
|---|---|
| `drift` reports no change | **confirmed** — byte-identical output |
| the install-target claim fires, naming `windsurf` | **confirmed**, with the three stale locations |
| the other 15 claims are unchanged | **confirmed** — 6 divergences before and after, all pre-existing |
| `drift` can check 0 of the Go closed collections | **confirmed** — 0 of 16 |

## Disclosure, restated

The fifteen pre-existing claims were written days earlier for step 1 and predate this diff. **C-016 was
written after the diff was sized**, and is the claim that fired. That is disclosed rather than buried, and
it means this run demonstrates the *mechanism* on the class rather than estimating a hit rate.

The mitigation is that the coverage result above — 0 of 16 — is independent of the change entirely, and it
is the stronger of the two findings.

## What this establishes, and what it does not

**Establishes**: on a repository outside archagent's static analysis, `set` claims over closed collections
catch documentation staleness that no existing check can, and the existing check contributes only noise.
This is the narrowed justification from the wardrowbe experiment, tested where it should bite, and it
holds.

**Does not establish**: any rate. One change, one collection, 32 insertions. A larger sample would say how
often a release touches a covered collection; this says only that when it does, the mechanism works and
the alternative does not.

**Does not rescue the broad claim.** The wardrowbe result stands: *"makes much of the drift computation
mechanical"* is not supported for a repository the tool can analyse, where `drift` already catches the
structural changes and the value drift claims would add is mostly trivia. The case for computed claims is
now specifically **the blind-spot case**, and it should be written that way in the design.

## The recommendation this leads to

Scope the feature to what the evidence supports:

1. **`set` claims over closed collections are the load-bearing kind.** They fired in step 1, they caught
   this, and they are the only kind that has ever caught anything neither a reader nor another instrument
   found first.
2. **The value proposition is coverage of blind spots, not drift in general.** For a repository archagent
   parses, `drift` already does the structural work. For one it does not — a Go service, a Rust binary,
   anything outside the configured languages — a claims file is the only mechanical check available.
3. **That suggests a cheaper shape than the full design**: rather than claims for everything, a claims
   file whose scope is *the part of the system archagent cannot see*, which `describe` already has to
   identify and which obstudio's artifact already documents in a dedicated section.

# Defects the round-2 review found in the obstudio artifact

Found by an independent reviewer on 2026-08-11 (`review-brief-2026-08-02.md` in the data repo), verified
against the pinned checkout at `88aebe8`. **Not yet fixed**, deliberately: a blind model judge is scoring
the same artifact, and an agreement rate is meaningless if the two reviewers saw different documents.
Fixes land after the judge's scores are in.

## 1. `deployment.md:6` — wrong file cited for the UI embed

Claims the React UI is embedded by `observer/cmd/obstudio/embed.go`. That file embeds the *skills*:

```
observer/cmd/obstudio/embed.go:5      //go:embed all:_skills
observer/internal/web/static_embed.go:10   //go:embed all:static      <- the UI
```

The prose around it is right — the UI *is* embedded in the binary — but the citation sends a reader to
the wrong file. Confirmed exactly as reported.

## 2. `mcp-server.md` — a true sentence carrying a false claim

> **This is the only outward interface that can change state beyond validation.** `observer_clear` wipes
> the store. There is no equivalent `POST /api/clear` in the REST surface.

There is no `POST /api/clear` — that clause is literally true. But `DELETE /api/data` exists
(`observer/internal/api/handler.go:93`, calling `clearData`), so the **bolded claim it supports is
false**. REST can clear the store; MCP is not the only mutating interface.

This is worse than a plain error. The narrow sentence is checkable and passes; the general claim it exists
to support does not. The reviewer caught it and corrected themselves mid-review rather than leaving the
gap in their own gap list.

## 3. `observer-http.md:100` — HTTP-001 is false, and the citation range hides it

The reviewer stopped at #2. Chasing it one step further finds the more serious version:

> HTTP-001 (proposed) — only `POST /api/validation/*` changes state; every `/api/query/*` route is a
> read. True at `88aebe8` (`api/handler.go:75-92`)

The state-changing routes are:

```
handler.go:89   POST   /api/validation/run
handler.go:90   POST   /api/validation/refresh
handler.go:91   POST   /api/validation/analyze
handler.go:93   DELETE /api/data          <- outside the cited range
```

The invariant is false, and **the cited range stops one line before the counterexample.** Extending it by
a single line would have shown the route that breaks the rule.

### Why this one matters beyond obstudio

`docs/evaluations/selfeval/archagent/CALIBRATION.md` says of the citation-resolution check:

> This does not catch a citation that resolves but does not support the claim — nothing mechanical will.

That was written as a known limit. This is the limit occurring, in the artifact written by the person who
wrote the sentence, one turn later. `api/handler.go:75-92` resolves perfectly: the file exists, the lines
exist, they contain route registrations. It is a *well-formed, resolvable, and wrong* citation.

I do not think the range was drawn to exclude line 93 — it was almost certainly copied from the block I
had scrolled through. That is the point. **A citation range is a claim about what is not in it**, and
nothing checks the boundary. The cheap partial defence is to prefer a whole-symbol or whole-block citation
over a hand-typed line range, since a range's edges are exactly where an unexamined counterexample sits.

## Found by the blind judge, after the human review (all verified against the code)

4. **SKILL-002 is marked `active` / "Currently held" and is false.** Four per-skill scripts hold real
   logic with no `references/scripts/` counterpart: `scan_python_otel_topology.py` (83 lines),
   `validate_gap_closure.py` (712), `validate_reader_report.py` (599), `validate_configure_output.py`
   (1222) — ~2,616 lines. I read `observe_report.py`, a genuine 32-line shim, and generalised to all of
   them. Python, which archagent analyses: the most checkable claim in the table, asserted instead.
5. **CLI-001 is false.** `api/handler.go:41`, `:72`, `:73` construct `validator.NewStore`,
   `validator.NewService`, `dashboards.NewResolver` — so `cmd` is not the only composition point.
6. **"64 Go files under `observer/`"** (stated twice) — `observer/` has 57. 64 is the repo-wide count
   including the `evals/` fixtures this artifact explicitly puts out of scope, so the number contradicts
   its own scoping.
7. **`Store` is not "one `sync.Mutex`"** — `store.go:313-332` has `mu sync.RWMutex` plus `subMu`,
   `invalidateMu`, `changeMu`.
8. **CORS is wide open and undescribed.** `Access-Control-Allow-Origin: *` (`api/handler.go:283`) with an
   unconditional WebSocket `CheckOrigin` (`websocket.go:21`) means any page the developer browses can read
   their telemetry and call `DELETE /api/data`. The artifact leans on "local by default, which is the
   product"; local is not unreachable. No invariant covers it and the "deliberately not written" section
   does not name it. **The strongest finding of the round, and neither the human nor I found it.**
9. **The validator state diagram is wrong.** `idle → running: Run() or telemetry changed`,
   `running → cancelled: new telemetry arrives mid-run` and `cancelled → running` do not exist:
   `MarkTelemetryChanged` (`manager.go:68`) only marks the store stale, runs begin on an explicit
   `Service.Run`, cancellation reaches `cancelActiveRun` only via `Reset`, and nothing auto-restarts.

## Status

| # | Where | Severity | Fixed |
|---|---|---|---|
| 1 | `deployment.md:6` | minor — wrong pointer, right prose | no |
| 2 | `mcp-server.md` | moderate — false claim behind a true sentence | no |
| 3 | `observer-http.md:100` (HTTP-001) | moderate — false invariant, range hides the counterexample | no |
| 4 | `invariants.md` (SKILL-002) | **serious** — a rule asserted `active` that the code violates, in an analysable language | no |
| 5 | `observer-cli.md` (CLI-001) | moderate — false invariant | no |
| 6 | `index.md`, `constitution.md` | minor — file count contradicts the stated scope | no |
| 7 | `telemetry-store.md` | minor — concurrency described wrongly | no |
| 8 | *absent* — CORS / WebSocket origin | **serious** — an unprotected path the documents' central claim implies is safe | no |
| 9 | `validator.md` diagram | moderate — edges the code does not have | no |

All still unfixed. They are the work-list for the next `describe` update pass; fixing them now would make
the two scorings incomparable to any later re-score of the same revision.


## Where each was addressed in archagent (2026-08-12)

The artifact itself is left as it was — it is evidence, and re-scoring it later has to be against the same
text. What mattered was whether each defect was preventable in the tool or the prompts. Eight of nine were.

| # | Defect | Fixed in |
|---|---|---|
| 4, 5 | invariants asserted `active` that the code violates | **`check` reporting.** `gen` already knew these rows were skipped; `check` never showed it. It now lists them under *Not checked — asserted in invariants.md, verified by nobody*, and an all-prose artifact gets `No invariant was checked … this is not a passing run` instead of a pass. |
| 1, 7 | a citation that resolves and is wrong | `describe` rule 1 — cite the line, and read the line you cite |
| 3 | HTTP-001's range stops one line before its counterexample | `describe` rule 2 — a line range is a claim about what is *not* in it; prefer whole-symbol citations |
| 2 | a true narrow sentence supporting a false general claim | `describe` rule 3 — "only"/"never" are exhaustiveness claims; enumerate and name the command |
| 4 | generalised from one of five sibling scripts | `describe` rule 4 — if a claim covers N files, open N files |
| 6 | a count contradicting the artifact's own scope | `describe` rule 5 — every number comes from a command, and name it |
| 9 | state-diagram edges the code does not have | `describe` — a state diagram is a set of claims, one per edge; cite the code that raises each event |
| 8 | CORS / WebSocket origin wide open and undescribed | **not fixable in a prompt** — filed as [#8](https://github.com/BenedatLLC/archagent/issues/8), a new `permissive-origin` signal for group D |

The `check` change is the one with teeth. The rest are instructions a generating agent may or may not
follow; that one makes the tool refuse to call an unchecked artifact clean, which is the same principle
(ADR 0002) applied to its own reporting rather than to a scan.

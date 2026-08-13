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

## Status

| # | Where | Severity | Fixed |
|---|---|---|---|
| 1 | `deployment.md:6` | minor — wrong pointer, right prose | no |
| 2 | `mcp-server.md` | moderate — false claim behind a true sentence | no |
| 3 | `observer-http.md:100` (HTTP-001) | moderate — false invariant, range hides the counterexample | no |

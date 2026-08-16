# Predicate claims — step 1, second attempt (2026-08-16)

Run against the pre-registration in `PREREGISTRATION-2.md`, which was committed before the measurement.

**The gate was ≥10 of the 12 named defects. All 12 were caught, plus one that was predicted not to be.
The gate passes.**

## Result against the prediction

| target | claims | agree | diverge |
|---|---|---|---|
| obstudio @ `88aebe8` | 15 | 9 | **6** |
| wardrowbe @ `v1.7.0` | 20 | 12 | **8** |
| | **35** | 21 | **14** |

Every one of the 12 named defects was caught, by the claim and kind predicted for it:

| # | defect | caught by | kind |
|---|---|---|---|
| O-2 | "MCP is the only outward interface that changes state" | C-002 | `absent` |
| O-3 | HTTP-001: "only `POST /api/validation/*` changes state" | C-001 — `DELETE /api/data` is not in the artifact | `set` |
| O-5 | CLI-001: "`cmd` is the only composition point" | C-003 — four constructor calls under `internal/api` | `absent` |
| O-7 | "`Store` is one `sync.Mutex`" | C-004 — `subMu`, `invalidateMu`, `changeMu` missing | `set` |
| W-1 | "no schema for schedules, so no public write path" | C-003 — `ScheduleCreate` exists | `absent` |
| W-2 | "eight SQLAlchemy tables" | C-001 — nineteen table names, none matching the eight | `set` |
| W-4 | "`validate_security` logs rather than raising" | C-005 — a `raise` is there | `absent` |
| W-5 | "falls back to local auth" | C-006 — returns `dev` and `unknown`, never `local` | `set` |
| W-6 | the services table omits `outfit_service` | C-007 | `set` |
| W-7 | the diagram's `stale → queued: swept and requeued` | C-004 — no `queued` state exists | `set` |
| W-10 | `ItemStatus` named a contract, values never enumerated | C-004 — same claim | `set` |
| W-18 | "schemas for seven of eight models" | C-002 — six modules, two of them unmatched | `set` |

**One defect was caught that the pre-registration predicted would not be.** O-1 — the artifact cites
`cmd/obstudio/embed.go` as embedding the React UI, when that file embeds the skills and
`internal/web/static_embed.go` embeds the UI. Written as a `holds` claim ("the UI is embedded by
`cmd/obstudio/embed.go`") it fails outright, and as a `set` of directives it shows both the missing one and
the wrong attribution. The prediction assumed a mis-attribution needs a prose-to-claim comparison; it does
not, because **writing the claim forces the assertion into a form a command can refute.**

So 13 of the 28 recorded defects are now reachable, against 8 under the value-based design.

## The authoring error rate fell, as predicted, but not far

The first attempt's most important result was that 10 of 37 commands (27%) measured something other than
what the prose meant. This time: **7 of 35 (20%)**.

| target | command | what it did wrong |
|---|---|---|
| wardrowbe | C-002 | `tr -d '.py'` deletes those *characters* anywhere — `family` became `famil` |
| wardrowbe | C-004 | swept every enum in `item.py`, mixing `ItemStatus` with `TaggingStatus` and `TaggedBy` |
| wardrowbe | C-016 | flagged the proxy route handler, which is *supposed* to read `BACKEND_URL` |
| obstudio | C-006 | evidence written without the filename prefix `rg` emits for a multi-file search |
| obstudio | C-008 | searched for `--host`; the source registers the flag as `"host"` |
| obstudio | C-012 | too broad — 510 characters of output for a claim needing one line |
| obstudio | C-013 | used a look-around, which `rg`'s default engine does not support |

The drop is real but small, and the reason is instructive: `absent` and `holds` removed the *reproduce an
exact figure* class of error entirely, and what remains is **scoping** — a command that looks at the right
place and takes in more than the claim covers. That class does not go away with a different claim kind.

**In production these would still be silent**, exactly as the first attempt concluded, because the recorded
evidence would come from the command rather than from the prose. One mitigation now has evidence behind
it: five of the seven show themselves the moment the *output* is visible next to the claim (`famil`, three
enums where one was meant, a filename prefix, a proxy path, 510 characters). Recording output is not a
nicety.

## Two prototype defects that only running could find

Both were found by real claims failing, not by tests, and both would have been shipped:

- **A URL prefix is not a path.** `rg -v '/api/validation/'` was refused as an absolute path escaping the
  root. It was the `absent` claim for O-2 — the most valuable kind, refused by the safety check. The fix
  is to treat a leading `/` as a path only when its first component is a directory that actually exists.
- **The output cap broke `absent` claims.** Capping output inside `run` made any broad `absent` claim
  unrunnable, because a *failing* `absent` claim legitimately produces a lot of output and only its
  emptiness matters. The cap belongs where the evidence is recorded, not where the command runs.

Together with the two from the first attempt — splitting a command on `|` breaks regex alternation, and a
regex beginning with `/` is not a path — that is four implementation traps on the way to a working
prototype, all in the parsing and safety layer rather than in the idea.

## What is still out of reach

The 15 defects not caught are unchanged in character from the first attempt:

- **Omissions (4)** — wide-open CORS, the SSRF-shaped route, per-user ownership, no invariant covering it.
  Nothing makes an author claim something they never considered. **Both security findings in this
  project's history are here**, and that remains the honest limit of the mechanism.
- **Presentation (3)** — missing diagrams, an uncaptioned map, an unfalsifiable rule.
- **Incidental counts (3)** — the file counts, which this design deliberately stops treating as claims.
- **Judgements and proxies (3)** — "per-skill scripts are shims", the invented validator diagram edges,
  three-path image access.
- **Tooling and text (2)** — an invariant marked `active` that the code violates, and the
  shell-corrupted paragraph.

## Recommendation

**Proceed to step 2.** The gate was set before the measurement and cleared without qualification, on a
design whose central rule — claims are predicates about closed sets and properties, never magnitudes —
also answers the objection that started the redesign: a documentation claim should be something whose
falsity changes what a reader does.

Two conditions to carry into step 2, both earned by these results rather than assumed:

1. **Recording the command's output is a requirement, not an option.** Five of the seven authoring errors
   are visible on sight in the output and invisible in the verdict.
2. **The `describe` prompt should stop emitting incidental counts.** Three recorded defects disappear if
   the number is never written, and no claim can protect a number nobody needs.

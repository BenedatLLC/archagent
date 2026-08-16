# Predicate claims — pre-registration for step 1 (second attempt)

**Written and committed before the measurement runs.** The first attempt predicted 17 divergences and
produced 8; the post-hoc explanation was that a claims table only catches a defect when the artifact
commits to a *number*, and most fabricated claims are not numbers. This is the redesign and its
prediction. Recording the prediction beforehand is what stops the redesign being fitted to the answer it
already knows.

## What changed in the design

Claims are **predicates**, not values, in three kinds:

| kind | passes when | used for |
|---|---|---|
| `absent` | the command finds nothing | *there is no local-auth mode*; *nothing outside `cmd` constructs a service* |
| `holds` | the command finds something; the output is kept as evidence and **not compared** | *`validate_security` raises* — so a line number moving is not a false alarm |
| `set` | the members are exactly these | the members of an enum, the routes that change state, the modes a function returns |

**There is no "this number is 19" kind, deliberately.** A count that is wrong by two usually changes
nothing a reader would do — *"Foo is called in ten places"* against eight is trivia, and a mechanism that
fires on it trains people to switch it off. Where a total genuinely matters it is because the set is
closed and completeness is the point, and then it is expressed as the **members**, so what fires is
"a fifth status appeared" rather than "the number moved".

This also removes a defect class by not writing it. Three of the 28 recorded defects are incidental counts
("64 Go files", "65 backend Python files", "117 frontend files"). Under this design they are not claims at
all, and the `describe` prompt should stop emitting them — a number nobody needs cannot be wrong.

## The prediction

Classified before running, defect by defect, naming the claim that would catch each. **12 of the 28
confirmed defects are predicted to be caught**, and the acceptance test is by name rather than by count,
because a bare count can be reached by unrelated finds.

### Predicted caught (12)

| # | defect | claim that catches it | kind |
|---|---|---|---|
| O-2 | "MCP is the only outward interface that changes state" | the routes that change state | `set` |
| O-3 | HTTP-001: "only `POST /api/validation/*` changes state" | same set | `set` |
| O-5 | CLI-001: "`cmd` is the only composition point" | constructor call sites outside `cmd` | `absent` |
| O-7 | "`Store` is one `sync.Mutex`" | the locks declared in `store.go` | `set` |
| W-1 | "`models/schedule.py` has no matching schema, so no public write path" | a `ScheduleCreate` schema exists | `absent` (violated) |
| W-2 | "eight SQLAlchemy tables" | the `__tablename__` values | `set` |
| W-4 | "`validate_security` logs rather than raises" | `raise` in `validate_security` | `holds` |
| W-5 | "falls back to local auth" | the modes `get_auth_mode` returns | `set` |
| W-6 | the services table lists seventeen, omitting `outfit_service` | the service modules | `set` |
| W-7 | the diagram's `stale → queued: swept and requeued` | the members of `ItemStatus` | `set` |
| W-10 | `ItemStatus` named as a contract, values never enumerated (and named wrongly by a reviewer) | same set | `set` |
| W-18 | "schemas for seven of eight models" | the schema modules | `set` |

### Predicted not caught (16), and why

- **Omissions (4)** — CORS wide open, the SSRF-shaped route, per-user ownership, no invariant covering it.
  A claims table cannot make anyone claim something they never thought of. Unchanged from the first design.
- **Presentation (3)** — missing diagrams, an uncaptioned map, an unfalsifiable rule.
- **Incidental counts (3)** — the file counts above, which this design deliberately stops treating as
  claims.
- **Mis-attribution (1)** — the UI embed cited to the wrong file. The *fact* is checkable; the defect is
  that the prose names a different file than the claim does, and nothing mechanical compares prose to a
  claim's description.
- **Judgements and proxies (3)** — "per-skill scripts are shims", the validator's invented diagram edges,
  the three-path image access. A line count is a proxy for "shim", and taking the proxy for the claim is
  how the defect was written in the first place.
- **Tooling and text (2)** — an invariant marked `active` that the code violates (already fixed
  elsewhere), and the shell-corrupted paragraph.

## The gate

**Accept and proceed to step 2 if at least 10 of the 12 named defects are caught.** By name, not by count.

**Reject if fewer than 8 are caught.** Between 8 and 10: undecided, and the reason each miss occurred
decides it rather than the total.

Two further numbers to record, neither a gate:

- **New defects found** — the first attempt turned up two nobody had seen. Any is a point in favour.
- **The authoring error rate.** The first attempt's most important result was that 10 of 37 commands
  measured something other than what the prose meant, and that in production those errors would be silent
  rather than loud. **The same count is taken again**, and it is expected to *fall*, because `absent` and
  `holds` do not require a command to reproduce an exact figure — the largest source of the first
  attempt's errors. If it does not fall, that is an argument against the mechanism in any form.

## Recording the evidence

Every command's output is stored beside it, as the first attempt's write-up recommended: `19` tells a
reviewer nothing, the nineteen table names tell them whether the command measured the right thing. Before
anything is recorded it is scanned for credential shapes — key prefixes, JWTs, private-key blocks, long
hex, high-entropy runs, assignments to secret-looking names — and a match **refuses the claim rather than
truncating the output**, since truncating stores a partial secret and reports success.

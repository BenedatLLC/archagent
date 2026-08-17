# Drift experiment — results (2026-08-16)

Pre-registered in `PREREGISTRATION-drift.md`. Real later history: wardrowbe `v1.7.0` → `v1.8.0`, 21
commits, 95 files, 4,589 insertions, written by the project's developers. The artifact (generation run 1)
and the claims file (`claims/arm-a-run1.md`, 15 entries, written days earlier for a different measurement)
were both fixed before the diff was looked at.

**The claims file caught nothing that `drift` did not. It caught nothing at all.** The pre-registered
result that "would argue against the design" is the result that occurred, and the reason is structural
rather than accidental.

## Ground truth: what the release made stale

Enumerated from the diff before comparing to either instrument.

| # | what changed | `drift` | claims |
|---|---|---|---|
| 1 | **the stale-item sweep was rewritten** — no longer a blind time-based condemn; it now checks each job's state in Redis and never condemns a row whose job is alive, with a 60s grace for never-started rows | no | no |
| 2 | new backend service `external_outfit_service.py` | **yes** | no |
| 3 | three new frontend modules — `upload-manager.ts`, `upload-queue.ts`, `calendar-indicators.ts` | **yes** | no |
| 4 | two new config keys — `ai_tagging_concurrency`, `ai_retry_cooldown_seconds` | no | no |
| 5 | two new columns and four new migrations — `ai_failed_at`, `upload_key` | no | no |
| 6 | new route `POST /suggestions` | **yes** | no |
| 7 | manual and bulk retry are now gated behind a cooldown after failure | no | no |
| 8 | counts moved — routes 104→106, migrations 22→26, backend tests 401→470 | no | no |

**`drift` 3 of 8. Claims 0 of 8.**

Item 1 is the most serious by a distance. The artifact describes the sweep's mechanism in a dedicated
paragraph, and the new code's own comment calls the behaviour it replaced *"the previous design"*. **No
lexical instrument reaches it** — the file did not move, no declaration changed, and no count it asserts is
different. It needs a reader.

## Why the claims file caught nothing

Not coverage, and not bad luck. **The predicate redesign deliberately removed the capability that would
have caught item 8.**

The value-based first design compared a recorded number against a fresh one, so 104→106 routes would have
fired. It was replaced precisely because that fires on trivia, and the argument for replacing it was
correct: a route count wrong by two changes nothing a reader would do. Under the predicate design a `holds`
claim records its output as evidence and **does not compare it**, so all three moved counts pass silently —
by design.

So the design faces a real dilemma that neither version resolves:

- **Compare values** → drift is detected, and most of what you detect is trivia that trains people to
  ignore the checker.
- **Do not compare values** → no trivia, and no value-drift detection either.

The five `set` claims in the file are the kind that *could* have caught meaningful drift — sets fire when
membership changes, which is never trivia. None of the five happened to cover anything this release
changed: tables (19, unchanged), compose services (unchanged), locales (unchanged), third-party hosts
(unchanged), model modules (unchanged).

## The one constructive result, and it is post-hoc

Checked after the fact and labelled as such. A `set` claim over the settings fields — which the file does
not contain — would have caught item 4:

```
config keys at v1.7.0: 44        at v1.8.0: 46
new: ai_retry_cooldown_seconds, ai_tagging_concurrency
```

**And `drift` structurally cannot see this.** The artifact itself documents the reason as a tool
limitation: `drift`'s config check reads declared keys against `os.getenv` sites, and pydantic-settings
resolves field names to environment keys at runtime, so every one of these 46 keys is invisible to it.
Run 1's own `drift` output lists 56 "dangling config" findings that are all this false positive.

That is the shape of a real argument for the mechanism, and it is narrower than the design claims: **a
claims file earns its place where it covers a closed collection that archagent's static analysis cannot
see.** Config keys under pydantic-settings are exactly that. "Makes much of the drift computation
mechanical" is not supported.

## Against the pre-registered predictions

| prediction | outcome |
|---|---|
| `drift` catches structural staleness, claims mostly do not | **confirmed** — 3 of 3 structural items, and claims caught none |
| claims catch value staleness, `drift` mostly does not | **refuted** — claims caught no value staleness, because the predicate design removed value comparison |
| the two overlap little | vacuously true; claims caught nothing to overlap with |
| claims recall is limited by the file's size | true, but not the binding constraint — the binding constraint is the *kind* of claim, not the number |

## What this changes

**The drift justification for computed claims does not survive as written.** §1 of the design says the
mechanism makes drift mechanical because "a code change that moves a number is reported by comparison
rather than inferred from a diff". On this release it reported nothing, and the numbers that moved were
ones nobody should act on.

**A narrower justification does survive**, and it should replace the broad one: `set` claims over closed
collections that archagent cannot analyse statically — pydantic-settings keys here; anything in a language
the tool does not parse elsewhere, which is obstudio's entire situation. That is a real gap, it is
documented in the artifacts as a known tool limitation, and nothing else fills it.

**Item 1 is the standing reminder.** The most consequential staleness in a 21-commit release was a
rewritten mechanism inside an unmoved file, and it is invisible to `drift`, to claims, to the recurrence
suite, and to the checklist. Every mechanical instrument this project has built would report that artifact
as clean. That is not an argument against any of them; it is the boundary of the whole approach, and it is
worth stating in the design rather than discovering again.

## Limits

- One revision pair on one repository, and a 21-commit release is not a typical single commit.
- 15 claims over a 27,000-word artifact. A larger file would have more `set` claims and more chance one
  covers what moved — but the value-comparison gap is a property of the design, not of the sample.
- The checkout at `~/.cache/archagent/variance/run-1` is left at v1.8.0 code with the v1.7.0 artifact, so
  the comparison can be re-run.

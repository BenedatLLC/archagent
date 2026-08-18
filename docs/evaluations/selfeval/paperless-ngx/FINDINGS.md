# Calibration round 4 — paperless-ngx (machine half)

Target: paperless-ngx at `v3.0.5` (`8fb73b270`), 727 source files under the configured paths — Django apps
under `src/`, an Angular frontend under `src-ui/src`. Roughly three times wardrowbe.

**The human review is outstanding; this records only the machine half.** The calibration number — human
against blind judge — cannot be computed until that comes back.

## Scores

| instrument | score |
|---|---|
| deterministic rubric | **1.00** — first clean score in the project; 727/727 covered, 69/69 globs resolve, zero drift |
| blind model judge (1–5) | **4.33** — accuracy 4, completeness 4, prose 5, diagrams 5, invariant strength 4, criticality 4 |
| code-derived checklist | **0.92** — 23 correct, 0 wrong, 2 absent (both `minor`) |

Judge means across rounds, all on `brief-v3` and therefore comparable: obstudio 3.67, wardrowbe 3.17,
paperless-ngx **4.33**. Against a measured floor of ±0.10 that is a large gap — and confounded, because it
is a different repository of different difficulty. It is not evidence that archagent improved.

## The finding that matters most, and it is about archagent

The judge's first defect: `index.md:216` claims *"Every `PAPERLESS_* ` key the system reads is listed under
`**Config:**`"*, while `deployment.md` lists 98 of roughly 185. Chasing that produced something worse than
a wrong sentence.

```
keys archagent's configscan finds (literal os.getenv):   98
keys the artifact declares:                              98
read-but-not-declared:                                    0
declared-but-not-read:                                    0
keys read only through a helper wrapper:                 79
```

paperless reads most of its configuration through `get_bool_from_env("PAPERLESS_X", ...)` and siblings —
79 keys whose names never appear as a literal argument to `os.getenv`. `configscan` matches literal
patterns only, so it sees exactly 98, the artifact declares exactly those 98, and **`drift` reports zero
config drift in both directions.**

So the tool does not merely miss the gap. **It certifies an incomplete list as complete.** And the loop is
self-reinforcing: the describing agent worked from archagent's view of the configuration surface, so the
artifact matches the blind spot precisely, and `drift` then agrees with itself. Nothing in the pipeline can
see the other 79 keys.

This is the eighth instance of the pattern Appendix A tracks — a condition rendering as a plausible clean
result — and the first where the tool actively confirms a false claim rather than failing quietly.

**It is also the third independent instance of the blind-spot class** that the computed-claims work
narrowed down to: obstudio's Go install targets, wardrowbe's pydantic-settings keys, and now paperless's
wrapper-read config keys. Three different repositories, three different mechanisms, same shape — a closed
collection archagent cannot enumerate, where an artifact's claim about completeness goes unchecked. A
`set` claim over `PAPERLESS_*` keys would have caught this one.

### What to do about it in the tool

Two options, and the second is the honest one:

1. **Teach `configscan` about wrapper functions** — find single-argument helpers whose body calls
   `os.getenv` on their parameter, then treat calls to them as config reads. Tractable, and it would move
   79 keys from invisible to visible here.
2. **Have `configscan` report its own coverage.** Whatever it learns to parse, some project will read
   config another way. Reporting "98 keys found by literal match; N further calls into helpers not
   resolved" turns a silent false negative into a stated limit — the same principle `check` already
   applies when it refuses to call an unchecked artifact clean.

Both are worth doing; only the second closes the class.

## The other two judge defects

- **django-cachalot is absent from the artifact entirely.** `settings/__init__.py:743` appends it to
  `INSTALLED_APPS` and `db_cache.py:8` supplies its key generators — an optional whole-ORM Redis read cache
  that changes staleness reasoning in the permission and search paths the artifact documents in detail.
  An omission, so no mechanical instrument reaches it.
- **Invariant-ID integrity is broken in two places.** `parsers.md:219` presents `PAR-001` as a table row
  that does not exist in `invariants.md` (the rule is `BND-006`), and `UI-002` means one thing in
  `invariants.md:20` and something unrelated in `web-client-ui.md:182`.

The third is a **new defect class, and it is mechanically checkable**: every invariant ID cited in a
subsystem document should exist in `invariants.md` and mean one thing. That is a `lint-docs` rule worth
adding, and it would have caught both instances.

## What the checklist result says about the instrument

0.92 with **zero `wrong` verdicts**. Both absences are silences — the per-locale Angular build, and at-rest
encryption.

The code-derived construction did what it was for: this is a *valid* quality estimate, where wardrowbe's
1.00 and obstudio's 0.88 were biased by having been written from a different artifact's mistakes.

It did **not** solve the headroom problem. Two items can move against a two-arm gate needing five. Across
three targets and both construction methods, fresh artifacts now score 0.88, 0.92 and 0.94–1.00.
**`describe` is accurate enough that a per-item accuracy instrument cannot discriminate between variants of
it.** The earlier diagnosis — that saturation was mainly about how checklists were built — was half right;
construction was a real problem and not the main one.

**Where headroom remains is completeness, not accuracy.** Zero wrong answers, four `4`s from the judge of
which two are coverage-shaped, five under-covered areas the generating agent declared itself, and both
checklist misses being silences. Any future two-arm comparison should be scored on coverage depth — the
dimension `status`'s thin and no-diagram flags were built for — not on factual accuracy.

## Two process notes from the run

- **`**Services:**` was dropped** because archagent does not discover compose files under
  `docker/compose/`, which also leaves `evaluate`'s data-ownership and cross-service families inactive. An
  archagent gap, not an artifact defect.
- **No invariant batch was presented for approval.** `describe` says to offer promotable rules as a batch
  for a yes/no; the run was unattended, so four rules were promoted on the agent's own verification. This
  will recur every time an arm is generated for a comparison, and needs a decision rather than a workaround.

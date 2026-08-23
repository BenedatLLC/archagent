# Architecture log

## 2026-08-01 — artifact created

First description of archagent by archagent. Eight subsystems identified from the real import graph
(an `ast` walk over every module in the package), not from memory.

Two observations recorded at creation, both confirmed against the code rather than assumed:

- `drift.py` is a hub: seven modules import it, but most of them want `_git`, `_source_files` or
  `_import_graph` — shared plumbing — rather than the drift check itself. Recorded as ADR 0003.
- `evaluate.py` at 1095 lines is the largest module and imports twelve siblings. It is the composition
  root for the signal families rather than a god object, but it is the first place to watch.

## 2026-08-22 — update pass before the 1.0 release

Reconciled the artifact against everything added since it was written. `drift` named seven possibly-stale
documents and one undocumented module; both lists are now empty.

- **`described.py` was the undocumented module**, and it is the answer to a defect the artifact itself
  demonstrated. `status` reported which files a subsystem *claims*; it could not report whether the
  claiming document says anything about them. Assigned to `reporting`.
- **Four subsystems gained capabilities the documents did not mention**: `configscan` now resolves helper
  wrappers and pydantic-settings fields as well as literal `os.getenv` (98 keys to 228 on one reviewed
  repository); `lint-docs` checks invariant-ID citations as well as Mermaid syntax; `init` supports Codex
  as an opt-in agent; and `evaluate` gained the two group-D exposure signals.
- **`check` no longer reports an unrunnable checker as passing.** When ast-grep's JSON failed to parse,
  the handling branch returned a pass for every invariant it touched. It also strips colour from the
  tools it launches, because an inherited `FORCE_COLOR` made a parser stop matching — the same failure
  arriving by a different route. Recorded in `deployment.md`, since it is why archagent sets any
  environment variable at all.
- **Three line citations in `cli.md` had drifted** to point at unrelated code. Nothing checks a line
  number, and nothing here does now either; they were corrected by hand. A citation that resolves to the
  wrong lines reads exactly like one that resolves to the right ones, which is the shape of most of the
  defects in this log.

Coverage is 30 of 30 source files across 8 subsystem documents, and all 30 are named somewhere.
`reporting` stays flagged `no diagram` on purpose — the reasoning is in that document.

## 2026-08-23 — declared dependencies join the structural graph (issue #25)

`evaluate` built its subsystem graph only from parsed imports, so on a repository in a language archagent
cannot analyse every structural signal produced nothing and the run said so nowhere. obstudio is the
worked example: ten subsystems, seventeen declared connectors, zero code-derived edges, six silent
signals — and a **1.00** on the rubric's *evaluate signal families active*, which reads the tool's own
coverage report and therefore certified a gap it could not see.

Declared `**Connects:** … via import` edges now join the graph, per DD-4. Bounded three ways: only
`import` kinds, a confidence downgrade plus a note on any finding resting on an uncorroborated edge, and
a coverage entry when the whole graph is declared.

The change was measured before it shipped rather than after. On archagent, wardrowbe and fastapi-template
it adds zero edges — declared and parsed already agree, because `drift` reports any disagreement — so the
blast radius is exactly the repositories that were blind. obstudio goes from 21 findings to 29, and its
`implicit-coupling` count drops from 8 to 6 as two co-changing pairs turn out to have a declared
dependency after all.

## 2026-08-23 — tests are not a layer (issue #26)

Calibration rounds 2 and 3 labelled seven `layer-inversion` findings blind across three repositories and
the split was total: all three confirmations were production code, all four dismissals were test or
migration packages. Every dismissed subsystem was tiered `infra` — the bottom rank — so everything it
imported read as "upward", and one test subsystem produced an inversion against every production
subsystem it exercised. wardrowbe's produced four.

The cause was `describe`'s vocabulary, not the check: the subsystem template offered
`<ui | domain | infra>` with no way to say *this is not a layer*, and `infra` was the natural pick for
test plumbing.

Two changes, chosen together because neither is sufficient. The ADL now **recognises non-layered tier
tokens** (`test`, `migration`, `ops`, …) and `describe` is told to use them — which stops the problem being
created. And `drift` now **reports a subsystem that covers only non-production code while claiming a
layer**, which is a doc-vs-code disagreement rather than a smell, and fixes artifacts that already exist
by telling the author to correct them rather than working around them.

Validated end to end on wardrowbe: correcting the two tiers takes `layer-inversion` from 7 findings to 2,
removing exactly the five a reviewer dismissed and keeping exactly the one they confirmed.

`tiers.py` is new, and is a leaf on purpose — `evaluate` already imports `drift`, so the shared vocabulary
could not live in either without closing a second cycle. It absorbed the three copies of `tier_of` that
had accumulated.

The drift check catches two of the four known cases. It misses fastapi-template's `backend-ops`, whose
startup and seed files sit in the app package under no distinguishing path. Inferring intent from a
filename like backend_pre_start is the name-based guess this project has twice regretted, so it is left to
`describe`.

## 2026-08-23 — a key the deployment reads is read (issue #24)

`read_config_keys` scans the configured `source_paths` — where application code lives, and precisely
where deployment configuration does not. So a key consumed only by a compose file or a container
entrypoint came back *declared but never read*: true, and not a defect. wardrowbe reported 24 of them at
once, which invites deleting an accurate manifest and buries the finding that matters.

`deployment_config_keys` asks the same question of the files `deployscan` already opens: compose
`environment:` blocks **and** raw `${VAR}` interpolation, `ENV`/`ARG` in Dockerfiles, and `env:` lists in
Kubernetes manifests. Interpolation matters on its own — `BACKEND_PORT` appears only in a port mapping,
so a structural scan of environment blocks would still have missed it.

wardrowbe goes from 24 dangling keys to 2, and both survivors are real: `AI_PROVIDER` appears nowhere,
and the manifest says `OIDC_ISSUER` where the code and compose both say `OIDC_ISSUER_URL`. That near-miss
was invisible among two dozen correct findings, which is the whole argument for the change.

`.env.example` is **not** counted as evidence of use, though the issue proposed it. It is already read as
a manifest, so counting it would make every declared key justify itself and empty the check; and where it
is not the manifest it is still a second declaration rather than a use.

Obstudio's seven remaining dangling keys are a different shape and are left: all are read by its Go core,
which archagent cannot parse, and two of those are *written* by the TypeScript extension for the Go
process to read.

## 2026-08-23 — the describe → evaluate hand-off, and where signal guidance lives

Prompted by a question about merging `evaluate` into `describe`. The merge turned out to be mostly done
already — `describe` runs `archagent evaluate` in its main flow and again on the update path — so the two
commands are not really two things a user must remember. What the question surfaced instead were three
defects in the prompts.

**The hand-off was an allusion.** Step 7 said "the `evaluate` skill judges the candidates" and never named
`/archagent-evaluate`, so whether it was invoked was left to chance. A user who lands on raw candidate
signals at the end of a long describe run has the interpretation guide nowhere in front of them. Now an
instruction, in the main flow and on the update path.

**The signal guidance was in the wrong prompt.** `describe` carried the `layer-skip` caveats while
`evaluate` — the skill whose entire purpose is interpreting signals — did not mention the sign at all. Moved,
and expanded with what the labelling rounds established: `layer-inversion` was right 3 of 3 on production
code and wrong 4 of 4 on test and migration packages, and `layer-skip` was dismissed every time.

**And the guidance had gone stale.** It claimed a shared kernel "will always show `layer-skip`" and that
flat peers show skips "whenever the orchestrator calls a capability directly". Neither survives the
narrowing: a skip now requires the intermediate tier to be occupied, so `app -> domain` reports nothing.
Worse, it advised modelling flat peers as a single tier "rather than forcing a strict ladder" — telling a
reader to distort the model to quiet a false positive that had been fixed twice, and the opposite of what
issue #26 established.

`tests/test_prompts.py` is new. The prompts ship as package data and nothing imported them, so no test had
ever read one.

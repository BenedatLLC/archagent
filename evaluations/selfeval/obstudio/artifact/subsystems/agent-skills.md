# agent-skills — the instructions shipped to coding agents

**Covers:** `skills/**/*.py`
**Tier:** app

## Purpose

The `$otel-audit`, `$otel-instrument`, `$otel-verify` and Splunk skills: markdown instructions plus a few
Python helpers, installed into a developer's coding agent by `obstudio install`. This is where the
product's judgement lives — what counts as an observability gap, how to add instrumentation without
breaking a service, what evidence proves telemetry is real.

Mostly prose, deliberately. The Go binary handles telemetry; these files handle knowing what to do
about it.

## Topology and components

| Skill | Purpose |
|---|---|
| `otel-audit` | scan a service for coverage gaps; read-only for application code |
| `otel-instrument` | add auto-instrumentation and optional custom spans or metrics |
| `otel-verify` | prove existing instrumentation with tests and optional live OTLP evidence |
| `splunk-configure` | generate detector Terraform from an audit report |
| `splunk-detector-publish`, `splunk-dashboard-publish` | diff local Terraform against live Splunk, create only the gaps |
| `splunk-sync`, `splunk-dashboard-sync` | **deprecated** aliases of the two above |
| `splunk-dashboard` | dashboard spec authoring |
| `references/` | shared prose and the shared scripts every skill delegates to |

Each skill is a directory with `SKILL.md`, optional `scripts/`, and `tests/`.

## Key abstractions

**A skill is a prompt with a trigger list, not code.** `SKILL.md` front-matter carries `name` and a
`description` that reads as dispatch logic — `otel-audit`'s (`skills/otel-audit/SKILL.md:2-14`) enumerates
the phrasings that should invoke it ("what signals am I missing", "observability readiness") *and* the one
that should not: "Do NOT use for implementing code changes -- use $otel-instrument instead." Skill
selection is the hard problem, and it is solved with explicit negative examples.

**Scripts are shims over one shared implementation.** `skills/otel-audit/scripts/observe_report.py` and
`skills/otel-verify/scripts/observe_report.py` are both 32-line launchers that resolve
`../../references/scripts/observe_report.py` and `runpy` it, printing an actionable message if the bundle
is incomplete. The duplication is intentional — a skill directory has to be self-contained when installed
alone — and the real logic exists once.

The two shims have nonetheless already drifted: their docstrings read "the shared OTel report **JSON**
validator" and "the shared OTel report **flow** validator" respectively, and that one word is the entire
difference between the files. Minor, and worth naming only because it is exactly the shape of divergence
this pattern invites.

**Deprecated skills remain installed, not deleted.** `splunk-sync` and `splunk-dashboard-sync` still ship
and still work, marked deprecated in the README. Agents hold stale instructions, so removing a trigger
word breaks a user in a way renaming does not.

## State and tiering

None. Files copied into an agent's skills directory by `obstudio install`.

## Invariants

- SKILL-001 (proposed) — every skill's `SKILL.md` must carry `name` and `description` front-matter;
  installation and discovery depend on it.
- SKILL-002 (proposed) — a per-skill script under `scripts/` must not contain logic; the implementation
  belongs in `references/scripts/`. Currently held.

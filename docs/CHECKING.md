# Enforcing invariants with `archagent check`

A walkthrough of the enforcement half of archagent: what an invariant is, which kinds actually compile
into a checker today, how to read a run, and how to wire it into your commits and CI.

`docs/COMMANDS.md` is the option-by-option reference. This is the guide.

**Contents** — [The shape of a rule](#the-shape-of-a-rule) · [What compiles today](#what-compiles-today) ·
[The Rule DSL](#the-rule-dsl) · [Reading a run](#reading-a-run) ·
[Writing a rule that catches something](#writing-a-rule-that-catches-something) ·
[Rules nothing can check yet](#rules-nothing-can-check-yet) · [Automation](#automation) ·
[When a check is wrong](#when-a-check-is-wrong)

---

## The shape of a rule

Every invariant is one row of the first markdown table in `<arch-dir>/invariants.md`. Nothing else in the
artifact is enforceable, and nothing outside that table is parsed.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-001 | BOUNDARY | structural | python | `forbid archagent.evaluate -> archagent.cli` | error | [0001](…) | active |

Read it as a sentence: *this rule protects a **boundary**, it is enforced **structurally** (by static
analysis rather than at runtime), it applies to **Python**, and it says the `evaluate` module must not
import the `cli` module. Breaking it is an **error**. The reason lives in ADR 0001. The rule is
**active**.*

Two columns decide whether anything happens:

- **Type** — which architectural property the rule protects. `BOUNDARY` · `INTERFACE` · `DATAFLOW` ·
  `STRUCTURAL` · `PURPOSE`.
- **Tier** — *how* it is enforced, cheapest first. `structural` · `contract` · `pbt` · `model-check` ·
  `prose`.

Three more affect what happens when it breaks:

- **Severity** — `error` fails the run and exits non-zero; `warn` is reported and does not.
- **Status** — `active` and `proposed` are both checked. `deprecated` is dropped before generation and does **not** appear in the *not checked* list, so a deprecated row leaves no trace in a run at all — which is the intent, and worth knowing if you are wondering where a rule went.
- **Why** — a link to the ADR carrying the rationale. Not decorative: a rule with no stated reason is one
  nobody can safely delete, so it survives long after the reason has gone.

## What compiles today

**This is the part to read before writing rules.** The vocabulary above is larger than the set of
combinations that produce a checker, and a row that compiles to nothing is reported as *not checked*
rather than failing — correct, and easy to miss if you were expecting enforcement.

| Type | Tier | Applies-to | Compiles to |
|---|---|---|---|
| `BOUNDARY` | `structural` | `python` | an import-linter `forbidden` contract |
| `BOUNDARY` | `structural` | `ts` / `tsx` / `typescript` / `js` / `javascript` | a dependency-cruiser rule |
| `STRUCTURAL` | any | any | an ast-grep rule — matched on the rule starting with `forbid-pattern` |
| any | any | any | a property-based test — matched on the rule starting with `property` |
| any | `prose` | any | **nothing, deliberately** — recorded as documentation |
| any | any | any | otherwise **nothing**, reported as `no v1 generator for <type>/<tier>/<applies-to>` |

Consequences worth stating plainly:

- **`INTERFACE`, `DATAFLOW` and `PURPOSE` have no generator of their own.** They are useful as
  classification, and a rule of those types compiles only if it is written as a `property` rule.
- **The `contract` and `model-check` tiers compile to nothing at all.** They exist in the vocabulary as
  places to grow into.
- **`BOUNDARY` requires tier `structural`.** `BOUNDARY`/`contract` is a valid-looking row that produces
  no checker.
- **For `forbid-pattern` and `property` rules the Tier column is not consulted** — the rule text decides.
  Set it accurately anyway; it is what a reader uses to judge the cost of the check.

archagent's own table is four `BOUNDARY/structural` rows and six `STRUCTURAL/structural` rows. That is
the well-trodden path.

If you want to see what your own rows do before writing any code, `archagent gen` prints the compilation
without running anything — each rule under the checker it produced, and each skipped rule with the reason.
That is the fastest way to find out a row you expected to be enforced is not.

## The Rule DSL

### `forbid <a> -> <b>[, <c>…]`

A **BOUNDARY** rule: `<a>` must not import `<b>`, directly or transitively.

```
forbid archagent.evaluate -> archagent.cli
forbid app.domain -> app.web, app.api
```

For Python the names are dotted modules resolved against `[python] root_package`. **If `root_package` is
wrong or unset, every contract scopes to an empty module set and passes** — `archagent modules` exists to
diagnose exactly that, and `init` now flags it when it cannot guess one. For JS/TS the names are paths
(`src/domain`).

### `forbid-pattern <ast-grep pattern> [in|outside <scope>]`

A **STRUCTURAL** rule: a code shape that must not appear.

```
forbid-pattern print($$$)
forbid-pattern print($$$) outside src/archagent/cli.py
forbid-pattern from .$M import $$$ in src/archagent/config.py
```

`$X` matches one node, `$$$` matches any number. `in <scope>` flags matches only there; `outside
<scope>` flags everywhere *except* there — that is the "only this module may do this" case, and it is the
more useful of the two. Omit the scope to search all configured sources. A scope is a path, a glob, or a
dotted module.

**`outside` is what makes an architectural rule out of a lint.** "Don't call `print`" is a style
preference; "only the CLI layer may call `print`" is a statement about where output belongs, and it fails
the moment a domain module starts writing to stdout.

### `property <path::test>` and `property stateful <path::TestCase>`

A **behavioural or data** rule, checked by a property-based test — the tier for things static analysis
cannot see. "All state is per-user", "encode then decode returns the input", "the queue never loses a
message under any interleaving."

```
property tests/test_props.py::test_roundtrip
property stateful tests/test_store.py::StoreMachine
```

The target's extension picks the framework: `.py` scaffolds a Hypothesis `@given` stub, a JS/TS file
scaffolds a **fast-check** `fc.property`. `stateful` scaffolds a `RuleBasedStateMachine` (Python) or
`fc.commands` model (JS/TS) — random operation sequences checked against invariants, which is the right
shape for stores and state machines.

`check` runs these in **your project's** environment via `[python] test_command` / `[ts] test_command`,
and reports the counterexample the framework found. They are slower than the static tiers by orders of
magnitude, which is what `--skip-pbt` is for.

## Reading a run

```
archagent check
```

Four outcomes per row, and the difference between two of them is the point:

| | Meaning |
|---|---|
| **PASS** | the checker ran and found nothing |
| **FAIL** | the checker ran and found a violation of an `error`-severity rule — exit code 1 |
| **WARN** | same, but the rule is `warn` severity — reported, exit code unchanged |
| **SKIP** | the checker **did not run** — never counted as a pass |

Below the table, a second section:

```
Not checked (2) — asserted in invariants.md, verified by nobody:
  CFG-001  tier 'prose': recorded as documentation, not enforced
  INT-004  no v1 generator for INTERFACE/contract/python
```

**Read that section every time.** A row there is a rule someone wrote down and nothing is enforcing. It
is not a failure — a `prose` row is a deliberate choice — but it is the gap between what your artifact
claims and what your build actually holds you to.

This distinction is load-bearing. An artifact whose rules were all `prose` tier once produced an empty
table and the line *"All invariants hold"* — while two of its eight rules were false. A run that checked
nothing must not look like a run that passed.

## Writing a rule that catches something

The single most useful habit: **verify a new rule by breaking the code on purpose.**

1. Write the row with `Status: proposed`.
2. `archagent gen` — confirm it appears under a checker and not under *skipped*.
3. Introduce the violation the rule exists to prevent. One line, in a scratch edit.
4. `archagent check` — confirm it **fails**, and that the message points at what you just did.
5. Revert, re-run, confirm it passes. Promote to `Status: active`.

A rule promoted without step 3 may be vacuous — scoped to a module set that is empty, or a pattern that
matches nothing — and a vacuous rule is worse than no rule, because it reports a passing state it never
tested. Every invariant in archagent's own table was verified this way.

`/archagent-invariant` walks an agent through the same loop.

## Rules nothing can check yet

Most architectural intent is not mechanically checkable, and pretending otherwise loses it. Record it
anyway, with **Tier `prose`**:

```
| CFG-001 | STRUCTURAL | prose | python | only the config layer reads the environment | error | [0005](…) | proposed | `rg -n "os.environ" --glob "!app/config.py"` | needs a scoped ast-grep pattern |
```

The row lives in the table, stays greppable, and is reported under *Not checked* on every run. Two
optional columns matter most here:

- **`Verification`** — the test, command or audit that does confirm it. `none` is a legitimate answer and
  more useful than a blank, because without it "archagent cannot generate a checker for this" and "nobody
  checks this at all" look identical.
- **`Graduation path`** — what would make it mechanical, or that nothing would.

`archagent scan-invariants` finds rules your docs and code already state — `INVARIANT:` markers, assertion
messages, and modal prose like "must never" or "only X may" — as candidates to lift into the table. Most
of them start as `prose` rows.

## Automation

### On every commit

```bash
archagent install-hook              # native .git/hooks/pre-commit, idempotent
archagent install-hook --skip-pbt   # static tiers only; leave the property tests to your suite
```

The hook composes with an existing pre-commit hook rather than replacing it. `--skip-pbt` is the usual
choice: the static tiers run in well under a second on most repositories, and property tests belong in
the test run.

### In CI

`check` exits 1 on an error-severity failure, so it needs no wrapper:

```yaml
- run: archagent check
```

This repository does exactly that, alongside two more gates:

```yaml
- run: archagent check
- run: archagent drift --exit-code      # the documents still match the code
- run: archagent lint-docs --exit-code  # diagrams parse, cited invariant IDs exist
```

The second is stricter than most projects need — `drift` is informational by design and its output is a
work-list. It gates here because this repository's artifact is offered as the worked example.

### In your test suite

A test that runs `check` against your own repo gives a contributor the failure before they push rather
than after a round trip:

```python
from archagent.check import run_checks
from archagent.config import load_config
from archagent.generate import generate
from archagent.invariants import parse_invariants

def test_the_architecture_holds():
    config = load_config(ROOT)
    invariants = parse_invariants(config.invariants_path)
    assert invariants, "an empty table would make this assertion vacuous"
    gen = generate(invariants, config)
    results = run_checks(invariants, config, gen.importlinter_ids, gen.depcruiser_ids,
                         gen.astgrep_ids, gen.pbt_ids)
    assert not [r for r in results if r.skipped_reason]      # nothing silently unchecked
    assert not [r for r in results if not r.passed and r.severity == "error"]
```

Note the first assertion. Asserting only on failures passes on a build where the checkers stopped running
— see `tests/test_self.py` in this repository, which exists because a real boundary violation once left
the suite green while `check` reported it.

## When a check is wrong

A failing check is a claim about your code, and it can be the claim that is wrong. Three honest responses,
in the order worth trying:

1. **The code is wrong.** Fix it. This is the common case, and it is the point.
2. **The rule is wrong.** Change the row and record why in its ADR. A rule that no longer describes the
   intended design should not survive because changing it feels like cheating.
3. **The rule is right but this case is a deliberate exception.** Narrow the scope — `outside <scope>` is
   usually how — and put the exception in the ADR. An unexplained narrowing is indistinguishable from
   giving up.

What not to do is widen a rule until it stops firing without recording why. That leaves a row that looks
enforced, passes every run, and protects nothing.

If a rule fires on code you believe is correct and none of the three fits, the check may be scoping wrong.
`archagent modules` shows how each Python file resolves to an import module and flags top-level name
collisions, which is the usual cause of a BOUNDARY rule behaving strangely.

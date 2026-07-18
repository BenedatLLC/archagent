# archagent: invariant — add or change an architectural invariant

Add (or modify) a row in `architecture/invariants.md` and confirm it works.

## Steps
1. Decide the **Type** (BOUNDARY, INTERFACE, DATAFLOW, STRUCTURAL, PURPOSE) and the cheapest **Tier**
   that can catch it (structural → contract → pbt → model-check).
2. Write the **Rule** in the compact DSL:
   - `forbid <a> -> <b>` (BOUNDARY)
   - `forbid-pattern <ast-grep pattern> [in|outside <scope>]` (STRUCTURAL) — `in <scope>` flags only
     there; `outside <scope>` flags everywhere except there ("only `<scope>` may do this"). `<scope>`
     is a path/glob or a dotted module.
   - `property <path::test>` (PBT — behavioral/data invariants). The target's file extension picks the
     framework: a `.py` target scaffolds a Hypothesis `@given` stub, a JS/TS target a **fast-check**
     `fc.property` stub. **Write the property yourself** (it needs system knowledge) — a preserved-invariant
     or model/round-trip check; the property IS the spec. Needs the language's `test_command`
     (`[python]` e.g. `uv run pytest`, `[ts]` e.g. `npx vitest run`) so `check` can run it.
   - `property stateful <path::TestCase>` (PBT — **stateful** systems: state machines, stores,
     lifecycles). `gen` scaffolds a Hypothesis `RuleBasedStateMachine` (Python) or a fast-check
     `fc.commands` model-based stub (JS/TS): model operations as commands/rules that get composed into
     random sequences, and assert what must always hold after each. The right tool for state/data-layer
     invariants a single property can't catch (e.g. "state resets on error", "writes reflected in reads").
3. Add the row: ID, Type, Tier, Applies-to (language), Rule, Severity, Why (link an ADR), Status.
   **Note on enforcement:** a row with a real `forbid` / `forbid-pattern` Rule is generated and checked
   regardless of Status (except `deprecated`); the only Tier that suppresses generation is `prose`. To park
   a rule you can't enforce yet, set Tier `prose` (documented, never run) — not Status `proposed`, which is
   still enforced.
4. Write or extend the ADR in `decisions/` explaining what the invariant prevents and why it matters.
5. Run `archagent check`. Confirm it PASSES on current clean code, and (sanity-check) that it would FAIL
   on a deliberate violation. Refine the rule until it catches the right thing.

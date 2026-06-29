# archagent: check — enforce the architecture and resolve violations

Make the code adhere to the described architecture.

## Steps
1. Run `archagent check`.
2. For each **FAIL** (error severity): read the invariant and its linked ADR (`Why`). Then either
   - fix the code to comply (preferred), or
   - if the invariant is genuinely wrong or outdated, change it in `architecture/invariants.md` and
     record the reason in a new ADR under `architecture/decisions/`.
   Never silently suppress or work around a failing invariant.
3. For each **WARN**: note it; fix if cheap, otherwise leave for follow-up.
4. Re-run `archagent check` until it is clean (exit 0).
5. If you changed the architecture, update `architecture/index.md` and append to `architecture/log.md`.

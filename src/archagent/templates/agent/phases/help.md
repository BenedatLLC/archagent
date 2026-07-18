# archagent: help — the lifecycle and what to run at each step

When the user asks for help, or how archagent works, or what to do next, give them this concise map and
then point them at the specific step they need. archagent runs a **reflexion loop** over the architecture:
describe the intended design → check & diff it against the code → evaluate its health → update. Set up
once, then cycle at design-review time and per-commit.

## The steps

| Step | Run | What it does |
|------|-----|--------------|
| Set up | `archagent init` | scaffold `architecture/` + install the agent skills (once per repo) |
| 1. Describe | `/archagent-describe` | document the architecture — build the first time, **update** thereafter |
| 2. Add rules | `/archagent-invariant` | add a checkable invariant (or edit `architecture/invariants.md`) |
| 3. Enforce | `archagent check` · `/archagent-check` | run the checkers, report pass/fail per invariant |
| 4. Diff | `archagent drift` | where the docs and code have diverged — the update work-list |
| 5. Evaluate | `archagent evaluate` · `/archagent-evaluate` | system-level architecture smells + recommended fixes |
| 6. Update | `/archagent-describe` | reconcile the artifact from the drift + evaluate output; record ADRs |
| Maintain | `archagent upgrade` | refresh the installed skills/prompts to the latest |

## Notes
- **Cadence:** run `check` on every commit; run `describe` + `evaluate` at design-review time and periodically.
- `archagent gen` regenerates the checker configs (`check` does this for you). Any command takes `--help`.
- The artifact format is specified in `docs/ADL-SPEC.md`; planned work is in `docs/ROADMAP.md`.
- The same overview is available from the CLI as `archagent help`.

Don't run anything as part of answering — just orient the user and point to the right next step.

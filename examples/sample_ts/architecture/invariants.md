# System Invariants (TypeScript sample)

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-010 | BOUNDARY | structural | ts | `forbid src/domain -> src/ui` | error | [0003](decisions/0003-layers.md) | active |
| STR-011 | STRUCTURAL | structural | ts | `forbid-pattern eval($$$)` | error | [0004](decisions/0004-no-eval.md) | active |

**BND-010** keeps domain logic from importing the UI layer.
**STR-011** forbids `eval` anywhere in the TypeScript sources.

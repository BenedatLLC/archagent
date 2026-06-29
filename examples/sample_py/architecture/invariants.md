# System Invariants

The single source of truth for archagent. The first table below is parsed; the prose
around it is for humans. Rule details and rationale live in the linked decisions.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-001 | BOUNDARY | structural | python | `forbid app.domain -> app.web` | error | [0007](decisions/0007-hexagonal.md) | active |
| STR-002 | STRUCTURAL | structural | python | `forbid-pattern print($$$) in src/app/domain` | warn | [0009](decisions/0009-no-io-in-domain.md) | active |

**BND-001** keeps the domain layer free of web concerns (a hexagonal boundary).
**STR-002** flags `print()` as a stand-in for "the domain layer does no direct I/O".

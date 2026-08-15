# Invariants

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-001 | BOUNDARY | prose | python | `forbid app.models -> app.api` | error | data layer must not depend on the HTTP layer | active |

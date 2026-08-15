# Invariants

Almost every row here is `prose` tier, and the reason is worth stating: the properties that actually
matter in this codebase are *dependency-injection shapes* ("a mutating route declares `CurrentUser`") and
*container ordering* ("the API starts after migrations"). Neither is a dependency edge or a code pattern,
so the DSL cannot express them. `archagent check` reports prose rows under **Not checked** rather than as
passing, which is the honest rendering.

| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |
|----|------|------|-----------|------|----------|-----|--------|
| BND-001 | BOUNDARY | structural | python | `forbid app.models -> app.api` | error | the data model must not depend on the HTTP layer | active |
| BND-002 | BOUNDARY | structural | python | `forbid app.core.security -> app.crud, app.api` | error | hashing and signing sit below everything | active |
| HTTP-001 | STRUCTURAL | prose | python | a route that mutates data declares `CurrentUser` or stricter | error | authorisation is a parameter type (`api/deps.py:30`, `:52`) | active |
| DOM-001 | STRUCTURAL | prose | python | a password reaches the database only through `crud.create_user` | error | one hashing path; `core/db.py:33` uses it rather than inserting directly | active |
| CORE-001 | STRUCTURAL | prose | python | the environment is read in `core/config.py` and nowhere else | error | one configuration surface | active |
| CORE-002 | BOUNDARY | prose | python | `forbid app.core -> app.crud` | warn | **currently violated** at `core/db.py:3`, deliberately — see `subsystems/backend-core.md` | proposed |
| CLIENT-001 | STRUCTURAL | prose | typescript | nothing under `frontend/src/client/` is hand-edited | error | it is generated; an edit survives until the next `generate-client` | active |
| APP-001 | STRUCTURAL | prose | typescript | no component calls `fetch` directly | warn | all backend access goes through the generated SDK | active |
| OPS-001 | STRUCTURAL | prose | — | the API does not start before migrations run | error | expressed by compose service ordering, not by code | active |

## Rules deliberately not written as invariants

**"The generated client matches the backend schema."** The strongest property in the system and not
checkable from the source tree: it holds only if `scripts/generate-client.sh` was run after the last route
change. A CI step that regenerates and fails on a non-empty diff is the right enforcement, and it belongs
in the build rather than in this table.

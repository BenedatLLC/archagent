# backend-tests — the pytest suite

**Covers:** `backend/tests/**/*.py`
**Tier:** infra
**Service:** backend
**Connects:** backend-http via import, backend-domain via import, backend-core via import, backend-ops via import

## Purpose

Documented as a subsystem rather than excluded, because it is in the configured source set and because the
fixtures encode contracts the production code relies on.

## Topology and components

| Directory | What it tests |
|---|---|
| `tests/api/routes/` | one module per router — items, login, private, users |
| `tests/crud/` | the persistence operations |
| `tests/scripts/` | the pre-start polling scripts |
| `tests/utils/` | factories that create users and items for the others |
| `conftest.py` | the session and client fixtures every test depends on |

## Key abstractions

**The fixtures decide what "authenticated" means in a test.** `conftest.py` builds a `TestClient` with a
superuser token, so a route test exercises the dependency ladder in `api/deps.py` rather than bypassing
it. A test that passes has therefore also exercised the authorisation path, which is why there are no
separate auth tests for most routes.

**`tests/utils/` is a factory, not a helper grab-bag.** `user.py` and `item.py` create realistic rows
through the same `crud` functions the API uses, so a test never inserts a differently-shaped row than
production would.

## Invariants

- TEST-001 (proposed) — a fixture creates data through `crud`, not by direct insert, so tests cannot pass
  against rows the application could never produce.

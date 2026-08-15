# backend-core — configuration, engine, hashing

**Covers:** `backend/app/core/**/*.py`
**Tier:** infra
**Service:** backend
**Connects:** backend-domain via import

## Purpose

The three things every other backend module needs: settings, the SQLAlchemy engine, and password
hashing plus JWT signing.

## Topology and components

| File | Job |
|---|---|
| `config.py` | a Pydantic `Settings` object read from the environment |
| `db.py` | the engine, and `init_db` which seeds the first superuser |
| `security.py` | password hashing and JWT creation |

## The layering exception

**`core/db.py:3` imports `crud`, which is the one upward dependency in the backend.** `init_db` seeds the
first superuser and does it by calling `crud.create_user` (`:33`) rather than inserting a row, so the
seeded account gets the same hashing and validation as any other. Infrastructure therefore depends on
domain logic.

The trade is deliberate and the alternative is worse — a second creation path would be a second place for
password handling to drift. It is recorded here rather than hidden because it is exactly the edge a
layering check will flag, and a reader should find the reason next to the finding.

## State and tiering

The engine is module-level (`db.py:6`), so one connection pool serves the process.

## Invariants

- CORE-001 (proposed) — settings are read from the environment in `config.py` and nowhere else.
- CORE-002 — `core` should not import upward. **Currently violated** by `db.py:3`, deliberately; see
  above. Recorded as a known exception rather than as a rule that holds.

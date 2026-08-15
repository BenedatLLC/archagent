# backend-domain — models, persistence operations, and email

**Covers:** `backend/app/crud.py`, `backend/app/models.py`, `backend/app/utils.py`
**Tier:** domain
**Service:** backend
**Connects:** backend-core via import

## Purpose

The data model and the operations over it. `models.py` holds the SQLModel table definitions and the
request/response schemas; `crud.py` holds the handful of functions that create and read them; `utils.py`
renders and sends the email templates.

## Key abstractions

**One module defines both the table and the wire schema.** SQLModel lets `User` be the ORM row and
`UserCreate`/`UserPublic` be the API shapes in the same file. That is why there is no separate
serialisation layer, and why a column rename is a single-file change that then propagates to the frontend
through the generated client (see `constitution.md`).

**`crud.py` is deliberately thin.** It exists so that password hashing happens in exactly one place —
`create_user` is the only path that writes a `hashed_password`, and `core/db.py:33` calls it rather than
inserting a row directly, which is why the seeded superuser is hashed the same way every other user is.

## State and tiering

Postgres, reached through the session injected by `backend-http`. This subsystem opens no connections
itself.

## Invariants

- DOM-001 (proposed) — a password must reach the database only through `crud.create_user`. True at
  `0.9.0`; not mechanically checked.

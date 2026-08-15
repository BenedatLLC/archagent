# Deployment

## Runtime shape

Five services in `docker-compose.yml`, plus two named volumes/networks:

| Service | What it is |
|---|---|
| `db` | Postgres, the only stateful component |
| `prestart` | runs to completion before `backend` starts: waits for `db`, applies Alembic migrations, seeds the superuser |
| `backend` | the FastAPI app |
| `frontend` | the built React bundle, served statically |
| `adminer` | a database console, for development |

`docker-compose.traefik.yml` adds the public proxy; `docker-compose.override.yml` carries the local
development wiring.

**`prestart` is the interesting one.** It is not a long-running service — it exists so that ordering is
expressed in compose rather than in application code, which is why `main.py` has no readiness check.

## Configuration

**Config:** `PROJECT_NAME`, `ENVIRONMENT`, `SECRET_KEY`, `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`,
`POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`BACKEND_CORS_ORIGINS`, `FRONTEND_HOST`, `SENTRY_DSN`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`,
`EMAILS_FROM_EMAIL`, `VITE_API_URL`

All backend keys are read by the Pydantic `Settings` object in `core/config.py` and nowhere else, so the
configuration surface is one class rather than scattered `os.getenv` calls.

**`archagent drift` reports every key above as "declared but not read in code", and that finding is
false.** Its config scanner matches `os.getenv` and `process.env`; this file contains neither, because
`class Settings(BaseSettings)` (`core/config.py:26`) declares configuration as typed class attributes that
pydantic-settings populates from the environment. The scanner cannot see them, so it concludes nothing
reads them. Do not "fix" this by deleting accurate declarations. `VITE_API_URL` is the
frontend's only one, consumed at `frontend/src/main.tsx:16`.

**`ENVIRONMENT` changes what exists, not just how it behaves.** `api/main.py:13` mounts `private.router`
only when it is `local`, and `main.py:14` initialises Sentry only when it is not. A deployed API is a
strict subset of a local one.

## Trust boundary

The backend's CORS list comes from `BACKEND_CORS_ORIGINS` plus `FRONTEND_HOST`, passed at `main.py:25`
together with `allow_credentials=True`. There is no wildcard, and there could not be: browsers refuse `*`
when credentials are sent. `allow_methods` and `allow_headers` *are* `["*"]`, which is broad but only
within origins that already passed the list check.

## External dependencies

| Dependency | Needed for | If absent |
|---|---|---|
| Postgres | everything | `prestart` blocks; the API never starts |
| SMTP | password recovery and new-account email | those flows fail; the rest works |
| Sentry | error reporting | not initialised unless `SENTRY_DSN` is set and `ENVIRONMENT != local` |

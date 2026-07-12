# Deployment & Configuration

How the system is deployed and configured. Keep this honest — `archagent drift` checks the
**Configuration** section against the code today; the **Deployment** view is descriptive for now.

## Deployment view

What runs where: processes/services, their runtimes/containers, and the external infrastructure they
depend on (datastores, queues, third-party APIs). One line per unit; note how they're wired.

- _e.g._ `web` (container, gunicorn) → Postgres, Redis
- _e.g._ `worker` (container) → Redis, S3

Source of truth: `docker-compose.yml` / k8s manifests / `Procfile` / `serverless.yml` as applicable.

## Configuration

**Config:** DOC_HOME, DATABASE_URL, OPENAI_API_KEY
<!-- The environment keys the system needs. `archagent drift` flags keys read in code but not listed
     here (undocumented) and keys listed but never read (dangling). A committed `.env.example` counts
     as a manifest too. -->

- **Access boundary.** Read configuration in one place, not scattered through the code. Enforce it with
  an invariant, e.g. `forbid-pattern os.getenv($$$) outside <config module>` (Python) or the
  `process.env` equivalent (JS/TS).
- **Secrets.** No credentials in source or in this repo. Scan with a dedicated tool (e.g. gitleaks) in CI.
- **Per-environment.** Note which keys differ by environment (dev/staging/prod) and any that are required.

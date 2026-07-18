# Deployment & Configuration

How the system is deployed and configured. Keep this honest — `archagent drift` checks the
**Configuration** section against the code today; the **Deployment** view is descriptive for now.

## Deployment view

**Services:** web, worker
<!-- The services/processes the system deploys. `archagent drift` flags services found in IaC
     (docker-compose / Procfile / k8s) but not listed here, and listed-but-missing ones.
     SINGLE-PROCESS APP? If this is a CLI, a library, or one process with no docker-compose/Procfile/k8s,
     DELETE this **Services:** line and describe the runtime in prose below — a declared service with no
     IaC is reported as dangling forever. Only keep **Services:** when there is real service topology. -->

What runs where: processes/services, their runtimes/containers, and the external infrastructure they
depend on (datastores, queues, third-party APIs). One line per unit; note how they're wired.

- _server app, e.g._ `web` (container, gunicorn) → Postgres, Redis · `worker` (container) → Redis, S3
- _single-process app, e.g._ one `cli` process (installed console script) → local files, a vector store;
  no service topology, so no `**Services:**` line — this prose is the deployment view.

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

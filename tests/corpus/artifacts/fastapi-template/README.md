# Minimal artifact for the `fastapi-template` corpus entry

Groups A, B and B/C read `**Service:**`, `**Tier:**` and `**Connects:**` from subsystem documents. No
corpus repository had an artifact, so those families were *structurally* unable to fire — adding a
service-shaped repository alone did not change that (issue #9).

This is the smallest artifact that makes them fire: metadata only, no narrative. It is copied into the
worktree before `evaluate` runs.

**It is written by us, not generated, and that is a bias worth naming.** Declaring the architecture is
declaring what the layering signals will compare against, so these findings are not evidence that
archagent describes this system correctly. The corpus asks *"did the output change?"* and never *"is the
output right?"*, and this artifact is only ever an input to the first question.

The declarations are read off the repository at `0.9.0`: five compose services, a FastAPI backend calling
Postgres, and a React frontend calling the backend over HTTP.

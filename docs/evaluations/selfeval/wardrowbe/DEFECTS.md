# Defects the round-3 reviewers found in the wardrowbe artifact

Two reviewers, one human and one blind model judge, on `architecture/` at `wardrowbe-v1.7.0`. Every
finding below was verified against the code by me before being listed. The artifact is left unfixed —
it is evidence, and re-scoring this revision has to be against the same text.

The point of this document is the last column. **A defect that only ever afflicts this artifact is worth
one fix; a defect archagent could have prevented is worth a rule.**

## Factual errors — mine, specific to this artifact

Found by the judge, all five verified. None generalise: they are wrong sentences, not a wrong process.
What they share is worth noting though — every one is a claim I made *in passing* rather than one I set
out to establish, which is the round-3 lesson in miniature.

| # | Claim | Reality |
|---|---|---|
| 1 | "`models/schedule.py` with no matching schema… no public write path" | `ScheduleCreate` at `schemas/notification.py:134`, `POST /schedules` at `api/notifications.py:245` |
| 2 | "eight SQLAlchemy tables" | 19 `__tablename__` declarations |
| 3 | `add_ai_job_id_to_items.py` "lets the API report tagging progress without asking Redis" | `tagging-progress` groups by `ClothingItem.status` in Postgres (`api/items.py:540`) |
| 4 | `validate_security()` "logs rather than raises" (said twice, framed as a virtue) | raises `RuntimeError` (`config.py:124`, `:132`) |
| 5 | "falls back to local auth (`settings.get_auth_mode()`)" | returns `oidc` / `dev` / `unknown` (`config.py:146-151`); no such mode |
| 6 | the services table lists seventeen services | `outfit_service.py` is absent from it |
| 7 | tagging diagram draws `stale → queued: swept and requeued` | `worker.py:40-41` sets `status=error` and stops |

## Generalizable — and what was done about each

| # | Defect | Generalises as | Status |
|---|---|---|---|
| 8 | **`SVC-001` marked `active` while `api/preferences.py:134` violates it** | **Second occurrence** — obstudio's `SKILL-002` was the first. A prose row cannot be checked, so `active` on one is a claim nobody verified. | **Fixed in the tool.** `check` now reports prose rows marked `active` whose `Why` cites nothing, under *Asserted active with no recorded evidence*. Both historical cases had rationale-only `Why` columns and would have been caught. |
| 9 | Five subsystem docs have no diagram; three have a *relational* subject and need one — 19 tables with no ER diagram, a two-node import cycle described only in prose, a "Topology" section that is a table | A document whose subject is a set of **relationships** needs a picture; prose about directionality is where a reader gives up. | **Prompt rule added.** |
| 10 | `backend-domain.md` calls `ItemStatus` "the contract between the API and the worker" without saying what its values are | Naming something a contract and not enumerating it. *Both* reviewers hit this: the human criticised the omission and then named the states wrongly (`pending, processing, done, error, abandoned` against the real `processing, ready, error, archived`). | **Prompt rule added.** |
| 11 | The generated system map has no caption | `archagent graph --write` emits a diagram and no caption slot, so the artifact's most prominent picture is the one most likely to be uncaptioned — while the prompt requires analytical captions everywhere else. | **Filed.** |
| 12 | No invariant covers per-user data ownership, which is hand-scoped at every call site (`item_service.get_by_id(item_id, current_user.id)`) | For any multi-user system, "where is ownership enforced, and what happens if a call site forgets" is a question the six dimensions never ask. | **Prompt rule added.** |
| 13 | `POST /test-ai-endpoint` fetches a **user-supplied URL** server-side (`api/preferences.py:119`, `:137`), with scheme validation only | SSRF shape: a static pattern, recognisable in any language, and exactly the class `permissive-origin` occupies. | **Filed as a new signal.** |
| 14 | `WEB-001` says "no *component* constructs a backend URL" while `frontend/lib/auth.ts:103` does | A rule scoped by a word that does not match a directory. The wording passes while the property fails. | Recorded; no general fix — this is what a reviewer is for. |
| 15 | `WRK-002` ("a job writes a terminal status or is sweepable") is unfalsifiable as written | Already covered by the existing vacuity guidance; the new evidence check flags it too. | Covered by #8's fix. |

## Coverage gaps, artifact-specific

Authentication end-to-end is never described — five auth routes, `utils/oidc.py` and the NextAuth handler
appear only as fragments. Background removal, the mobile-callback flow, `GZipMiddleware`, and the
family-sharing access model are each one list entry. All real, all fixed by writing more; none says
anything about archagent.

## The pattern across three rounds

Both security-relevant findings in this project's history came from the **model judge** and from neither
the human nor me: obstudio's wide-open CORS, and this round's SSRF-shaped route. Two out of two. That is
the strongest argument the calibration rounds have produced for the two-reader rule — not that either
reader is better, but that the one who walks the tree systematically finds a category the one who samples
never reaches.

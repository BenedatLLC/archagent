# Judged rubric, calibration round 3 (2026-08-15) — wardrowbe

Second agreement measurement. Target: [Anyesh/wardrowbe](https://github.com/Anyesh/wardrowbe) at
`wardrowbe-v1.7.0` — chosen against the freshness criteria `fastapi-template` failed, and the first target
on which every `evaluate` signal family is active.

Reviews and parsed records are in the data repo. The judge saw the brief, the artifact and the code, ran
after the human had finished, and had no access to their scores. No defect was fixed in between.

## Agreement

| criterion | human | judge | diff |
|---|---|---|---|
| accuracy | 5 | 3 | **−2** |
| completeness | 3 | 3 | 0 |
| prose | 5 | 4 | −1 |
| diagrams | 4 | 3 | −1 |
| invariant_strength | 4 | 3 | −1 |
| invariant_criticality | 4 | 3 | −1 |
| **mean** | **4.17** | **3.17** | **−1.00** |

Exact agreement **1/6 (17%)**, within one point **5/6 (83%)**.

Alongside round 2 (obstudio): exact 2/6, within-one 6/6, gap −0.33. Two rounds is not a trend, but the
direction has repeated — **the judge scored lower on every criterion where they differed, in both
rounds.** That is now four times out of four for `prose`, `diagrams`, `invariant_strength` and
`invariant_criticality`.

## The result that matters: sampling five claims found nothing

The human scored `accuracy` **5** — "every claim sampled holds exactly as stated" — and the five sampled
claims *do* all hold. I re-checked them: the same-origin proxy, the `services ↔ utils` cycle, the
`settings.debug` gating, the derived stale-job cutoff, the stripped hop-by-hop headers. Five for five.

The judge scored `accuracy` **3** and produced five contradicted claims. I verified every one against the
code:

| Artifact claim | Reality |
|---|---|
| "`models/schedule.py` with no matching schema… a table with no public write path" | `ScheduleCreate` exists at `schemas/notification.py:134`, and `POST /schedules` at `api/notifications.py:245` |
| "eight SQLAlchemy tables" | **19** `__tablename__` declarations |
| `add_ai_job_id_to_items.py` "is what lets the API report tagging progress without asking Redis" | `tagging-progress` groups by `ClothingItem.status` in Postgres (`api/items.py:540`); the job id is not involved |
| `validate_security()` "**logs** rather than raises… starts and complains loudly" — said twice | it **raises `RuntimeError`** (`config.py:124`, `:132`) |
| "falls back to local auth (`settings.get_auth_mode()`)" | `get_auth_mode()` returns `oidc` / `dev` / `unknown` (`config.py:146-151`); there is no local-auth mode |

Plus three more the judge found and I confirmed: the tagging diagram draws `stale → queued: swept and
requeued` where `worker.py:40-41` sets `status=error` and stops; `outfit_service.py` is missing from a
table claiming seventeen services; and `SVC-001` is marked `active` while `api/preferences.py:134` calls
an AI endpoint straight from a route handler.

**Both reviewers were diligent and both were evidenced. The difference is method.** Sampling the
headline claims tests the claims the author stated most carefully — which are the ones most likely to be
right. Walking the artifact against the tree tests the claims the author made in passing, which is where
the errors were: a table count taken from a file listing, a schema inferred from a directory, a startup
behaviour recalled rather than read.

The lesson is not that the human was careless. It is that **"pick the five most load-carrying claims" —
the wording of the `accuracy` criterion itself — selects against finding errors**, because load-bearing
claims get checked while writing and incidental ones do not. The criterion needs to ask for coverage, not
for importance.

## The failure class recurred a third time, in my own artifact and in the review

"Falls back to local auth (`settings.get_auth_mode()`)" cites the correct function and describes a mode
it does not have. That is the third round running for this shape:

- round 1: `HTTP-001` cited `handler.go:75-92` to prove only POSTs mutate, with `DELETE` at `:93`
- round 2: the human's `diagrams` 5 cited `manager.go:68` as starting a run; it only marks staleness
- round 3: my `deployment.md` cites `get_auth_mode()` for a mode it never returns — **and** the human's
  `completeness` names `ItemStatus` as `pending, processing, done, error, abandoned` where the enum is
  `processing, ready, error, archived` (`pending` belongs to `TaggingStatus`; `done` and `abandoned` exist
  nowhere)

Six instances across three rounds, in artifacts and in reviews, by every participant. The citation
resolves; the recalled contents do not match. Nothing mechanical catches it, which is the entire argument
for §14's checklists putting the ground truth *in* the checklist rather than asking a reader to recall it.

## What the judge found that nobody else did

`api/preferences.py` exposes `POST /test-ai-endpoint`, which fetches a **user-supplied URL** server-side.
There is URL-scheme validation (`"Only HTTP and HTTPS URLs are allowed"`) and no further restriction, so
the shape is SSRF: a caller can point it at an internal address the backend can reach and the frontend
cannot. The artifact documents the route and says nothing about the exposure, and no invariant covers it.

Neither the human nor I found this. Round 2's judge found the equivalent (a wide-open CORS policy). **That
is twice out of two that the strongest security-relevant finding came from the model judge**, and it is
the clearest argument yet for the two-reader rule rather than for either reader alone.

## Instrument failures

The parser could not read this review either — it put the score in the criterion heading
(`## accuracy — Score: 5`) rather than in a `score:` field, so all six criteria were skipped. **Two of
three real reviews have now been lost to formatting**, each for a different reason, each with sound
content. Fixed by reading a heading score when no field score is present; a field still wins where both
exist.

Also fixed: `Next.js` was reported as an invented citation, because it ends in `.js`.

## Limits

- Two rounds, one human, one judge, six criteria. The repeated direction of the gap is suggestive and
  nothing more.
- The judge and the human did not use identical inputs for `prose`: `writing-style.md` is not in the
  wardrowbe checkout, and both said so and substituted.
- I wrote the artifact under review and verified the judge's findings myself. The verification is
  reproducible from the citations above; the choice of what to verify is not independent of me.
- The judge withdrew one finding after checking it — it expected a default `SECRET_KEY` to be unguarded
  in production and found the code stricter than its own documentation claimed. Worth recording as
  evidence that it was checking rather than accumulating.

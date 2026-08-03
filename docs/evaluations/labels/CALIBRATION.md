# Calibration round 1 (2026-08-01) — the first independent labels

19 group-F findings from the pinned corpus, labelled by a reviewer who did not build the checks, with the
tool's severity and confidence withheld until after each verdict. This is the first evidence about
archagent's output that is not my own judgement.

## Precision by signal

| signal | n | confirm | partial | dismiss | strict | 95% CI | lenient | 95% CI |
|---|---|---|---|---|---|---|---|---|
| scattered-source-of-truth | 9 | 8 | 0 | 1 | **89%** | [0.56, 0.98] | 89% | [0.56, 0.98] |
| enum-value-escape | 10 | 6 | 3 | 1 | **60%** | [0.31, 0.83] | 90% | [0.60, 0.98] |

*Strict* counts only full confirmations. *Lenient* credits **partial** — "something real is here, but not
what the finding claims", e.g. the escape exists but from a different enum than the one named. Reporting
one number would hide that the enum signal is usually pointing at something true while frequently
mis-attributing it.

**`partial` was not an anticipated verdict.** The reviewer reached for it unprompted on 3 of 10 enum
items, and the original parser dropped unrecognised verdicts silently — so the most informative labels in
the set were nearly lost. Fixed; `partial` is now first-class.

## Agreement with my own labels: 13/19 (68%)

The number this exercise existed to produce. My labels came from the evaluation pass, where I labelled,
tuned thresholds against those labels, and then graded the result.

| # | finding | mine | theirs | who was right |
|---|---|---|---|---|
| 3 | `ImageGenerationRequestQuality` | dismiss | partial | theirs — I called it a pure word collision; some sites really are the enum's own domain used as literals |
| 9 | `integrations` metadata cluster | **dismiss** | **confirm** | **theirs, clearly** — I dismissed it as an incoherent grab-bag without investigating. It is a genuine scattered source of truth: one helper duplicated verbatim in three places and bypassed by ~30 hand-rolled loops that have *diverged on key order*, so a request carrying both keys resolves differently depending on which module looks |
| 10 | `DataResidency` `{eu, us}` | **confirm** | **dismiss** | **theirs** — `AllowedModelRegion` is a different concept that merely shares two strings; the enum's real consumer uses it correctly |
| 16 | `ServiceTier` | ambiguous | partial | theirs — the escape is real but from `ServiceTierBlock`, not the enum named |
| 17 | oauth `{S256, authorization_code, code}` | **confirm** | **dismiss** | **theirs** — RFC-frozen wire constants (RFC 6749/7636). They cannot drift, a typo fails loudly, and inline is the industry standard |
| 18 | `_Action` `{BLOCKED, …}` | confirm | partial | theirs — three independent vendor vocabularies sharing AWS Bedrock's strings; the real gap is elsewhere |

**I was wrong in both directions.** Three findings I confirmed are dismissible (10, 17, and partly 18),
and one I dismissed is real (9). A biased labeller does not simply grade generously — the errors go both
ways and cancel in aggregate, which is exactly why the headline precision looked plausible.

Item 9 is the one that should change how the checks are used. I dismissed it from the value set alone
("mixed concepts — grab-bag") without opening the files. The reviewer opened them and found the strongest
finding in the set. **A verdict reached from the finding's summary is not a verdict.**

## What this says about the earlier numbers

The evaluation pass reported 71% precision for scattered-source-of-truth and 84% for enum escapes. On this
subset the independent numbers are 89% and 60%/90%. The direction differs per signal and the intervals are
wide at n≈10, so the honest reading is: **the earlier figures were not reliable, and these replace them
for this subset.** They are not a correction of a small error; they were produced by a process with no
independent signal in it.

## Limits

- 19 items, one reviewer. Wilson intervals span roughly ±25 points.
- One repository dominates: 17 of 19 findings are litellm's.
- `change-prone-file` was deliberately excluded — the defect study already gives it independent evidence.
- This calibrates **findings**, not the artifact rubric, and not a model judge. Agreement with a model
  judge needs judge verdicts over the same items; these labels are the ground truth that would make that
  measurement mean something.

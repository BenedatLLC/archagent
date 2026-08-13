# Judged rubric, calibration round 2 (2026-08-12) — obstudio

Two independent scorings of the same artifact: a human reviewer and a blind model judge, on
`docs/architecture/` for [signalfx/obstudio](https://github.com/signalfx/obstudio) at `88aebe8` — a
repository neither of them wrote, and which I described. **This is the first agreement number the judged
rubric has produced.** Round 1 could not produce one: it had a single reviewer whose citations turned out
to be fabricated, and an instrument that discarded five of six scores before measuring anything
(`../archagent/CALIBRATION.md`).

Reviews: `review-brief-2026-08-02.md` (human) and `review-judge-2026-08-12.md` (judge), with parsed records
`judged-*.json`, all in the data repo. The judge saw the brief, the artifact and the code, and nothing else
— no access to the human's scores, and it ran after the human had finished so the artifact was identical
for both. No defect was fixed in between, deliberately.

## Agreement

| criterion | human | judge | diff |
|---|---|---|---|
| accuracy | 3 | 3 | 0 |
| completeness | 3 | 4 | +1 |
| prose | 5 | 4 | −1 |
| diagrams | 5 | 4 | −1 |
| invariant_strength | 4 | 4 | 0 |
| invariant_criticality | 4 | 3 | −1 |
| **mean** | **4.00** | **3.67** | **−0.33** |

**Exact agreement 2/6 (33%). Within one point 6/6 (100%).** With n=6 and one artifact, none of this is a
precision estimate; treat it as a first reading with a wide interval, not a number to quote.

Two things are worth more than the headline:

**They agree exactly where the evidence is hardest and diverge where it is softest.** `accuracy` (3/3) and
`invariant_strength` (4/4) both require opening the code and checking claim by claim; both matched.
`prose` and `diagrams` — the two most interpretive criteria — are where they split, and in the same
direction. That is the pattern anchored descriptors are supposed to suppress, and they only partly did.

**The judge scored lower on every criterion where they differed.** A −0.33 mean gap over six criteria is
one reviewer being consistently stricter, not noise in both directions. Whether that is the judge being
harsh or the human being generous is answered below, and the answer is not the flattering one.

## Both scorings were evidenced. Only one was exhaustive.

Neither review had a fabricated citation — the round-1 failure did not recur. The judge resolved ~331 line
references; the only non-resolving strings were `writing-style.md`, which it flagged itself as absent from
the checkout (it judged prose against a copy outside the repo and said so).

But the judge found six defects the human did not, and I verified every one against the code:

| finding | verified |
|---|---|
| `DELETE /api/data` (`api/handler.go:93`) is undescribed, and **CLI-001 and HTTP-001 are both false** because of it | yes |
| **SKILL-002 is marked `active` / "Currently held" and is violated** by four per-skill scripts totalling ~2,616 lines of real logic (`scan_python_otel_topology.py` 83, `validate_gap_closure.py` 712, `validate_reader_report.py` 599, `validate_configure_output.py` 1222) | yes |
| **CLI-001 violated**: `api/handler.go:41`, `:72`, `:73` construct `validator.NewStore`, `validator.NewService`, `dashboards.NewResolver` | yes |
| the artifact says "64 Go files under `observer/`" twice; `observer/` has **57** — 64 is the repo-wide count including the `evals/` fixtures the artifact explicitly excludes | yes |
| `Store` is described as "behind one `sync.Mutex`"; it is a `sync.RWMutex` plus `subMu`, `invalidateMu`, `changeMu` (`store.go:313-332`) | yes |
| `Access-Control-Allow-Origin: *` (`api/handler.go:283`) with an unconditional WebSocket `CheckOrigin` (`websocket.go:21`) lets any page the developer browses read their telemetry and call the destructive route | yes |

The last is the strongest finding of the round and **neither the human nor I found it**. The artifact leans
repeatedly on "local by default, which is the product", and local does not mean unreachable: a browser tab
on any site can issue those requests. No invariant covers it and the "deliberately not written" section
does not name it.

The SKILL-002 error is the one that should have been caught by me. I read `observe_report.py` — a genuine
32-line shim — and generalised to all per-skill scripts without opening the other four. It is Python, which
archagent *does* analyse, so it was the most checkable claim in the table and I asserted it instead.

## The finding that matters for the rubric itself

The human scored `diagrams` **5** — "verified nine diagrams against actual code" — and wrote, of the
validator state machine:

> logical states map to code — idle→running via Run() or change callback at `manager.go:68`

`manager.go:68` is:

```go
func (m *Manager) MarkTelemetryChanged(changedAt time.Time) {
    m.store.MarkTelemetryChanged(changedAt)
}
```

It marks the store stale. It does not start a run. The diagram's `idle → running: Run() or telemetry
changed`, `running → cancelled: new telemetry arrives mid-run` and `cancelled → running: restart against
the new snapshot` edges are wrong — runs begin only on an explicit `Service.Run`, cancellation reaches
`cancelActiveRun` only through `Reset`, and nothing restarts automatically. The judge caught it; the human
cited the correct line and drew the opposite conclusion from it.

So the round produced the same lesson at both levels:

- In the **artifact**: `HTTP-001` cites `api/handler.go:75-92` to prove only POSTs mutate state, while
  `DELETE /api/data` sits at `:93`. The range stops one line short of its own counterexample.
- In the **review**: a citation resolves, is quoted accurately, and supports the opposite of what it says.

`../archagent/CALIBRATION.md` predicted exactly this — "*this does not catch a citation that resolves but
does not support the claim, and nothing mechanical will*" — as a known limit of the resolution check. It
occurred twice in the next round, once in the artifact and once in a review, and in both cases the person
writing was confident. **Resolution-checking raises the floor and does not touch the ceiling.** The only
thing that caught either was a second reader.

## What this says about using a model judge

On this evidence the judge is usable for the code-checking criteria and is the stricter reader: it agreed
with the human exactly where claims are verifiable, and everywhere it disagreed it was lower — because it
had found defects the human had not. That is a better result for the judge than for the rubric, and it
does not license replacing the human with it. One artifact, one judge, six criteria.

Practical reading, pending more rounds:

- **Two readers, not one.** Every serious defect in this round was found by exactly one of the two. Neither
  scoring alone would have produced the list above.
- **The judge earns its place on `accuracy` / `completeness` / `invariant_*`.** Those are the criteria it
  matched or beat the human on, and the ones a reader is most likely to answer from the documents alone.
- **`prose` and `diagrams` remain unresolved.** They are where the two split, and the split is not random:
  the human rated both 5 while holding a mistaken verification of a diagram edge. A high interpretive score
  can rest on a check that did not hold.
- **Scores still gate nothing** (design §13.2), and both records carry that caveat.

## Limits

- One artifact, one human, one judge, six criteria. Exact agreement of 33% on n=6 has an interval so wide
  it is barely a measurement; the within-one-point figure is the more meaningful of the two.
- The human and the judge did not use identical inputs for `prose`: `writing-style.md` is not in the
  obstudio checkout, and the judge substituted a copy from elsewhere and said so.
- The judge ran ~95 minutes and 51 tool calls. Cost is not free, and nothing here establishes that a
  cheaper judge would agree.
- I wrote the artifact under review, and I verified the judge's findings against the code myself. The
  verification is reproducible from the citations in the table above; the judgement of which findings
  matter is not independent of me.

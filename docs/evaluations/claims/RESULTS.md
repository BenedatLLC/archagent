# Computed claims — step 1 (2026-08-16)

Step 1 of `docs/designs/computed-claims.md` §8, run against the two unrepaired artifacts.

**The pre-registered prediction was at least 17 divergences. The result is 8. The gate says stop, and
steps 2 and 3 should not be run as the design currently stands.**

The reason it came in low is more useful than the number, and it points at a specific different design.

## Result

| | obstudio @ `88aebe8` | wardrowbe @ `v1.7.0` | total |
|---|---|---|---|
| claims written | 13 | 21 | **34** |
| agreed with the code | 9 | 17 | 26 |
| **diverged** | **4** | **4** | **8** |
| facts left uncomputed under the safety rules | 12 | 10 | **22** |

The eight divergences:

| claim | artifact says | code says | previously known? |
|---|---|---|---|
| obstudio Go files under `observer/` | 64 | 57 | yes — round 2, defect 6 |
| obstudio state-changing HTTP routes | 3 | 4 | yes — round 2, defect 3 (HTTP-001) |
| obstudio locks guarding the store | 1 | 4 | yes — round 2, defect 7 |
| obstudio skills shipped | 8 | 9 | **no — new** |
| wardrowbe backend Python files | 65 | 125 | yes — noise-floor replicate |
| wardrowbe SQLAlchemy tables | 8 | 19 | yes — round 3, defect 2 |
| wardrowbe schema modules | 7 | 6 | yes — round 3 (approximately; see below) |
| wardrowbe Kubernetes manifests | 10 | 11 | **no — new** |

**Two of the eight had never been found**, by four reviewers across two rounds and eight checklist
judgings: `skills/` ships nine skills where an invariant's rationale says eight, and `k8s/` holds eleven
manifests where `deployment.md` enumerates ten (it omits `namespace.yaml`). Both took seconds and no judge.

## Why 8 and not 17

The §3 evidence classified 17 of 28 confirmed defects as *facts a deterministic command could settle*.
That classification was correct. **It was the wrong question.**

A claims table only catches a defect when the artifact **commits to a value**. Most of the 17 are facts a
command could establish, which the artifact stated as prose behaviour rather than as a number:

| defect | a command could settle it | but the artifact said |
|---|---|---|
| `validate_security` logs rather than raises | `rg 'raise RuntimeError' config.py` → 2 | "logs rather than raises" — no value |
| falls back to local auth | `rg -A6 'def get_auth_mode'` → three modes | "falls back to local auth" — no value |
| stale jobs are requeued | `rg 'status=ItemStatus' worker.py` | a diagram edge |
| the UI is embedded by `cmd/obstudio/embed.go` | `rg 'go:embed'` → two directives | *which* file, not *how many* |
| the services table lists seventeen | `ls services/` → 17 | the count was right; the **table** omitted one |
| per-skill scripts are shims | `wc -l` → 2,616 lines | "shims" — a judgement |

The mechanism as designed asks *does this recorded number still hold*. Most fabricated claims are not
numbers. **A claim would have to be a predicate — "`validate_security` raises" — with a command whose exit
status or output settles it, not only a value with a command that reproduces it.** That is a different
design, and predicting its yield is a new pre-registration, not a reinterpretation of this one.

## The finding that matters more than the count

I wrote 37 commands. **Ten of them measured something other than what the prose meant** — a 27% authoring
error rate, and 56% of the divergences on the first pass were false:

| what the command did | what the prose meant |
|---|---|
| counted `.d.ts` files | the artifact's 117 excludes declarations |
| counted volume names as compose services | five services, three volumes, both two-space indented |
| counted `os.Getenv` in `_test.go` | three production sites |
| counted directories under `skills/` | `references/` is not a skill |
| `wc -l file` printed the filename beside the count | the number alone |
| counted every `.py`/`.ts` in the repo | the paths `archagent.toml` configures |
| took "~19 routes" and "several migrations" as counts | a hedge is not a claim |

**In this retrospective those errors were loud, and in production every one of them would be silent.**
Here the recorded value came from the prose, so a wrong command produced a visible mismatch. In the real
workflow the recorded value comes *from the command*, so a command that measures the wrong thing records a
plausible number, agrees with itself forever, and lends a fabricated claim the appearance of verification.

That is §5.1's risk, measured: it is not a hypothetical, it happened in 27% of first attempts, and it was
caught only because a human already knew the answer. The mitigation in the design — store the output
rather than the bare count, so a reviewer can see what the command measured — would have caught roughly
half of them (the `.d.ts`, volumes, `_test.go`, `references/` and `wc` cases all show themselves the
moment the output is visible). It would not have caught the configured-paths one.

## What the safety rules cost

**22 facts could not be expressed as a command** — about 39% of the assertions extracted. They divide
cleanly, and the division is the same one §3 predicted:

- **Needs an import graph** (5) — package cycles, "the only composition root", "the leaf every package
  depends on". `evaluate` already computes these; a claims table is the wrong tool.
- **A property of every code path** (7) — "a run that could not execute reports a failure kind", "no
  component constructs a backend URL", "the browser never talks to the backend".
- **A reason or a judgement** (6) — "the proxy is a route handler *because* rewrites are baked at build
  time", "where the product's complexity lives", "shims".
- **A claim about another tool's output** (2) — "`archagent drift` reports 13 undocumented routes".
- **A hedge** (2) — "~148 source files", "several are hand-named".

**None was refused by the safety rules themselves.** Only one command was ever rejected by static
validation for a safety reason (`observer/../extension/src/...` leaving the target root), and it was
rewritten in seconds. The allowlist did not bite. **The rules of §5.4 are close to free** — that question
is answered, and answered favourably.

## Two prototype defects worth carrying into any implementation

- **Splitting the command on `|` breaks regex alternation.** `rg -o '@router\.(get|post|delete)'` is one
  stage, not three, and the first version reported `post` and `delete` as disallowed tools. Splitting has
  to be quote-aware; nothing else distinguishes a pipeline separator from an alternation.
- **The path-escaping check misfires on regexes.** `rg '/add_[a-z_]+\.py$'` starts with `/` and is not a
  path. An argument is only a path if it has no regex metacharacters.

## Recommendation

**Do not proceed to steps 2 and 3 as specified.** The gate was pre-registered and it was not met.

Two things are worth deciding separately, and neither is settled by this result:

1. **Predicate claims** — the design change the "why 8" analysis points at. It would reach a much larger
   share of the recorded defects, and it needs its own prediction before anything is built.
2. **The 27% authoring error rate is the real risk and it is independent of which design is chosen.** Any
   version of this mechanism records agent-written commands whose correctness nobody re-derives. Storing
   command *output* rather than a bare count is the cheapest available mitigation and should be a
   requirement, not a suggestion, in whatever is built.

The two new defects argue the mechanism has value even at this yield. They cost seconds and no judge, and
they are exactly the kind of small factual error that a human reviewer's attention never reaches.

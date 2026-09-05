# extraction — the static scanners

**Covers:** `src/archagent/fetchscan.py`, `src/archagent/originscan.py`, `src/archagent/configscan.py`, `src/archagent/deployscan.py`, `src/archagent/webapi.py`, `src/archagent/datamap.py`, `src/archagent/connscan.py`, `src/archagent/obsscan.py`, `src/archagent/invscan.py`, `src/archagent/mdutil.py`, `src/archagent/tiers.py`, `src/archagent/coverage.py`, `src/archagent/version.py`
**Tier:** infra
**Connects:** config via import, drift via import

## Purpose

Pull verifiable facts out of a codebase without running it. Each scanner answers one narrow question and
returns data; none of them judges.

| Module | Fact extracted |
|---|---|
| `tiers.py` | the `**Tier:**` vocabulary: which tokens name a layer, and which say *not a layer* |
| `configscan.py` | environment keys the code reads — `os.getenv` / `process.env` / `import.meta.env`, helper wrappers, and pydantic-settings fields |
| `deployscan.py` | services declared in docker-compose / k8s / Procfile, and the env keys those files consume |
| `webapi.py` | HTTP routes, from the code or an OpenAPI spec |
| `datamap.py` | table definitions and datastore touch points |
| `connscan.py` | outbound calls whose target resolves to a known service |
| `obsscan.py` | tracing / correlation-id instrumentation |
| `originscan.py` | permissive cross-origin policy, and state-changing route registrations |
| `fetchscan.py` | a route that fetches a URL the caller supplied, and what guarded it |
| `invscan.py` | invariants already *stated* in prose or asserts, as candidates |
| `mdutil.py` | markdown helpers (fence stripping, empty-value detection) |
| `coverage.py` | what an extractor could not see — sites seen vs sites resolved |
| `version.py` | the running build's version, as a leaf anything may read |

## What a scanner actually returns

"Extracts environment keys" describes a shape, not a result. Three scanners, each shown as the code it
reads and the fact it hands back:

**`configscan`** — given `os.getenv("DATABASE_URL", "sqlite://")` anywhere in the source set,
`read_config_keys` returns the bare set `{"DATABASE_URL", ...}`. Deliberately a set of names and not a
map to locations: its only consumer compares it against `declared_config_keys`, the keys named under
`**Config:**` in `deployment.md`. A key read but never declared is drift; a key declared but never read is
dead configuration.

A literal `os.getenv` is only one of three ways a real codebase reads the environment, and finding only
that spelling produces the worst available result: a short list that looks like a complete one. So
`configscan` also resolves **helper wrappers** — a function whose body reads `os.environ` and whose callers
pass the key — and **pydantic-settings** classes, where the key is a field name, an `env_prefix` and an
alias rather than a string literal anywhere. On one reviewed repository the literal-only scan found 98
keys and the full scan found 228.

Two constraints keep that from over-reaching. The wrapper rule requires the receiver to be `os.environ`
itself; accepting any `.get(param)` made every `dict.get` in the codebase look like an env wrapper and
dragged in names like `Document` and `Checksum`. And test paths are skipped, because a repository's own
test fixtures set environment keys that are not part of its configuration surface.

**The configuration surface has two halves, and scanning one of them looks like scanning both.**
`read_config_keys` covers the configured `source_paths`, which is where application code lives and is
precisely where deployment configuration does not. So `deployment_config_keys` asks the same question of
the compose files, Dockerfiles and k8s manifests `deployscan` already opens — a key consumed there is
read, just not by application code.

Issue #24 is the measurement: wardrowbe reported 24 declared-but-unread keys, every one correct and none
of them a defect. `BACKEND_PORT` appears only in a compose *port mapping*, so a structural scan of
`environment:` blocks would still have missed it — the raw text is scanned for `${VAR}` interpolation as
well, because interpolation anywhere in the file is a read. After the fix that list is 2, and both are
real: one key appears nowhere at all, and the other is `OIDC_ISSUER` where everything else says
`OIDC_ISSUER_URL`. That near-miss was invisible among two dozen correct ones, which is the argument for
the change — a signal buried is a signal lost.

The scan is deliberately narrow. `env:` is read as a Kubernetes key only in its list-of-`{name, value}`
form, so a GitHub Actions `env:` mapping does not pull CI variables into the configuration surface; and
`${tag}` and `$ID` are rejected on the conventional shape of an environment name, or every template
placeholder in every compose file would qualify.

**A key a process *writes* is configuration too** (issue #29). obstudio's TypeScript extension does
`env.WEAVER_PATH = weaver` and builds an `env: { … }` object for the Go binary it spawns; the reader is
invisible because archagent does not parse Go, but the writer is right there, and both keys were reported
as declared-but-never-read. A write is arguably better evidence than a read — whoever wrote it knew the
name mattered.

The object form is anchored on `env:` and **brace-matched**, not on the launcher call with a fixed
window: obstudio's block is fourteen keys and the one that mattered sat past any reasonable distance from
the `spawn(`, while a window wide enough to reach it would sweep in whatever followed. `{ FOO: bar }` on
its own is a dictionary; the `env:` label is what makes this specific rather than a hunt for shouting
keys.

**`webapi`** — given `@app.get("/orders/{order_id}")`, `extract_routes` returns
`Route(method="GET", path="orders/{}")`, keeping the original string in `raw` and the file in `source`.
The normalisation is the interesting part: parameter names are erased and surrounding slashes stripped
*because* the comparison is against an OpenAPI spec or another framework's spelling of the same route,
and `/orders/{id}` and `/orders/{order_id}` are the same endpoint. Only `method` and `path` take part in
equality (`webapi.py:38-44`).

**`invscan`** — given `assert user.is_authenticated, "only signed-in users may post"` in production
code, it returns a `Candidate` carrying that message, `path:line`, `kind="assertion"`,
`confidence="low"`, and a coarse guess at which DSL tier it belongs in. An explicit
`INVARIANT`/`@invariant` marker returns `kind="marker"`, `confidence="high"` instead, and the noisier
`kind="modal"` pass — "must never", "only X may" — runs over documents only, because modal words in code
are too common to be worth surfacing.

The marker/assertion split is not cosmetic. The same assert in a *test* file yields nothing at all: there
the message is the test's own failure text, and conflating the two put `response`, `123, 456` and
`Transfer-Encoding` at the top of httpx's report under a "high confidence" heading. Even the high tier is
only confidence that a marker was *found* — never that what it states is architectural. These are
candidates a person classifies and verifies, never facts.

The pattern holds for all eight: a file set in, typed facts out, and the value is in what the fact can be
compared against rather than in the fact itself.

## Key abstractions

**`coverage.py` exists so an extractor can say it saw nothing.** Every scanner here returns *facts*, and
the failure mode of a scanner is not a wrong fact but a short list — a wrong source path, an ignored
glob, a timed-out walk, each producing a smaller true-looking answer. `Coverage` counts candidate sites
alongside resolved ones, and **refuses to call `seen == 0` sound** unless the caller has declared that an
empty repository is a legitimate answer for that scanner. The refusal is the point: the first prototype
of the import counter reported `0 of 0` over an empty file set on its first run, committing the exact
error it was written to detect, and a shared type is the only reason the next one will not.

**`version.py` is a leaf because reading a version should not be an upward dependency.** `graph.py`
stamps the tool version into a generated map; `from . import __version__` made `reporting` (domain)
import the package root, which the model groups with `cli` (ui). The inversion was real and its substance
was false — what `graph` needs is the version, not the command line. Surfaced by the import coverage
counter, which found those two imports unresolved and so revealed a missing edge, which in turn revealed
the modelling problem behind it.

**`tiers.py` is a leaf, and that is the whole reason it exists.** `evaluate` needs the layer ranks to find
inversions and `drift` needs them to notice a subsystem claiming a layer it has no business on — and
`evaluate` already imports `drift`, so putting the vocabulary in either would have closed a second cycle
on top of the one ADR 0003 records. It imports nothing internal, which is what makes it usable from
anywhere. `tier_of` had accumulated three copies (`evaluate`, `graph`, and nearly `drift`) before the move
— the duplicated decision this tool's own `scattered-source-of-truth` check exists to find.

It also carries **tokens meaning *not a layer*** — `test`, `migration`, `ops` and friends. An unrecognised
token was already skipped by the layering check, so recognising these changes no behaviour on its own;
what it buys is telling *the author said this is off the ladder* apart from *the author typed `domian`*.
Issue #26: four of seven labelled `layer-inversion` findings came from test and migration packages tiered
`infra`, the bottom rank, so everything they imported read as upward.

**Regex and AST, never execution.** "Static" here means no import of the target code, so scanning a
repository can never run it.

**The dangerous spelling is not the obvious one.** `originscan` looks for a wildcard origin, but also for
the header *echoing the request's own `Origin` back* — which is more permissive than `*`, because browsers
reject a wildcard when credentials are sent, so reflection is the form that actually allows a cross-origin
read of an authenticated response. It contains no star, so a wildcard-only scan sees nothing.

**`originscan` is the one scanner not bound to the configured languages.** Every other extractor needs a
parser and so only sees `languages` from `archagent.toml`; this one is a literal search for a handful of
spellings that works the same anywhere. It reads Go, which archagent otherwise cannot analyse — which is
the point, because the finding that prompted it was in Go and a scanner blind to that case would be worth
nothing. Weaker evidence than a parse, so it is used only to *raise* a finding's severity, never lower it.

**`fetchscan` is the only scanner that follows a value rather than matching one.** It tracks request
input to an outbound HTTP call — Python via `ast` within a single function, JS/TS via regex within a file
that looks like a request handler, which is the same split the rest of the tool uses. Anything routed
through a helper is missed, so a clean result is not a clearance, and it says so.

**The question it really answers is "does the caller choose the host".** Not "is caller input in the URL"
— every proxy builds `f"{base}{path}"` from configuration and a request path, and reporting those would
make the signal useless. Only a tainted value at the *front* of a URL controls the destination, and that
property has to travel with a name through assignment or a proxy reads as an SSRF the moment the URL is
bound to a variable.

Five false-positive classes are pinned as tests, because a taint check that fires on everything is worse
than none: `self` is a parameter and tainted every method on every class; an f-string's literal text is
not a variable reference; an ORM `session.delete(item)` shares its verbs with an HTTP client; a fixed base
with a caller-supplied path is a proxy; and a React component fetching a prop issues that request from the
*user's* browser, which has none of the server's network position.

**A wrapped declaration is still one declaration.** `configscan`'s `**Config:**` pattern runs to the next
blank line or `**Field:**`, not to the end of its first line. A real manifest is a long list of keys and
whoever writes it wraps it; reading only the first line silently honours part of the declaration and
reports the rest as undeclared — a confident, wrong finding against a document that does declare them.

**"Is this build configuration?" is the second shared path predicate, for the same reason.**
`is_build_config` matches `*.config.{js,ts,mjs}` and `*.d.ts`. `described` held that rule privately and
`_mistiered` needed the same answer without having it — so wardrowbe's test subsystem, covering twelve
tests and five config files, could not be recognised as non-production. It kept a `**Tier:** infra` it
should never have had, everything it imported read as upward, and that produced a false `layer-inversion`
finding on the signal whose measured precision is 43%.

Across the four recorded artifacts exactly one subsystem changes verdict under the wider predicate: the
one it was written for. That number is worth having, because the failure mode of loosening this check is
calling a production subsystem non-production, which would invert it into a new false-positive source.

**"Is this a test path?" is one question with one answer here — and three others elsewhere.**
`configscan.is_test_path` is public because `drift` uses it to decide what is exempt from documentation
and `evaluate` uses it to decide which reading of a hard-coded endpoint applies; a second definition would
be a second behaviour, and the two commands would disagree about the same file. Three further definitions
do still exist (`described.py`, `originscan.py` inline twice, `hotspots.py`) with **three different
directory sets** — `e2e/` is test code to one and not the others — which is the scattered-source-of-truth
shape this tool's own group F looks for, recorded as issue #32 rather than quietly unified, because some
of the divergence is legitimate and the interesting question is why `dupdecide` did not report it.

**Every scanner can say what it could not read, and each does it exactly.** `configscan` counts an env
read whose key is not a literal, `datamap` a table declaration whose name is computed, `webapi` a route
decorator whose path is an expression. In each case the shape is recognised and the *value* is not — a
fact about the scan rather than a guess about the code, which is what makes the number safe to print
without hedging it.

`webapi` draws the line explicitly: a verb-named decorator whose first argument is a literal that does
not start with `/` is not counted at all. `@cache.get("key")` is not a route, and counting it would turn
a fact about what could be read into a guess about what the code is.

The lookahead in those patterns sits *before* the whitespace. `=\s*(?!["'])` matches
`__tablename__ = "orders"` anyway — the engine backtracks `\s*` to zero characters, looks ahead at the
space and succeeds. Written the wrong way round twice: once here, and once years earlier in
`_ENV_READ_ANY`, where it over-counted padded literal reads as opaque and went unnoticed while the number
stayed internal.

**Conservative by design.** `connscan` drops a call whose target it cannot resolve rather than guessing;
`datamap` requires a real table definition. A scanner that guesses produces findings nobody can act on.

**Detection confidence is not truth confidence.** `invscan` separates a *labelled* invariant — someone
wrote `INVARIANT` — from an *assertion message*, which is whatever text explains a failure. They were one
tier called "high confidence", and on httpx that put `response`, `123, 456` and `Transfer-Encoding` at
the top of the report, because in a test the message after the comma is the test's own failure text
rather than a stated rule.

So assertion messages are dropped in test paths and demoted elsewhere, while an explicit marker keeps its
standing everywhere including tests — the same treatment `hardcoded-endpoint` gives a test file, and for
the same reason: re-read rather than skip. The heading no longer claims high confidence at all, since
what the scanner is confident about is having found a marker, never that the marker states an
architectural rule.

**`invscan` is the odd one out.** It extracts *candidates* for the invariants table rather than facts —
`INVARIANT:` markers, asserts, and modal prose ("must never", "only X may") — which a person then
classifies and verifies before promoting.

## State and tiering

Read-only over the working tree. Most of these are leaves; `invscan.py:24` imports `_source_files` from
`drift`, and that single edge is what closes the `drift ↔ extraction` cycle recorded in ADR 0003.
`connscan` imports `configscan` alone and is not part of it.

## Lifecycles / key flows

None. Each scanner is a pure function from a file set to facts.

## Invariants

None specific. These modules are depended on, so their signatures are the contract.

# extraction — the static scanners

**Covers:** `src/archagent/fetchscan.py`, `src/archagent/originscan.py`, `src/archagent/configscan.py`, `src/archagent/deployscan.py`, `src/archagent/webapi.py`, `src/archagent/datamap.py`, `src/archagent/connscan.py`, `src/archagent/obsscan.py`, `src/archagent/invscan.py`, `src/archagent/mdutil.py`, `src/archagent/tiers.py`
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

**`webapi`** — given `@app.get("/orders/{order_id}")`, `extract_routes` returns
`Route(method="GET", path="orders/{}")`, keeping the original string in `raw` and the file in `source`.
The normalisation is the interesting part: parameter names are erased and surrounding slashes stripped
*because* the comparison is against an OpenAPI spec or another framework's spelling of the same route,
and `/orders/{id}` and `/orders/{order_id}` are the same endpoint. Only `method` and `path` take part in
equality (`webapi.py:38-44`).

**`invscan`** — given `assert user.is_authenticated, "only signed-in users may post"`, it returns a
`Candidate` carrying that message, `path:line`, `kind="marker"`, `confidence="high"`, and a coarse guess
at which DSL tier it belongs in. In code it matches only explicit `INVARIANT`/`@invariant` markers and
assertion messages; the noisier `kind="modal"` pass — "must never", "only X may" — runs over documents
only, because modal words in code are too common to be worth surfacing. Even so these are *candidates* a
person classifies and verifies, never facts.

The pattern holds for all eight: a file set in, typed facts out, and the value is in what the fact can be
compared against rather than in the fact itself.

## Key abstractions

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

**Conservative by design.** `connscan` drops a call whose target it cannot resolve rather than guessing;
`datamap` requires a real table definition. A scanner that guesses produces findings nobody can act on.

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

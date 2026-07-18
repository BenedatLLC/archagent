"""Connector-kind inference from code (static) — the "else inferred" half of connector typing.

Where `**Connects:**` declares the *intended* connector kind, this infers the *actual* kind from the code
so the connector signals work without annotation and, more valuably, so `drift` can flag where the code
contradicts the declaration (a declared `async-event` that is really a blocking HTTP call — the doc claims
a decoupling the code doesn't have). This is Wright's port-role conformance check, done lightweightly.

Conservative by design: it resolves a call target two ways — a literal host in an HTTP client call, or a
config-driven endpoint (an `*_URL`/`*_ENDPOINT`-shaped env key whose base name resolves to a service, in a
file that makes HTTP calls) — and drops any target it can't resolve to a known subsystem/service name; it
never guesses. Still invisible to a static scan: non-env variable/constant URLs, base-URL client objects,
dynamic dispatch, gRPC stubs, and async producer↔consumer pairing — so inferred edges are always
lower-confidence than declared ones, and those forms are deferred (Tier B).
"""

from __future__ import annotations

import re
from pathlib import Path

from .configscan import _ENV_READS

# a synchronous HTTP/RPC client call, capturing the first string-literal argument (the URL)
_SYNC_CALL = re.compile(
    r"""(?:requests|httpx|session|client|http)\s*\.\s*(?:get|post|put|patch|delete|head|request)\s*\(\s*f?['"]([^'"]+)['"]"""
    r"""|(?:fetch)\s*\(\s*[`'"]([^`'"]+)[`'"]"""
    r"""|axios\s*(?:\.\s*(?:get|post|put|patch|delete))?\s*\(\s*[`'"]([^`'"]+)[`'"]"""
    r"""|got\s*(?:\.\s*(?:get|post|put|delete))?\s*\(\s*[`'"]([^`'"]+)[`'"]""",
    re.IGNORECASE,
)
# any HTTP/RPC client call, literal argument or not (the gate for config-driven endpoint inference)
_HTTP_CALL = re.compile(
    r"(?:requests|httpx|session|client|http)\s*\.\s*(?:get|post|put|patch|delete|head|request)\s*\("
    r"|(?:fetch|got)\s*\("
    r"|axios\s*(?:\.\s*(?:get|post|put|patch|delete))?\s*\(",
    re.IGNORECASE,
)
# a publish / enqueue — an asynchronous event emission (target intentionally not resolved: Tier B)
_ASYNC_PUB = re.compile(
    r"\.\s*(?:publish|apply_async|delay)\s*\(|KafkaProducer|\bcelery\b|\.\s*send_task\s*\(",
    re.IGNORECASE,
)
_SCHEME_HOST = re.compile(r"[a-z][a-z0-9+.-]*://([^/\s'\"`]+)", re.IGNORECASE)
# trailing tokens that mark an env key as an *endpoint* (BILLING_URL, ORDERS_SERVICE_ENDPOINT, …)
_ENDPOINT_SUFFIX = {"URL", "URI", "ENDPOINT", "HOST", "ADDR", "ADDRESS", "SERVICE", "BASE", "SVC"}


def sync_call_targets(root: Path, rel: str, names: set[str]) -> set[str]:
    """Subsystem/service names this file synchronously calls, resolved from either a literal host in an
    HTTP call *or* a config-driven endpoint env key (`BILLING_URL` → `billing`). The env-key route only
    counts when the file actually makes an HTTP client call, so a plain config read isn't mistaken for one."""
    text = _read(root, rel)
    if text is None:
        return set()
    targets: set[str] = set()
    for h in _literal_hosts(text):
        r = resolve_host(h, names)
        if r:
            targets.add(r)
    if _HTTP_CALL.search(text):  # config-driven endpoints, only in a file that makes HTTP calls
        for key in _env_keys(text):
            base = _endpoint_base(key)
            if base:
                r = resolve_host(base, names)
                if r:
                    targets.add(r)
    return targets


def sync_call_hosts(root: Path, rel: str) -> set[str]:
    """URL hosts of hard-coded synchronous HTTP/RPC calls in this file (empty if none/unreadable)."""
    text = _read(root, rel)
    return _literal_hosts(text) if text is not None else set()


def _literal_hosts(text: str) -> set[str]:
    hosts: set[str] = set()
    for m in _SYNC_CALL.finditer(text):
        h = _host(next((g for g in m.groups() if g), ""))
        if h:
            hosts.add(h)
    return hosts


def _env_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for pat in _ENV_READS:
        keys.update(pat.findall(text))
    return keys


def _endpoint_base(key: str) -> str | None:
    """The service-name base of an *endpoint-shaped* env key (`BILLING_URL` → `billing`,
    `ORDERS_SERVICE_ENDPOINT` → `orders`), or None if the key doesn't look like an endpoint."""
    toks = key.upper().split("_")
    stripped = False
    while len(toks) > 1 and toks[-1] in _ENDPOINT_SUFFIX:
        toks.pop()
        stripped = True
    return "-".join(toks).lower() if stripped else None


def emits_events(root: Path, rel: str) -> bool:
    """Whether this file publishes/enqueues an asynchronous message."""
    text = _read(root, rel)
    return text is not None and bool(_ASYNC_PUB.search(text))


def resolve_host(host: str, names: set[str]) -> str | None:
    """Match a URL host to a known subsystem/service `name`, or None. Conservative: exact, suffix-stripped
    (`billing-svc` ~ `billing`), or full-token-subset match — never a loose substring."""
    if not host:
        return None
    hostbase = host.split(":")[0].split(".")[0].lower().replace("_", "-")
    htoks = set(hostbase.split("-"))
    fallback: str | None = None
    for name in names:
        n = name.lower().replace("_", "-")
        if hostbase == n or _strip(hostbase) == _strip(n):
            return name
        ntoks = set(n.split("-"))
        if ntoks and ntoks <= htoks:  # every token of the name appears in the host
            fallback = name
    return fallback


def _strip(s: str) -> str:
    return re.sub(r"-(svc|service|api)$", "", s)


def _host(url: str) -> str | None:
    m = _SCHEME_HOST.match(url)
    return m.group(1).split(":")[0].lower() if m else None  # relative URLs have no resolvable host


def _read(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text()
    except OSError:
        return None

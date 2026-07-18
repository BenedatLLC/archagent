"""Connector-kind inference from code (static) — the "else inferred" half of connector typing.

Where `**Connects:**` declares the *intended* connector kind, this infers the *actual* kind from the code
so the connector signals work without annotation and, more valuably, so `drift` can flag where the code
contradicts the declaration (a declared `async-event` that is really a blocking HTTP call — the doc claims
a decoupling the code doesn't have). This is Wright's port-role conformance check, done lightweightly.

Conservative by design: it captures only *literal* outbound calls (a hard-coded host in an HTTP client
call, or a publish/enqueue) and drops any target it can't resolve to a known subsystem/service name — it
never guesses. Config-driven endpoints, variable URLs, dynamic dispatch, and gRPC stubs are invisible to a
static scan, so inferred edges are always lower-confidence than declared ones (Tier A only; async
producer↔consumer pairing is deferred).
"""

from __future__ import annotations

import re
from pathlib import Path

# a synchronous HTTP/RPC client call, capturing the first string-literal argument (the URL)
_SYNC_CALL = re.compile(
    r"""(?:requests|httpx|session|client|http)\s*\.\s*(?:get|post|put|patch|delete|head|request)\s*\(\s*f?['"]([^'"]+)['"]"""
    r"""|(?:fetch)\s*\(\s*[`'"]([^`'"]+)[`'"]"""
    r"""|axios\s*(?:\.\s*(?:get|post|put|patch|delete))?\s*\(\s*[`'"]([^`'"]+)[`'"]"""
    r"""|got\s*(?:\.\s*(?:get|post|put|delete))?\s*\(\s*[`'"]([^`'"]+)[`'"]""",
    re.IGNORECASE,
)
# a publish / enqueue — an asynchronous event emission (target intentionally not resolved: Tier B)
_ASYNC_PUB = re.compile(
    r"\.\s*(?:publish|apply_async|delay)\s*\(|KafkaProducer|\bcelery\b|\.\s*send_task\s*\(",
    re.IGNORECASE,
)
_SCHEME_HOST = re.compile(r"[a-z][a-z0-9+.-]*://([^/\s'\"`]+)", re.IGNORECASE)


def sync_call_hosts(root: Path, rel: str) -> set[str]:
    """URL hosts of hard-coded synchronous HTTP/RPC calls in this file (empty if none/unreadable)."""
    text = _read(root, rel)
    if text is None:
        return set()
    hosts: set[str] = set()
    for m in _SYNC_CALL.finditer(text):
        url = next((g for g in m.groups() if g), "")
        h = _host(url)
        if h:
            hosts.add(h)
    return hosts


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

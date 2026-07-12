"""Observability markers (static) — the input for `evaluate`'s cross-boundary tracing signal.

The system-level observability question is: when a request crosses a service boundary, can you follow
it? That needs a trace/correlation context propagated across calls. We can't prove propagation
statically, but we can detect the two things whose *combination* reveals a blind spot: a service that
makes **cross-service calls** (HTTP client, message publish) but carries no **tracing/correlation
marker** anywhere (an OpenTelemetry/Sentry/structlog import, or a correlation-id header). `evaluate`
aggregates these to the service level.

Conservative on purpose: over-matching a marker only makes us *quieter* (fewer blind-spot claims), which
is the safe direction for a smell detector.
"""

from __future__ import annotations

import re
from pathlib import Path

# tracing / correlation instrumentation — an import or a correlation-id header/context
_OBSERVABILITY = re.compile(
    r"opentelemetry|opentracing|ddtrace|jaeger|zipkin|elastic[_-]?apm|sentry_sdk|newrelic"
    r"|structlog|\bMDC\b|traceparent|x-request-id|x-correlation-id|x-trace-id"
    r"|correlation[_-]?id|request[_-]?id|trace[_-]?id",
    re.IGNORECASE,
)

# outbound cross-service communication — an HTTP client call or a message publish
_OUTBOUND = re.compile(
    r"\brequests\.(?:get|post|put|patch|delete|request)\b|\bhttpx\.|\baiohttp\b"
    r"|urllib\.request|http\.client|\bfetch\(|\baxios\.|\bgot\("
    r"|\.publish\(|\.apply_async\(|\.delay\(|\bkafka|\bboto3",
    re.IGNORECASE,
)


def scan(root: Path, rel: str) -> tuple[bool, bool]:
    """Return (has_observability_marker, makes_outbound_call) for one file."""
    try:
        text = (root / rel).read_text()
    except OSError:
        return (False, False)
    return (bool(_OBSERVABILITY.search(text)), bool(_OUTBOUND.search(text)))

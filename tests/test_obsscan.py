"""archagent obsscan — static observability markers (input for evaluate's tracing signal)."""

from archagent.obsscan import scan


def _w(tmp, rel, text):
    (tmp / rel).write_text(text)
    return rel


def test_detects_tracing_and_outbound(tmp_path):
    _w(tmp_path, "a.py", 'import opentelemetry\nimport requests\nr = requests.get("http://svc/x")\n')
    assert scan(tmp_path, "a.py") == (True, True)


def test_outbound_without_tracing(tmp_path):
    _w(tmp_path, "b.py", 'import httpx\nr = httpx.get("http://svc/x")\n')
    assert scan(tmp_path, "b.py") == (False, True)


def test_correlation_header_counts_as_observability(tmp_path):
    _w(tmp_path, "c.js", "const id = req.headers['x-correlation-id']\nawait fetch('http://svc/x')\n")
    assert scan(tmp_path, "c.js") == (True, True)


def test_plain_module_has_neither(tmp_path):
    _w(tmp_path, "d.py", "def add(a, b):\n    return a + b\n")
    assert scan(tmp_path, "d.py") == (False, False)

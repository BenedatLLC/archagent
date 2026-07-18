"""archagent connscan — static connector-kind inference from code."""

from archagent.connscan import emits_events, resolve_host, sync_call_hosts


def _w(tmp, rel, text):
    (tmp / rel).write_text(text)
    return rel


def test_sync_call_hosts_from_http_clients(tmp_path):
    _w(tmp_path, "a.py",
       'import requests\n'
       'r = requests.post("http://billing-svc/pay")\n'
       'x = httpx.get("https://ledger.internal:8080/balance")\n'
       'rel = requests.get("/local/path")\n')       # relative -> no host
    assert sync_call_hosts(tmp_path, "a.py") == {"billing-svc", "ledger.internal"}  # raw host; resolve strips domain


def test_sync_call_hosts_js(tmp_path):
    _w(tmp_path, "a.ts",
       "await fetch('http://orders-svc/x')\n"
       "await axios.post('https://pay/charge')\n")
    assert sync_call_hosts(tmp_path, "a.ts") == {"orders-svc", "pay"}


def test_variable_url_not_captured(tmp_path):
    _w(tmp_path, "a.py", 'r = requests.get(f"{BILLING_URL}/pay")\n')  # host is in a var
    assert sync_call_hosts(tmp_path, "a.py") == set()


def test_emits_events(tmp_path):
    _w(tmp_path, "a.py", "channel.publish(evt)\n")
    _w(tmp_path, "b.py", "task.apply_async(args)\n")
    _w(tmp_path, "c.py", "return x.send(data)\n")   # bare send -> not counted
    assert emits_events(tmp_path, "a.py") is True
    assert emits_events(tmp_path, "b.py") is True
    assert emits_events(tmp_path, "c.py") is False


def test_resolve_host():
    names = {"billing", "orders-svc", "ledger"}
    assert resolve_host("billing-svc", names) == "billing"       # suffix-stripped
    assert resolve_host("orders-svc", names) == "orders-svc"     # exact
    assert resolve_host("ledger.internal", names) == "ledger"    # domain head
    assert resolve_host("unknown-host", names) is None
    assert resolve_host("", names) is None

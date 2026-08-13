"""The permissive-origin scanner (issue #8).

Found because a blind judge noticed what a human reviewer and the artifact's author both missed: a local
telemetry tool with `Access-Control-Allow-Origin: *` and an unconditional WebSocket `CheckOrigin`, whose
documents leaned throughout on "local by default, which is the product". Local is not unreachable.
"""

from pathlib import Path

import pytest



def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


# --- the policy itself ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel,line,kind", [
    ("svc/handler.go", 'w.Header().Set("Access-Control-Allow-Origin", "*")', "acao-wildcard"),
    ("svc/ws.go", "CheckOrigin: func(r *http.Request) bool { return true },", "ws-checkorigin-true"),
    ("app/main.py", 'app.add_middleware(CORSMiddleware, allow_origins=["*"])', "allow-origins-wildcard"),
    ("web/server.js", 'app.use(cors({ origin: "*" }))', "cors-origin-wildcard"),
    ("web/other.js", "app.use(cors())", "cors-default-open"),
    ("api/app.py", "CORS(app)", "flask-cors-default-open"),
])
def test_each_permissive_spelling_is_found(tmp_path, rel, line, kind):
    from archagent.originscan import scan
    hits = scan(_repo(tmp_path, {rel: f"x = 1\n{line}\n"}))
    assert [h.kind for h in hits] == [kind]
    assert hits[0].line == 2


def test_a_restricted_origin_is_not_reported(tmp_path):
    from archagent.originscan import scan
    assert scan(_repo(tmp_path, {
        "svc/a.go": 'w.Header().Set("Access-Control-Allow-Origin", "https://app.example.com")\n',
        "web/b.js": 'app.use(cors({ origin: "https://app.example.com" }))\n',
        "app/c.py": 'app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"])\n',
    })) == []


def test_a_commented_out_policy_is_not_reported(tmp_path):
    from archagent.originscan import scan
    assert scan(_repo(tmp_path, {
        "svc/a.go": '// w.Header().Set("Access-Control-Allow-Origin", "*")\n',
        "app/b.py": '# app.add_middleware(CORSMiddleware, allow_origins=["*"])\n',
    })) == []


def test_test_files_are_skipped(tmp_path):
    """A fixture server opening its origin says nothing about the deployed policy, and reporting it
    trains a reader to ignore the signal."""
    from archagent.originscan import scan
    hits = scan(_repo(tmp_path, {
        "svc/handler_test.go": 'w.Header().Set("Access-Control-Allow-Origin", "*")\n',
        "tests/conftest.py": 'CORS(app)\n',
        "svc/handler.go": 'w.Header().Set("Access-Control-Allow-Origin", "*")\n',
    }))
    assert [h.file for h in hits] == ["svc/handler.go"]


def test_it_reads_languages_archagent_does_not_analyse(tmp_path):
    """The whole point. The motivating case is Go, which has no parser here — a scanner bound to the
    configured languages would have missed the one finding it was built for."""
    from archagent.originscan import scan
    hits = scan(_repo(tmp_path, {"svc/main.go": 'w.Header().Set("Access-Control-Allow-Origin", "*")\n'}))
    assert len(hits) == 1 and hits[0].file.endswith(".go")


# --- what raises the severity: a state-changing route behind the policy ---------------------------

def test_a_registered_mutating_route_is_found(tmp_path):
    from archagent.originscan import mutating_routes
    root = _repo(tmp_path, {"svc/api.go": 'mux.HandleFunc("DELETE /api/data", clearData(s))\n'})
    assert mutating_routes(root) == ["svc/api.go:1"]


def test_a_read_only_route_is_not_a_mutating_route(tmp_path):
    from archagent.originscan import mutating_routes
    assert mutating_routes(_repo(tmp_path, {
        "svc/api.go": 'mux.HandleFunc("GET /api/query/traces", queryTraces(s))\n'})) == []


def test_a_ui_placeholder_is_not_a_route(tmp_path):
    """This shipped as a false positive before the pattern required a registration call: a bare quoted
    `"POST /charge"` matched the hint text of a search box in a React component, and raised a finding's
    severity on evidence that was not a route."""
    from archagent.originscan import mutating_routes
    assert mutating_routes(_repo(tmp_path, {
        "web/Tab.tsx": '{ key: "rootSpanName", kind: "text", placeholder: "POST /charge" },\n'})) == []


def test_a_client_call_is_not_a_route(tmp_path):
    """`router.delete("/x")` and `apiClient.delete("/x")` are indistinguishable textually, and one of
    them is a caller. Python and JS/TS are parsed properly by webapi.extract_routes, so the textual
    fallback does not need to guess."""
    from archagent.originscan import mutating_routes
    assert mutating_routes(_repo(tmp_path, {
        "web/client.ts": 'await apiClient.delete("/api/data");\n'})) == []


def test_scope_restricts_the_route_search(tmp_path):
    """The question is not "does this repo contain a DELETE route" but "is one reachable behind this
    policy". A fixture app under evals/ answers neither."""
    from archagent.originscan import mutating_routes
    root = _repo(tmp_path, {
        "observer/api.go": 'mux.HandleFunc("DELETE /api/data", h)\n',
        "evals/fixture/app.go": 'mux.HandleFunc("DELETE /other", h)\n',
    })
    assert mutating_routes(root, under=("observer/",)) == ["observer/api.go:1"]
    assert len(mutating_routes(root)) == 2

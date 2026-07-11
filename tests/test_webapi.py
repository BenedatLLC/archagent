"""Static web-route extraction and OpenAPI loading."""

from archagent.webapi import Route, extract_routes, load_openapi, matches


def _files(tmp, mapping):
    for rel, content in mapping.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return set(mapping)


def test_fastapi_and_flask_decorators(tmp_path):
    files = _files(tmp_path, {
        "src/api.py": (
            "@app.get('/items')\ndef list_items(): ...\n"
            "@router.post('/items/{id}')\ndef create(id): ...\n"
        ),
        "src/legacy.py": (
            "@app.route('/legacy', methods=['POST', 'GET'])\ndef legacy(): ...\n"
            "@bp.get('/health')\ndef health(): ...\n"
        ),
    })
    routes = extract_routes(tmp_path, files)
    assert Route("GET", "items") in routes
    assert Route("POST", "items/{}") in routes           # {id} normalized to {}
    assert Route("POST", "legacy") in routes and Route("GET", "legacy") in routes
    assert Route("GET", "health") in routes


def test_django_urls(tmp_path):
    files = _files(tmp_path, {
        "src/urls.py": (
            "from django.urls import path, re_path\n"
            "urlpatterns = [\n"
            "    path('api/users/', v),\n"
            "    re_path(r'^items/(?P<id>\\d+)/$', v),\n"
            "]\n"
        ),
    })
    paths = {r.path for r in extract_routes(tmp_path, files)}
    assert "api/users" in paths
    assert "items/{}" in paths


def test_non_route_decorator_is_ignored(tmp_path):
    files = _files(tmp_path, {"src/x.py": "@cache.get('key')\ndef f(): ...\n"})  # no leading slash
    assert extract_routes(tmp_path, files) == []


def test_express_and_fastify_routes(tmp_path):
    files = _files(tmp_path, {
        "src/routes.ts": (
            "app.get('/users', h)\n"
            "router.post('/users/:id', h)\n"
            "fastify.delete('/users/:id', h)\n"
        ),
    })
    routes = extract_routes(tmp_path, files)
    assert Route("GET", "users") in routes
    assert Route("POST", "users/{}") in routes      # :id normalized to {}
    assert Route("DELETE", "users/{}") in routes


def test_nestjs_controller_routes(tmp_path):
    files = _files(tmp_path, {
        "src/users.controller.ts": (
            "@Controller('users')\n"
            "export class UsersController {\n"
            "  @Get()\n  findAll() {}\n"
            "  @Post(':id')\n  create() {}\n"
            "}\n"
        ),
    })
    paths = {(r.method, r.path) for r in extract_routes(tmp_path, files)}
    assert ("GET", "users") in paths           # controller prefix + empty method path
    assert ("POST", "users/{}") in paths       # prefix + :id


def test_load_openapi_json(tmp_path):
    (tmp_path / "openapi.json").write_text(
        '{"paths": {"/items": {"get": {}, "post": {}}, "/items/{id}": {"get": {}}}}')
    routes, spec_path = load_openapi(tmp_path)
    assert spec_path == "openapi.json"
    assert Route("GET", "items") in routes and Route("POST", "items") in routes
    assert Route("GET", "items/{}") in routes


def test_matches_wildcard_and_method(tmp_path):
    others = [Route("GET", "items"), Route("POST", "items")]
    assert matches("*", "items", others)        # Django wildcard matches any method at that path
    assert matches("GET", "items", others)
    assert not matches("DELETE", "items", others)
    assert not matches("GET", "widgets", others)

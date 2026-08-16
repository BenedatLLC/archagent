"""Server-side fetch of a caller-supplied URL (issue #12).

Found by a blind model judge on wardrowbe, by neither the human reviewer nor the artifact's author — the
second round running where the security-relevant finding came from the judge alone.

The tests that matter here are the negative ones. A taint check that fires on everything is worse than
none, and the first two runs of this scanner produced nine hits and two hits against one real case; both
false-positive sources are pinned below.
"""

from pathlib import Path

import pytest

from archagent.fetchscan import scan_python


def _mod(tmp_path: Path, body: str, name: str = "api.py") -> tuple[Path, set[str]]:
    (tmp_path / name).write_text(body)
    return tmp_path, {name}


ROUTE_FETCH = '''
import httpx
from fastapi import APIRouter
router = APIRouter()

@router.post("/test-endpoint")
async def test_endpoint(data: dict):
    url = data.get("url", "").rstrip("/")
    async with httpx.AsyncClient() as client:
        return await client.get(url)
'''


def test_a_route_fetching_request_input_is_found(tmp_path):
    root, files = _mod(tmp_path, ROUTE_FETCH)
    hits = scan_python(root, files)
    assert len(hits) == 1
    assert hits[0].in_route and hits[0].guard == "none"


def test_a_scheme_check_is_reported_as_shape_only(tmp_path):
    """The distinction the whole signal turns on: a scheme check constrains what the string looks like,
    never where the request goes. It must not read as a defence."""
    root, files = _mod(tmp_path, ROUTE_FETCH.replace(
        'url = data.get("url", "").rstrip("/")',
        'url = data.get("url", "")\n    if not url.startswith("https://"):\n        raise ValueError'))
    assert scan_python(root, files)[0].guard == "shape-only"


def test_an_allowlist_is_reported_as_such(tmp_path):
    root, files = _mod(tmp_path, ROUTE_FETCH.replace(
        'url = data.get("url", "").rstrip("/")',
        'url = data.get("url", "")\n    if url not in ALLOWED_HOSTS:\n        raise ValueError'))
    assert scan_python(root, files)[0].guard == "allow-list"


# --- the false positives that actually occurred -----------------------------------------------------

def test_self_does_not_taint_every_service_method(tmp_path):
    """First run: 9 hits against 1 real case. `self` is a parameter, so treating parameters as
    caller-supplied outside a route handler tainted every method on every class."""
    root, files = _mod(tmp_path, '''
import httpx

class WeatherService:
    def __init__(self, base): self.base = base
    async def fetch(self):
        async with httpx.AsyncClient() as client:
            return await client.get(self.base + "/current")
''')
    assert scan_python(root, files) == []


def test_a_literal_in_an_fstring_is_not_a_variable_reference(tmp_path):
    """Second run: `f"{endpoint.url}/models"` mentions the word `models`, and a nearby
    `models = data.get("data", [])` had tainted that name. Matching the unparsed *text* of the argument
    called a path segment a tainted variable."""
    root, files = _mod(tmp_path, '''
import httpx
from fastapi import APIRouter
router = APIRouter()

@router.get("/probe")
async def probe(endpoint, data: dict):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{endpoint.url}/models")
        models = data.get("data", [])
        return models
''')
    hits = [h for h in scan_python(root, files) if h.source == "models"]
    assert hits == []


def test_generic_dict_access_outside_a_route_is_not_request_input(tmp_path):
    """`data.get("data", [])` in a service is ordinary dict access, not a request body."""
    root, files = _mod(tmp_path, '''
import httpx

async def summarise(data, target):
    rows = data.get("data", [])
    async with httpx.AsyncClient() as client:
        return await client.get(target)
''')
    assert scan_python(root, files) == []


def test_a_constant_url_is_not_a_finding(tmp_path):
    root, files = _mod(tmp_path, '''
import httpx
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health(data: dict):
    async with httpx.AsyncClient() as client:
        return await client.get("https://status.example.com/health")
''')
    assert scan_python(root, files) == []


def test_a_non_http_call_is_not_a_fetch(tmp_path):
    """`.get` is also how you read a dict. Only calls on something client-shaped count."""
    root, files = _mod(tmp_path, '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/x")
async def x(data: dict):
    url = data.get("url")
    return {"echo": url}
''')
    assert scan_python(root, files) == []


def test_an_orm_session_is_not_an_http_client(tmp_path):
    """The corpus regression caught this: `session.delete(item)` and `session.get(User, id)` are
    SQLAlchemy, and they share their verbs with an HTTP client. Three ORM deletes on fastapi-template
    were reported as server-side fetches. A name is a client only if a client was assigned to it."""
    root, files = _mod(tmp_path, '''
from fastapi import APIRouter
router = APIRouter()

@router.delete("/items/{item_id}")
def delete_item(session, item_id: str):
    item = session.get(Item, item_id)
    session.delete(item)
    return {"ok": True}
''')
    assert scan_python(root, files) == []


def test_a_client_bound_by_a_with_statement_is_still_a_client(tmp_path):
    """The fix must not lose the ordinary spelling: `async with httpx.AsyncClient() as client`."""
    root, files = _mod(tmp_path, ROUTE_FETCH)
    assert len(scan_python(root, files)) == 1

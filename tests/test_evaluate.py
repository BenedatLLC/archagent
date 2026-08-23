"""archagent evaluate — system-level smell candidates (regime A, static)."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.evaluate import evaluate


def _cfg(tmp):
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _src(cfg, rel, text):
    p = cfg.project_root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _sub(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / f"{name}.md").write_text(text)


def _signs(result):
    return {f.sign for f in result.findings}


def _of(result, sign):
    return [f for f in result.findings if f.sign == sign]


# --- Coverage of the evaluation itself (inactive families) --------------------------------

def _has_inactive(result, needle):
    return any(needle in i.family for i in result.inactive)


def test_missing_metadata_reported_as_inactive(tmp_path):
    cfg = _cfg(tmp_path)
    # two subsystems, but no **Service:**, **Tier:**, or **Connects:** anywhere
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "a", "# a\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "b", "# b\n\n**Covers:** `src/pkg/b.py`\n")
    r = evaluate(cfg, history=False)
    assert _has_inactive(r, "data & source-of-truth")   # needs >=2 Service:
    assert _has_inactive(r, "layering")                 # needs >=2 Tier:
    assert _has_inactive(r, "connector topology")       # needs Connects:
    assert any("Service" in i.reason for i in r.inactive)


def test_full_metadata_activates_families(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "a", "# a\n\n**Covers:** `src/pkg/a.py`\n**Service:** svc-a\n**Tier:** ui\n"
                   "**Connects:** b via sync-call\n")
    _sub(cfg, "b", "# b\n\n**Covers:** `src/pkg/b.py`\n**Service:** svc-b\n**Tier:** domain\n")
    r = evaluate(cfg, history=False)
    assert not _has_inactive(r, "data & source-of-truth")
    assert not _has_inactive(r, "layering")
    assert not _has_inactive(r, "connector topology")
    # history still inactive because we passed history=False
    assert _has_inactive(r, "git history")


# --- God Component ------------------------------------------------------------------------

def test_god_component_flags_a_hub(tmp_path):
    cfg = _cfg(tmp_path)
    # hub imported by three others AND importing three others
    _src(cfg, "pkg/hub.py", "from pkg import a, b, c\n")
    for n in ("a", "b", "c"):
        _src(cfg, f"pkg/{n}.py", "from pkg import hub\n")
    _sub(cfg, "hub", "# Hub\n\n**Covers:** `src/pkg/hub.py`\n")
    for n in ("a", "b", "c"):
        _sub(cfg, n, f"# {n}\n\n**Covers:** `src/pkg/{n}.py`\n")
    r = evaluate(cfg)
    god = _of(r, "god-component")
    assert god and god[0].subjects == ["hub"]


# --- Cyclic dependency --------------------------------------------------------------------

def test_subsystem_cycle_detected_with_shape(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/x.py", "from pkg import y\n")
    _src(cfg, "pkg/y.py", "from pkg import x\n")
    _sub(cfg, "x", "# X\n\n**Covers:** `src/pkg/x.py`\n")
    _sub(cfg, "y", "# Y\n\n**Covers:** `src/pkg/y.py`\n")
    r = evaluate(cfg)
    cyc = _of(r, "cycle-subsystem")
    assert cyc and sorted(cyc[0].subjects) == ["x", "y"]
    assert "tiny cycle" in cyc[0].detail


def test_no_cycle_when_acyclic(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/x.py", "from pkg import y\n")
    _src(cfg, "pkg/y.py", "z = 1\n")
    _sub(cfg, "x", "# X\n\n**Covers:** `src/pkg/x.py`\n")
    _sub(cfg, "y", "# Y\n\n**Covers:** `src/pkg/y.py`\n")
    assert "cycle-subsystem" not in _signs(evaluate(cfg))


# --- Unstable Dependency ------------------------------------------------------------------

def test_unstable_dependency_flags_dependence_on_volatile(tmp_path):
    cfg = _cfg(tmp_path)
    # 'core' is stable (a, b, c depend on it) yet itself depends on the volatile 'vol'
    # (vol depends on p, q and is depended on only by core) — the wrong-direction dependency.
    for n in ("a", "b", "c"):
        _src(cfg, f"pkg/{n}.py", "from pkg import core\n")
    _src(cfg, "pkg/core.py", "from pkg import vol\n")
    _src(cfg, "pkg/vol.py", "from pkg import p, q\n")
    _src(cfg, "pkg/p.py", "x = 1\n")
    _src(cfg, "pkg/q.py", "y = 1\n")
    for n in ("a", "b", "c", "core", "vol", "p", "q"):
        _sub(cfg, n, f"# {n}\n\n**Covers:** `src/pkg/{n}.py`\n")
    r = evaluate(cfg)
    ud = _of(r, "unstable-dependency")
    assert any(f.subjects == ["core"] and "vol" in f.detail for f in ud)


# --- Leaky abstraction / tier -------------------------------------------------------------

def test_layer_inversion_flagged(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/db.py", "from pkg import ui\n")     # infra depends UP on ui
    _src(cfg, "pkg/ui.py", "z = 1\n")
    _sub(cfg, "db", "# DB\n\n**Tier:** infra\n\n**Covers:** `src/pkg/db.py`\n")
    _sub(cfg, "ui", "# UI\n\n**Tier:** ui\n\n**Covers:** `src/pkg/ui.py`\n")
    r = evaluate(cfg)
    assert r.tier_declared is True
    inv = _of(r, "layer-inversion")
    assert inv and inv[0].subjects == ["db", "ui"]


def test_layer_skip_flagged(tmp_path):
    """A skip past a layer that is actually there.

    The `svc` subsystem is what makes this a skip rather than the shape of the system, and it was added
    after calibration round 2: this fixture previously declared only `ui` and `data`, so it asserted the
    exact false positive a reviewer dismissed three times — a leak past a layer the system did not have.
    """
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/ui.py", "from pkg import db\n")     # ui reaches past domain to infra
    _src(cfg, "pkg/svc.py", "y = 1\n")
    _src(cfg, "pkg/db.py", "z = 1\n")
    _sub(cfg, "ui", "# UI\n\n**Tier:** ui\n\n**Covers:** `src/pkg/ui.py`\n")
    _sub(cfg, "svc", "# SVC\n\n**Tier:** domain\n\n**Covers:** `src/pkg/svc.py`\n")
    _sub(cfg, "db", "# DB\n\n**Tier:** data\n\n**Covers:** `src/pkg/db.py`\n")
    r = evaluate(cfg)
    assert "layer-skip" in _signs(r)


def test_tier_check_skipped_without_declarations(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/db.py", "from pkg import ui\n")
    _src(cfg, "pkg/ui.py", "z = 1\n")
    _sub(cfg, "db", "# DB\n\n**Covers:** `src/pkg/db.py`\n")
    _sub(cfg, "ui", "# UI\n\n**Covers:** `src/pkg/ui.py`\n")
    r = evaluate(cfg)
    assert r.tier_declared is False
    assert "layer-inversion" not in _signs(r)


# --- Hard-coded endpoints -----------------------------------------------------------------

def test_hardcoded_endpoint_flags_only_real_service_endpoints(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/net.py",
         'PROD = "http://10.2.3.4:8080/api"\n'      # IP literal — flag
         'PEER = "https://cache.svc:6379"\n'         # host:port — flag
         'LOCAL = "http://localhost:8000"\n'         # localhost — skip
         'API = "https://api.stripe.com/v1"\n'       # public API, no port — skip
         '# see https://internal.host:9000/docs\n')  # comment — skip
    _sub(cfg, "net", "# Net\n\n**Covers:** `src/pkg/net.py`\n")
    hits = [f.detail for f in _of(evaluate(cfg), "hardcoded-endpoint")]
    assert any("10.2.3.4" in h for h in hits)
    assert any("cache.svc:6379" in h for h in hits)
    assert not any("localhost" in h for h in hits)
    assert not any("stripe" in h for h in hits)
    assert not any("internal.host" in h for h in hits)  # in a comment


def test_reserved_ranges_are_not_endpoints_anywhere(tmp_path):
    """An address the IETF reserved for documentation or made unroutable cannot be infrastructure, so
    neither reading of this finding applies. On dspy, half of `hardcoded-endpoint`'s entire output was
    `169.254.169.254` — the cloud metadata address, used in a fixture *because* it is unreachable — and
    the report advised moving it to service discovery."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/net.py",
         'META = "http://169.254.169.254/latest/meta-data/"\n'   # RFC 3927 link-local
         'DOC = "http://192.0.2.10:8080/"\n'                     # RFC 5737 TEST-NET-1
         'REAL = "http://10.2.3.4:8080/api"\n')                  # routable — still flagged
    _sub(cfg, "net", "# Net\n\n**Covers:** `src/pkg/net.py`\n")
    hits = [f.detail for f in _of(evaluate(cfg), "hardcoded-endpoint")]
    assert not any("169.254" in h for h in hits)
    assert not any("192.0.2" in h for h in hits)
    assert any("10.2.3.4" in h for h in hits), "the routable one must survive the exclusion"


def test_an_endpoint_in_a_test_gets_the_reading_that_applies_to_tests(tmp_path):
    """Not skipped — *re-read*. Pinning is a claim about deployment and a test has no environment to be
    pinned to, so the production recommendation is not merely unhelpful there, it is wrong. The finding
    that remains is about hermeticity, and it drops to `low`."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/net.py", 'PROD = "http://10.2.3.4:8080/api"\n')
    _src(cfg, "pkg/tests/test_net.py", 'HOST = "http://20.102.90.50:2017/"\n')
    _sub(cfg, "net", "# Net\n\n**Covers:** `src/pkg/**`\n")
    found = {f.subjects[0].split(":")[0]: f for f in _of(evaluate(cfg), "hardcoded-endpoint")}
    prod = found["src/pkg/net.py"]
    test = found["src/pkg/tests/test_net.py"]

    assert prod.severity == "med" and test.severity == "low"
    # the test finding must not repeat the pinning advice, which is the part that was wrong
    assert "service discovery" not in test.recommendation
    assert "config" not in test.recommendation
    assert "infrastructure the suite does not control" in test.recommendation
    # and both name the address they found rather than advising in the abstract
    assert "10.2.3.4" in prod.recommendation
    assert "20.102.90.50" in test.recommendation


# --- Service cycle (distributed monolith) -------------------------------------------------

def test_service_cycle_from_compose(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  a:\n    image: a\n    depends_on:\n      - b\n"
        "  b:\n    image: b\n    depends_on:\n      - a\n"
    )
    # a <-> b is a cyclic service dependency (distributed-monolith signal)
    cyc = _of(evaluate(cfg), "cycle-service")
    assert cyc and sorted(cyc[0].subjects) == ["a", "b"]


# --- Group A: data & source-of-truth ------------------------------------------------------

def _svc_sub(cfg, name, service, covers, extra=""):
    _sub(cfg, name, f"# {name}\n\n**Service:** {service}\n\n**Covers:** `{covers}`\n{extra}")


def test_duplicated_source_of_truth(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/amodels.py", '__tablename__ = "orders"\n')
    _src(cfg, "pkg/bmodels.py", '__tablename__ = "orders"\n')
    _svc_sub(cfg, "a", "svc-a", "src/pkg/amodels.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/bmodels.py")
    dup = _of(evaluate(cfg), "duplicated-source-of-truth")
    assert dup and "orders" in dup[0].detail and sorted(dup[0].subjects) == ["svc-a", "svc-b"]


def test_service_intimacy(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/amodels.py", '__tablename__ = "orders"\n')          # svc-a owns orders
    _src(cfg, "pkg/bq.py", 'q = "SELECT * FROM orders WHERE id = 1"\n')  # svc-b reaches in
    _svc_sub(cfg, "a", "svc-a", "src/pkg/amodels.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/bq.py")
    r = evaluate(cfg)
    intim = _of(r, "service-intimacy")
    assert intim and "orders" in intim[0].detail and "svc-b" in intim[0].detail
    assert "duplicated-source-of-truth" not in _signs(r)  # single owner


def test_shared_persistency_via_db_conn_key(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/adb.py", 'import os\nu = os.getenv("ANALYTICS_DB_URL")\n')
    _src(cfg, "pkg/bdb.py", 'import os\nu = os.getenv("ANALYTICS_DB_URL")\n')
    _svc_sub(cfg, "a", "svc-a", "src/pkg/adb.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/bdb.py")
    sp = _of(evaluate(cfg), "shared-persistency")
    assert sp and "ANALYTICS_DB_URL" in sp[0].detail


def test_shared_library_across_services(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/shared.py", "helper = 1\n")
    _src(cfg, "pkg/a.py", "from pkg import shared\n")
    _src(cfg, "pkg/b.py", "from pkg import shared\n")
    _svc_sub(cfg, "shared", "svc-a", "src/pkg/shared.py")
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/b.py")
    lib = _of(evaluate(cfg), "shared-library")
    assert lib and "src/pkg/shared.py" in lib[0].detail
    assert sorted(lib[0].subjects) == ["svc-a", "svc-b"]


def test_group_a_gated_on_multiple_services(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/amodels.py", '__tablename__ = "orders"\n')
    _src(cfg, "pkg/bmodels.py", '__tablename__ = "orders"\n')
    _svc_sub(cfg, "a", "svc-a", "src/pkg/amodels.py")   # both in the same service
    _svc_sub(cfg, "b", "svc-a", "src/pkg/bmodels.py")
    signs = _signs(evaluate(cfg))
    assert not ({"duplicated-source-of-truth", "shared-persistency", "service-intimacy"} & signs)


# --- connector-typed edges (**Connects:**) ------------------------------------------------

def _conn_sub(cfg, name, service, covers, connects):
    _sub(cfg, name, f"# {name}\n\n**Service:** {service}\n\n**Connects:** {connects}\n\n**Covers:** `{covers}`\n")


def test_distributed_monolith_on_sync_cycle(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _conn_sub(cfg, "a", "svc-a", "src/pkg/a.py", "b via sync-call")
    _conn_sub(cfg, "b", "svc-b", "src/pkg/b.py", "a via sync-call")
    dm = _of(evaluate(cfg), "distributed-monolith")
    assert dm and dm[0].severity == "high" and sorted(dm[0].subjects) == ["svc-a", "svc-b"]


def test_async_service_cycle_is_informational(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _conn_sub(cfg, "a", "svc-a", "src/pkg/a.py", "b via async-event")
    _conn_sub(cfg, "b", "svc-b", "src/pkg/b.py", "a via async-event")
    dm = _of(evaluate(cfg), "distributed-monolith")
    assert dm and dm[0].severity == "low"  # event-decoupled cycle -> informational, not a monolith


def test_extraneous_adjacent_connector(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    # a -> b via sync-call AND b -> a via async-event: two kinds between the same pair
    _conn_sub(cfg, "a", "svc-a", "src/pkg/a.py", "b via sync-call")
    _conn_sub(cfg, "b", "svc-b", "src/pkg/b.py", "a via async-event")
    eac = _of(evaluate(cfg), "extraneous-adjacent-connector")
    assert eac and sorted(eac[0].subjects) == ["a", "b"]


def test_no_connector_signals_without_connects(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    signs = _signs(evaluate(cfg))
    assert not ({"distributed-monolith", "extraneous-adjacent-connector"} & signs)


def test_distributed_monolith_inferred_from_code_without_declarations(tmp_path):
    # no **Connects:** anywhere — the sync cycle is inferred from hard-coded HTTP calls between the services
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", 'import requests\nrequests.post("http://svc-b/x")\n')
    _src(cfg, "pkg/b.py", 'import requests\nrequests.get("http://svc-a/y")\n')
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/b.py")
    dm = _of(evaluate(cfg), "distributed-monolith")
    assert dm and dm[0].severity == "high"
    assert "inferred" in dm[0].detail and dm[0].confidence == "low"


# --- Group D: cross-boundary observability ------------------------------------------------

def test_no_request_tracing_systemic(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", 'import requests\nr = requests.get("http://svc-b/x")\n')
    _src(cfg, "pkg/b.py", 'import requests\nr = requests.get("http://svc-a/y")\n')
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/b.py")
    nt = _of(evaluate(cfg), "no-request-tracing")
    assert nt and sorted(nt[0].subjects) == ["svc-a", "svc-b"]


def test_trace_chain_gap_when_only_some_instrument(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", 'import opentelemetry\nimport requests\nr = requests.get("http://svc-b/x")\n')
    _src(cfg, "pkg/b.py", 'import requests\nr = requests.get("http://svc-a/y")\n')  # no instrumentation
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/b.py")
    r = evaluate(cfg)
    assert "no-request-tracing" not in _signs(r)
    gap = _of(r, "trace-chain-gap")
    assert gap and [f.subjects[0] for f in gap] == ["svc-b"]


def test_no_observability_finding_without_cross_service_calls(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 2\n")
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/b.py")
    assert not ({"no-request-tracing", "trace-chain-gap"} & _signs(evaluate(cfg)))


def test_no_observability_finding_when_all_instrumented(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", 'import opentelemetry\nimport requests\nr = requests.get("http://svc-b")\n')
    _src(cfg, "pkg/b.py", 'import opentelemetry\nimport requests\nr = requests.get("http://svc-a")\n')
    _svc_sub(cfg, "a", "svc-a", "src/pkg/a.py")
    _svc_sub(cfg, "b", "svc-b", "src/pkg/b.py")
    assert not ({"no-request-tracing", "trace-chain-gap"} & _signs(evaluate(cfg)))


def test_clean_project_has_no_findings(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from pkg import b\n")
    _src(cfg, "pkg/b.py", "x = 1\n")
    _sub(cfg, "a", "# A\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "b", "# B\n\n**Covers:** `src/pkg/b.py`\n")
    assert evaluate(cfg).findings == []


def test_no_inactive_family_may_claim_a_sign_that_was_reported(tmp_path):
    """The invariant the coverage report exists to hold.

    Its job is to stop "no findings" being read as "clean". The inverse — naming a family inactive while
    that family produced a finding — defeats it just as thoroughly, and happened: the git-history entry
    claimed all of F under `--no-history` while `enum-value-escape`, a pure code scan, had fired in the
    same run. The old assertions were substring matches on the label ("git history"), which passed both
    before and after the fix, so they could not have caught it. This checks the property instead.
    """
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/e.py", 'from enum import Enum\n\n\nclass Status(Enum):\n'
                          '    ACTIVE = "active"\n    PAUSED = "paused"\n    DONE = "done"\n')
    for n in "abcd":
        _src(cfg, f"pkg/{n}.py", 'def f(s):\n    if s == "active": return 1\n'
                                 '    if s == "paused": return 2\n    if s == "done": return 3\n')
    _sub(cfg, "a", "# a\n\n**Covers:** `src/pkg/*.py`\n**Tier:** domain\n")
    for history in (False, True):
        r = evaluate(cfg, history=history)
        reported = {f.sign for f in r.findings}
        for entry in r.inactive:
            overlap = reported & set(entry.signs)
            assert not overlap, (
                f"{entry.family!r} is reported inactive but these signs were reported: {sorted(overlap)}")


def test_a_degraded_family_lists_no_signs(tmp_path):
    """"E — bug-fix weighting" means change-prone-file is ranked on total churn, not that it did not run.
    Listing its sign would make the check above fail — correctly, because the label would then be
    claiming more than it means."""
    from archagent.evaluate import Inactive
    assert Inactive("E — bug-fix weighting", "no convention learned").signs == ()


# --- permissive origin (group D, issue #8) --------------------------------------------------------

def test_a_wide_open_origin_with_a_mutating_route_is_high(tmp_path):
    """The severity turns on what else is reachable: the same policy in front of a delete route means any
    page the developer browses can delete their data."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    (tmp_path / "src/pkg/api.py").write_text(
        'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n\n'
        '@app.delete("/api/data")\ndef clear():\n    pass\n')
    _sub(cfg, "a", "# a\n\n**Covers:** `src/pkg/*.py`\n**Tier:** domain\n")
    f = _of(evaluate(cfg, history=False), "permissive-origin")
    assert len(f) == 1 and f[0].severity == "high" and f[0].group == "D"


def test_a_wide_open_origin_with_no_mutating_route_is_med(tmp_path):
    """A permissive origin is not automatically a defect — a read-only surface is a design choice."""
    cfg = _cfg(tmp_path)
    (tmp_path / "src/pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/pkg/api.py").write_text(
        'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n\n'
        '@app.get("/api/traces")\ndef traces():\n    pass\n')
    _sub(cfg, "a", "# a\n\n**Covers:** `src/pkg/*.py`\n**Tier:** domain\n")
    f = _of(evaluate(cfg, history=False), "permissive-origin")
    assert len(f) == 1 and f[0].severity == "med"


def test_a_restricted_origin_produces_no_finding(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "src/pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/pkg/api.py").write_text(
        'app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"])\n')
    _sub(cfg, "a", "# a\n\n**Covers:** `src/pkg/*.py`\n**Tier:** domain\n")
    assert _of(evaluate(cfg, history=False), "permissive-origin") == []


# --- layer-skip only fires over a tier the system has (calibration round 2) --------------------------

def _tiered(tiers: dict, edges: dict):
    """A model carrying just the tier declarations and edges the layering check reads."""
    from archagent.evaluate import _Model, _tier_violations
    m = _Model.__new__(_Model)
    m.subs = list(tiers)
    m.tier = dict(tiers)
    m.edges = {s: set(edges.get(s, ())) for s in tiers}
    return _tier_violations(m)


def test_a_skip_over_an_unpopulated_tier_is_not_reported():
    """Round 2's whole layer-skip result: 3 findings, 3 dismissals, one reason. Neither repository
    declared anything at rank 3, so a ui -> domain edge was counted as skipping a layer that was not in
    the system, and the advice to "route through the intermediate layer" named nothing."""
    found = _tiered({"cli": "ui", "core": "domain"}, {"cli": ["core"]})
    assert [f.sign for f in found] == []


def test_a_skip_over_a_tier_that_exists_is_still_reported():
    """The check must not be turned off — only narrowed. With something declared at the intermediate
    rank there is a real layer being bypassed and something concrete to route through."""
    found = _tiered({"cli": "ui", "api": "app", "core": "domain"}, {"cli": ["core"]})
    assert [f.sign for f in found] == ["layer-skip"]


def test_the_intermediate_tier_must_lie_between_the_two_ends():
    """A populated rank outside the gap is not something the edge could route through."""
    found = _tiered({"ui1": "ui", "d": "domain", "i": "infra"}, {"ui1": ["d"]})
    assert [f.sign for f in found] == []           # infra is below the target, not between


def test_layer_inversion_is_unaffected_by_the_skip_narrowing():
    """Round 2 scored inversion 2 of 4, but both failures were about how tiers were assigned to test and
    migration packages rather than about this check. Narrowing it on that evidence would be acting on a
    different finding than the one measured."""
    found = _tiered({"infra1": "infra", "d": "domain"}, {"infra1": ["d"]})
    assert [f.sign for f in found] == ["layer-inversion"]


# --- declared Connects edges join the structural graph (issue #25) ----------------------------------

def _sub_with(cfg, name, body):
    _sub(cfg, name, body)


def test_a_declared_import_edge_the_code_cannot_show_still_builds_the_graph(tmp_path):
    """A Go, Rust or Java majority repo produces no import graph, so every structural signal was inert
    and nothing said so. DD-4: the declared model is ground truth and inference corroborates it — a
    dependency the author declared is a dependency whether or not archagent can parse the language."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")           # no imports between them anywhere in code
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "top", "# T\n\n**Tier:** infra\n\n**Connects:** low via import\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "low", "# L\n\n**Tier:** domain\n\n**Covers:** `src/pkg/b.py`\n")
    r = evaluate(cfg)
    assert "layer-inversion" in _signs(r)


def test_a_finding_resting_only_on_declarations_is_marked_and_downgraded(tmp_path):
    """The honest cost of trusting declarations. Reporting a taken-on-trust finding at the same
    confidence as a measured one hides the very distinction DD-4 draws."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "top", "# T\n\n**Tier:** infra\n\n**Connects:** low via import\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "low", "# L\n\n**Tier:** domain\n\n**Covers:** `src/pkg/b.py`\n")
    f = _of(evaluate(cfg), "layer-inversion")[0]
    assert f.confidence == "med"                       # down from "high"
    assert "no parsed import corroborates" in f.detail


def test_a_measured_edge_is_not_marked_or_downgraded(tmp_path):
    """The same finding, with a real import behind it, must be unaffected."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "top", "# T\n\n**Tier:** infra\n\n**Connects:** low via import\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "low", "# L\n\n**Tier:** domain\n\n**Covers:** `src/pkg/b.py`\n")
    f = _of(evaluate(cfg), "layer-inversion")[0]
    assert f.confidence == "high" and "corroborates" not in f.detail


def test_a_declared_only_graph_is_reported_as_unverified_coverage(tmp_path):
    """Before this, obstudio scored 1.00 on the rubric's "evaluate signal families active" while six
    structural signals produced nothing — a perfect coverage mark over a gap nobody could see."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "top", "# T\n\n**Tier:** infra\n\n**Connects:** low via import\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "low", "# L\n\n**Tier:** domain\n\n**Covers:** `src/pkg/b.py`\n")
    r = evaluate(cfg)
    entry = [i for i in r.inactive if "structural graph" in i.family]
    assert entry, [i.family for i in r.inactive]
    # signs stays EMPTY: these families are degraded, not absent — they still emit. Listing the signs
    # would contradict the findings in the same report, which is what `signs` exists to prevent.
    assert entry[0].signs == ()


def test_a_parsed_graph_reports_no_unverified_coverage_entry(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "top", "# T\n\n**Tier:** infra\n\n**Connects:** low via import\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "low", "# L\n\n**Tier:** domain\n\n**Covers:** `src/pkg/b.py`\n")
    assert not [i for i in evaluate(cfg).inactive if "structural graph" in i.family]


def test_a_non_import_connector_does_not_become_an_import_edge(tmp_path):
    """`via async-event` is not a code dependency and must not create one — that would manufacture
    layering violations out of a message queue."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "x = 1\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "top", "# T\n\n**Tier:** infra\n\n**Connects:** low via async-event\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "low", "# L\n\n**Tier:** domain\n\n**Covers:** `src/pkg/b.py`\n")
    assert "layer-inversion" not in _signs(evaluate(cfg))


def test_the_mechanical_severity_caveat_is_not_gated_on_triage():
    """It used to live inside `if flagged:`, so a run where nothing was marked for investigation printed
    its findings with HIGH and MED severities and never said what those words mean. Round 5's reviewer
    read exactly such a run on dspy — 65 findings, zero flagged — and scored `finding_restraint` 2 of 5,
    naming this: "the body gives HIGH/MED severity without saying it is mechanical"."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src" / "archagent" / "cli.py").read_text()
    body = src[src.index("def evaluate_cmd") if "def evaluate_cmd" in src else 0:]
    i_caveat = src.index("Severity above is mechanical")
    i_flagged = src.index("flagged = [f for f in findings if f.investigate]")
    assert i_caveat < i_flagged, "the caveat must print before, and independently of, the triage block"


# --- What a god-component finding tells the reader to do (#31) -----------------------------

def test_god_component_names_the_seam_it_measured(tmp_path):
    """"Split this subsystem along its internal seams; extract the most-depended-on responsibilities"
    named no seam and no responsibility — while the finding held both. Fan-in was computed from the very
    edges that say which files other subsystems reach for."""
    cfg = _cfg(tmp_path)
    # `core` is a hub: three subsystems import it and it imports three. Only core/api.py is reached from
    # outside; core/impl*.py are internal.
    _src(cfg, "pkg/core/api.py", "from pkg.x import a\nfrom pkg.y import b\nfrom pkg.z import c\n")
    _src(cfg, "pkg/core/impl1.py", "from pkg.core import api\n")
    _src(cfg, "pkg/core/impl2.py", "from pkg.core import api\n")
    for n in ("p", "q", "r"):
        _src(cfg, f"pkg/{n}.py", "from pkg.core import api\n")
    for n in ("x", "y", "z"):
        _src(cfg, f"pkg/{n}.py", "v = 1\n")
    _sub(cfg, "core", "# Core\n\n**Covers:** `src/pkg/core/**`\n")
    for n in ("p", "q", "r", "x", "y", "z"):
        _sub(cfg, n, f"# {n}\n\n**Covers:** `src/pkg/{n}.py`\n")

    found = _of(evaluate(cfg), "god-component")
    assert found, "fan-in 3 / fan-out 3 is the hub threshold"
    rec = [f for f in found if f.subjects == ["core"]][0].recommendation

    assert "src/pkg/core/api.py" in rec, "the file other subsystems reach for must be named"
    assert "`p`" in rec and "`q`" in rec, "the dependents must be named"
    # and the two internal files are identified as the movable body, not left for the reader to work out
    assert "imported only from inside" in rec


def test_god_component_advice_survives_an_empty_import_graph(tmp_path):
    """The seam clause comes from the file-level import graph. A declared-only model (a Go or Rust repo)
    has none, and the recommendation must degrade to the general advice rather than to a half-sentence
    naming nothing."""
    from archagent.evaluate import _seam_advice, _Model
    m = _Model(subs=["a"], files={"a": {"x.go"}}, tier={}, edges={"a": set()}, rev={"a": set()},
               weight={}, service={}, import_graph={}, file_subs={"x.go": {"a"}}, connectors={})
    assert _seam_advice(m, "a") == ""

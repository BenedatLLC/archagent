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
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/ui.py", "from pkg import db\n")     # ui reaches past domain to infra
    _src(cfg, "pkg/db.py", "z = 1\n")
    _sub(cfg, "ui", "# UI\n\n**Tier:** ui\n\n**Covers:** `src/pkg/ui.py`\n")
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


def test_clean_project_has_no_findings(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from pkg import b\n")
    _src(cfg, "pkg/b.py", "x = 1\n")
    _sub(cfg, "a", "# A\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "b", "# B\n\n**Covers:** `src/pkg/b.py`\n")
    assert evaluate(cfg).findings == []

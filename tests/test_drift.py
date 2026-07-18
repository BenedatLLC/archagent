"""archagent drift — the reflexion-diff between architecture/ docs and code."""

import json
import os
import shutil
import subprocess

import pytest

from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import _connectors, find_drift


def test_connectors_parsing():
    assert _connectors("no fields here") is None
    assert _connectors("**Depends-on:** a, b") == {"a": "import", "b": "import"}         # alias, default kind
    assert _connectors("**Depends-on:** a b") == {"a": "import", "b": "import"}          # legacy space form
    assert _connectors("**Connects:** billing via sync-call, utils") == {
        "billing": "sync-call", "utils": "import"}                                        # mixed, default import
    assert _connectors("**Connects:** q via async-event, db via shared-data") == {
        "q": "async-event", "db": "shared-data"}
    assert _connectors("**Connects:** x via bogus-kind") == {"x": "import"}              # unknown kind -> import
    # Connects takes precedence over a Depends-on alias in the same doc
    assert _connectors("**Connects:** a via async-event\n**Depends-on:** z") == {"a": "async-event"}


def _repo(tmp):
    (tmp / "src" / "pkg").mkdir(parents=True)
    (tmp / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp / "src" / "pkg" / "b.py").write_text("y = 2\n")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _doc(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / name).write_text(text)


def test_dangling_reference_flags_missing_only(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nUses `src/pkg/a.py` and `src/pkg/gone.py`.\n")
    r = find_drift(cfg)
    missing = [ref for _, ref in r.dangling]
    assert "src/pkg/gone.py" in missing
    assert "src/pkg/a.py" not in missing


def test_resolves_bare_and_subpath_refs(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nSee `a.py` and `pkg/b.py` — both real.\n")
    assert find_drift(cfg).dangling == []


def test_non_code_backticks_are_ignored(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nRun `check`, see `../invariants.md`, call `st.lists`.\n")
    assert find_drift(cfg).dangling == []


def test_covers_glob_matching_nothing_is_dangling(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n**Covers:** `src/pkg/**`\n")       # matches a.py, b.py
    assert find_drift(cfg).dangling == []
    _doc(cfg, "ghost.md", "# Ghost\n\n**Covers:** `src/ghost/**`\n")  # matches nothing
    assert any("src/ghost/**" in ref for _, ref in find_drift(cfg).dangling)


def test_undocumented_gated_on_covers(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n**Covers:** `src/pkg/a.py`\n")  # covers only a.py
    r = find_drift(cfg)
    assert r.covers_declared is True
    assert "src/pkg/b.py" in r.undocumented
    assert "src/pkg/a.py" not in r.undocumented


def test_undocumented_skipped_without_covers(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\nRefs `src/pkg/a.py` and `src/pkg/b.py` but no Covers.\n")
    r = find_drift(cfg)
    assert r.covers_declared is False
    assert r.undocumented == []


def test_json_cli_output(tmp_path):
    from typer.testing import CliRunner

    from archagent.cli import app

    _repo(tmp_path)
    (tmp_path / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nroot_package = "pkg"\nsource_paths = ["src"]\n')
    (tmp_path / "architecture" / "subsystems" / "pkg.md").write_text("# Pkg\n\nUses `src/pkg/gone.py`.\n")

    result = CliRunner().invoke(app, ["drift", "--project", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert set(data) >= {"dangling", "stale", "undocumented", "git_available", "covers_declared"}
    assert any(d["ref"] == "src/pkg/gone.py" for d in data["dangling"])


def test_no_git_skips_stale(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n`src/pkg/a.py`\n")
    r = find_drift(cfg)
    assert r.git_available is False
    assert r.stale == []


def _dep_repo(tmp):
    (tmp / "src" / "pkg").mkdir(parents=True)
    (tmp / "src" / "pkg" / "__init__.py").write_text("")
    (tmp / "src" / "pkg" / "a.py").write_text("from pkg.b import thing\n")  # a -> b
    (tmp / "src" / "pkg" / "b.py").write_text("thing = 1\n")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def test_undeclared_dependency_flagged(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Depends-on:** placeholder\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    r = find_drift(cfg)
    assert ("sa", "sb") in r.undeclared_deps      # a imports b, sa didn't declare sb


def test_declared_dependency_satisfied(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Depends-on:** sb\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    r = find_drift(cfg)
    assert r.undeclared_deps == [] and r.stale_deps == []


def test_stale_dependency_flagged(tmp_path):
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")  # a no longer imports b
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Depends-on:** sb\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    r = find_drift(cfg)
    assert ("sa", "sb") in r.stale_deps and r.undeclared_deps == []


def test_dependency_drift_gated_on_declaration(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n")  # no Depends-on
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    assert find_drift(cfg).undeclared_deps == []


def test_connects_alias_behaves_like_depends_on(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Connects:** sb\n")  # default kind = import
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    r = find_drift(cfg)
    assert r.undeclared_deps == [] and r.stale_deps == []  # a imports b, sb declared via import


def test_sync_call_connector_not_flagged_stale(tmp_path):
    # sa declares a runtime sync-call to sb but does NOT import it — must NOT be "stale" (it's not an import)
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")  # a does not import b
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Connects:** sb via sync-call\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    r = find_drift(cfg)
    assert r.stale_deps == []               # a sync-call is not expected in the import graph
    assert r.undeclared_deps == []


def test_import_kind_connector_still_stale_when_unused(tmp_path):
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")  # a does not import b
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Connects:** sb via import\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    assert ("sa", "sb") in find_drift(cfg).stale_deps  # import-kind is checked against the import graph


def _js_repo(tmp):
    (tmp / "src" / "app").mkdir(parents=True)
    (tmp / "src" / "app" / "a.ts").write_text("import { thing } from './b';\nexport const x = thing;\n")  # a -> b
    (tmp / "src" / "app" / "b.ts").write_text("export const thing = 1;\n")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["ts"],
        python=PythonConfig(root_package=None, source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def test_ts_undeclared_dependency(tmp_path):
    cfg = _js_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/app/a.ts`\n**Depends-on:** placeholder\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/app/b.ts`\n")
    assert ("sa", "sb") in find_drift(cfg).undeclared_deps      # a.ts imports ./b


def test_ts_declared_dependency_satisfied(tmp_path):
    cfg = _js_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/app/a.ts`\n**Depends-on:** sb\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/app/b.ts`\n")
    r = find_drift(cfg)
    assert r.undeclared_deps == [] and r.stale_deps == []


def test_ts_package_json_bin_entrypoint(tmp_path):
    cfg = _js_repo(tmp_path)
    (tmp_path / "package.json").write_text('{"name": "app", "bin": {"mycli": "dist/cli.js"}}')
    _doc(cfg, "sa.md", "# SA\n\nNo mention here.\n")
    assert ("mycli", "dist/cli.js") in find_drift(cfg).undocumented_entrypoints


def test_ts_route_undocumented(tmp_path):
    cfg = _js_repo(tmp_path)
    (tmp_path / "src" / "app" / "routes.ts").write_text("app.get('/widgets', h)\n")
    _doc(cfg, "sa.md", "# SA\n\nno routes mentioned\n")
    assert ("GET", "/widgets") in find_drift(cfg).undocumented_routes


def test_missing_deployment_edge(tmp_path):
    cfg = _dep_repo(tmp_path)  # a.py imports b
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Service:** web\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n**Service:** db\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  web: {}\n  db: {}\n")  # no depends_on
    r = find_drift(cfg)
    assert ("web", "db") in r.missing_deploy_edges   # code needs web->db, compose doesn't wire it


def test_satisfied_deployment_edge(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n**Service:** web\n")
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n**Service:** db\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    depends_on: [db]\n  db: {}\n")
    r = find_drift(cfg)
    assert r.missing_deploy_edges == []


def test_deployment_edge_gated_on_service_mapping(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n")  # no **Service:**
    _doc(cfg, "sb.md", "# SB\n\n**Covers:** `src/pkg/b.py`\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  web: {}\n  db: {}\n")
    r = find_drift(cfg)
    assert r.missing_deploy_edges == [] and r.extra_deploy_edges == []


def test_config_drift_against_manifest(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "src" / "pkg" / "settings.py").write_text(
        "import os\nA = os.getenv('DOC_HOME')\nB = os.environ['SECRET_KEY']\n")
    (tmp_path / ".env.example").write_text("DOC_HOME=/data\nUNUSED_KEY=1\n")
    r = find_drift(cfg)
    assert "SECRET_KEY" in r.undocumented_config     # read in code, not in manifest
    assert "UNUSED_KEY" in r.dangling_config          # declared, never read
    assert "DOC_HOME" not in r.undocumented_config    # in both


def test_service_drift_against_compose(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    image: x\n  worker:\n    image: y\n")
    _doc(cfg, "deployment.md", "# Deploy\n\n**Services:** web, ghost\n")
    r = find_drift(cfg)
    assert "worker" in r.undocumented_services   # in compose, not declared
    assert "ghost" in r.dangling_services         # declared, not in IaC
    assert "web" not in r.undocumented_services   # in both


def test_service_drift_gated_on_declaration(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    image: x\n")
    r = find_drift(cfg)  # no **Services:** declared -> skipped
    assert r.undocumented_services == [] and r.dangling_services == []


def test_config_drift_gated_on_manifest(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "src" / "pkg" / "settings.py").write_text("import os\nA = os.getenv('DOC_HOME')\n")
    # no .env.example and no **Config:** anywhere -> skipped (low-noise)
    r = find_drift(cfg)
    assert r.undocumented_config == [] and r.dangling_config == []


def test_undocumented_entrypoint_flagged(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n\n[project.scripts]\nmytool = "pkg.cli:main"\n')
    _doc(cfg, "pkg.md", "# Pkg\n\nNo mention here.\n")
    assert ("mytool", "pkg.cli:main") in find_drift(cfg).undocumented_entrypoints


def test_documented_entrypoint_not_flagged(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n\n[project.scripts]\nmytool = "pkg.cli:main"\n')
    _doc(cfg, "pkg.md", "# Pkg\n\nThe `mytool` command runs it.\n")
    assert find_drift(cfg).undocumented_entrypoints == []


def test_route_undocumented_without_spec(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "src" / "pkg" / "api.py").write_text("@app.get('/widgets')\ndef w(): ...\n")
    _doc(cfg, "pkg.md", "# Pkg\n\nNothing about routes here.\n")
    assert ("GET", "/widgets") in find_drift(cfg).undocumented_routes


def test_route_documented_not_flagged(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "src" / "pkg" / "api.py").write_text("@app.get('/widgets')\ndef w(): ...\n")
    _doc(cfg, "pkg.md", "# Pkg\n\nThe `/widgets` endpoint lists widgets.\n")
    assert find_drift(cfg).undocumented_routes == []


def test_route_diff_against_openapi_spec(tmp_path):
    cfg = _repo(tmp_path)
    (tmp_path / "src" / "pkg" / "api.py").write_text(
        "@app.get('/widgets')\ndef w(): ...\n@app.post('/gadgets')\ndef g(): ...\n")
    (tmp_path / "openapi.json").write_text('{"paths": {"/widgets": {"get": {}}, "/legacy": {"get": {}}}}')
    r = find_drift(cfg)
    assert r.openapi_spec == "openapi.json"
    assert ("POST", "/gadgets") in r.undocumented_routes    # in code, not in spec
    assert ("GET", "/legacy") in r.dangling_routes           # in spec, not in code
    assert ("GET", "/widgets") not in r.undocumented_routes  # in both


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_stale_doc_detected_via_git(tmp_path):
    cfg = _repo(tmp_path)
    _doc(cfg, "pkg.md", "# Pkg\n\n**Covers:** `src/pkg/**`\n")

    def git(*args, date=None):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, env=env)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "docs+code", date="2020-01-01T00:00:00")
    # code moves on in a later commit; the doc does not
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 2\n")
    git("add", "-A")
    git("commit", "-qm", "code change", date="2021-01-01T00:00:00")

    r = find_drift(cfg)
    assert r.git_available is True
    assert any("pkg.md" in doc for doc, _ in r.stale)

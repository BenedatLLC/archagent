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


def test_drift_honors_custom_arch_dir(tmp_path):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "docs" / "architecture" / "subsystems").mkdir(parents=True)
    cfg = Config(
        project_root=tmp_path, languages=["python"], arch_dir="docs/architecture",
        python=PythonConfig(root_package="pkg", source_paths=["src"]), ts=TSConfig(source_paths=["src"]),
    )
    (cfg.architecture_dir / "subsystems" / "sa.md").write_text("# SA\n\nUses `src/pkg/gone.py`.\n")
    assert "src/pkg/gone.py" in [ref for _, ref in find_drift(cfg).dangling]  # found the doc in docs/architecture


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


# --- issue #1: prose / Mermaid / placeholder must not be parsed as declarations ----------

def test_prose_line_start_is_not_a_declaration(tmp_path):
    # a hand-wrapped sentence beginning with "services." must not become declared services
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n\n"
                       "services. All entry-point scripts run as the same `cli` process; they differ\n")
    r = find_drift(cfg)
    assert r.dangling_services == [] and r.undocumented_services == []


def test_mermaid_config_node_is_not_a_config_key(tmp_path):
    # a lifecycle diagram state named `Configured` must not be read as config keys
    cfg = _dep_repo(tmp_path)
    (tmp_path / ".env.example").write_text("REAL_KEY=1\n")            # manifest → config drift active
    (tmp_path / "src" / "pkg" / "a.py").write_text('import os\nos.getenv("REAL_KEY")\n')  # reads it (not dangling)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n\n"
                       "```mermaid\nstateDiagram-v2\n  Configured --> Ready: FILE_LOCATIONS + Settings.set\n```\n")
    r = find_drift(cfg)
    assert r.dangling_config == [] and r.undocumented_config == []
    assert "FILE_LOCATIONS" not in r.dangling_config and "-->" not in r.dangling_config


def test_connects_none_placeholder_is_not_edges(tmp_path):
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")  # no imports
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/a.py`\n"
                       "**Connects:** _(none — this is the base of the dependency graph)_\n")
    r = find_drift(cfg)
    assert r.stale_deps == [] and r.undeclared_deps == []


def test_covers_data_file_glob_not_dangling(tmp_path):
    # a Covers glob that matches real non-code assets (prompt .md) is legitimate, not dangling
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "prompts").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "prompts" / "sys.md").write_text("prompt\n")
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/pkg/prompts/*.md`\n")
    dangling = [ref for _, ref in find_drift(cfg).dangling]
    assert not any("src/pkg/prompts/*.md" in d for d in dangling)


def test_covers_glob_matching_nothing_still_dangling(tmp_path):
    cfg = _dep_repo(tmp_path)
    _doc(cfg, "sa.md", "# SA\n\n**Covers:** `src/ghost/**`\n")  # matches no file at all
    assert any("src/ghost/**" in ref for _, ref in find_drift(cfg).dangling)


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


def test_connector_kind_mismatch_async_declared_but_sync_code(tmp_path):
    # sa declares billing via async-event, but the code makes a blocking HTTP call to billing-svc
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "a.py").write_text('import requests\nrequests.post("http://billing-svc/pay")\n')
    _doc(cfg, "sa.md", "# SA\n\n**Service:** orders-svc\n\n**Connects:** billing via async-event\n\n**Covers:** `src/pkg/a.py`\n")
    _doc(cfg, "billing.md", "# Billing\n\n**Service:** billing-svc\n\n**Covers:** `src/pkg/b.py`\n")
    r = find_drift(cfg)
    assert ("sa", "billing", "async-event", "sync-call") in r.connector_mismatches


def test_no_mismatch_when_kinds_agree(tmp_path):
    cfg = _dep_repo(tmp_path)
    (tmp_path / "src" / "pkg" / "a.py").write_text('import requests\nrequests.post("http://billing-svc/pay")\n')
    _doc(cfg, "sa.md", "# SA\n\n**Service:** orders-svc\n\n**Connects:** billing via sync-call\n\n**Covers:** `src/pkg/a.py`\n")
    _doc(cfg, "billing.md", "# Billing\n\n**Service:** billing-svc\n\n**Covers:** `src/pkg/b.py`\n")
    assert find_drift(cfg).connector_mismatches == []  # declared sync-call, code does sync-call — agree


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


def test_a_bare_extension_in_prose_is_not_a_file_reference(tmp_path):
    """"the suite is `.ts` only" names no file. Reading it as one produced a dangling finding against a
    document that had referenced nothing."""
    from archagent.drift import _file_refs
    refs = _file_refs("The suite is `.ts` only, and `frontend/scripts/` holds three `.mjs` tools "
                      "alongside `app/main.py`.")
    assert refs == ["app/main.py"]


# --- a subsystem claiming a layer it has no business on (issue #26) ---------------------------------

def test_a_test_only_subsystem_tiered_as_production_is_reported(tmp_path):
    """Four of seven labelled `layer-inversion` findings came from test or migration packages tiered
    `infra` — the bottom rank — so everything they imported read as "upward". The artifact says something
    the code contradicts, which is drift's job rather than a smell."""
    from archagent.drift import _mistiered
    assert _mistiered({"backend/tests/test_api.py"}, "infra") == "infra"
    assert _mistiered({"backend/migrations/env.py"}, "infra") == "infra"


def test_a_subsystem_already_off_the_ladder_is_not_reported(tmp_path):
    """Nothing to correct once the author has said so."""
    from archagent.drift import _mistiered
    assert _mistiered({"backend/tests/test_api.py"}, "test") == ""
    assert _mistiered({"backend/migrations/env.py"}, "migration") == ""


def test_a_subsystem_with_no_tier_is_not_reported(tmp_path):
    from archagent.drift import _mistiered
    assert _mistiered({"backend/tests/test_api.py"}, None) == ""


def test_a_production_subsystem_is_not_reported(tmp_path):
    from archagent.drift import _mistiered
    assert _mistiered({"backend/app/api/routes.py"}, "domain") == ""


def test_a_subsystem_mixing_production_and_test_code_is_not_reported(tmp_path):
    """**Every** covered file must be non-production, not merely most. A subsystem holding production code
    alongside its tests is a production subsystem and belongs on the ladder — flagging it would move the
    false positives rather than remove them."""
    from archagent.drift import _mistiered
    assert _mistiered({"backend/app/svc.py", "backend/tests/test_svc.py"}, "infra") == ""


def test_a_subsystem_covering_nothing_is_not_reported(tmp_path):
    """`all()` over an empty set is True, which would report every doc that declares a tier and covers
    no resolvable files."""
    from archagent.drift import _mistiered
    assert _mistiered(set(), "infra") == ""


def test_a_key_read_only_by_the_deployment_is_not_dangling(tmp_path):
    """Issue #24. `read_config_keys` scans `source_paths`, which is exactly where deployment
    configuration does not live, so a key consumed only by compose came back "declared but never read" —
    true, and not a defect. wardrowbe produced 24 of those at once."""
    from archagent.config import Config, PythonConfig, TSConfig
    from archagent.drift import find_drift
    (tmp_path / "architecture").mkdir()
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("import os\nX = os.getenv('APP_SECRET')\n")
    (tmp_path / "docker-compose.yml").write_text(
        'services:\n  api:\n    ports:\n      - "${BACKEND_PORT:-8000}:8000"\n')
    (tmp_path / "architecture" / "deployment.md").write_text(
        "# Deployment\n\n**Config:** APP_SECRET, BACKEND_PORT, GONE_ENTIRELY\n")
    cfg = Config(project_root=tmp_path, languages=["python"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]),
                 ts=TSConfig(source_paths=["src"]))
    r = find_drift(cfg)
    assert r.dangling_config == ["GONE_ENTIRELY"], r.dangling_config


def test_deployment_keys_suppress_a_dangling_finding_but_do_not_create_an_undocumented_one(tmp_path):
    """Deliberately asymmetric. Compose interpolation picks up image tags and port numbers, so treating
    every one as part of the configuration surface would trade two dozen false dangling findings for two
    dozen false undocumented ones."""
    from archagent.config import Config, PythonConfig, TSConfig
    from archagent.drift import find_drift
    (tmp_path / "architecture").mkdir()
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("import os\nX = os.getenv('APP_SECRET')\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  api:\n    image: app:${RELEASE_TAG}\n")
    (tmp_path / "architecture" / "deployment.md").write_text("# D\n\n**Config:** APP_SECRET\n")
    cfg = Config(project_root=tmp_path, languages=["python"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]),
                 ts=TSConfig(source_paths=["src"]))
    r = find_drift(cfg)
    assert r.undocumented_config == []          # RELEASE_TAG is not reported as undeclared config
    assert r.dangling_config == []

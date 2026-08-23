"""Deployment topology: services extracted from IaC vs a declared list."""

from archagent.deployscan import declared_services, extract_service_edges, extract_services


def test_extract_compose_services(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  web:\n    image: nginx\n    depends_on: [db]\n"
        "  worker:\n    build: .\n"
        "  db:\n    image: postgres\n"
    )
    assert extract_services(tmp_path) == {"web", "worker", "db"}


def test_extract_procfile_and_k8s(tmp_path):
    (tmp_path / "Procfile").write_text("web: gunicorn app\nworker: celery -A app worker\n")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "api.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec: {}\n"
    )
    services = extract_services(tmp_path)
    assert {"web", "worker", "api"} <= services


def test_declared_services_from_doc():
    assert declared_services("# Deploy\n\n**Services:** web, worker, db\n") == {"web", "worker", "db"}
    assert declared_services("# no services line\n") == set()


def test_prose_line_starting_with_services_is_not_a_declaration():
    # issue #1: a hand-wrapped sentence must not become declared services
    doc = "services. All entry-point scripts run as the same `cli` process; they differ only in\n"
    assert declared_services(doc) == set()
    assert declared_services("**Services:** _(none)_\n") == set()


def test_non_k8s_yaml_ignored(tmp_path):
    (tmp_path / "openapi.yaml").write_text("openapi: 3.0.0\npaths: {}\n")  # no apiVersion/kind
    assert extract_services(tmp_path) == set()


def test_extract_compose_depends_on_edges(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  web:\n    depends_on: [db]\n"
        "  worker:\n    depends_on:\n      redis:\n        condition: service_started\n"
        "  db: {}\n  redis: {}\n"
    )
    edges = set(extract_service_edges(tmp_path))
    assert ("web", "db") in edges          # list form
    assert ("worker", "redis") in edges    # long form (map)


# --- environment keys the deployment reads (issue #24) ----------------------------------------------

from archagent.deployscan import deployment_config_keys


def test_a_compose_environment_mapping_names_its_keys(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    environment:\n      DATABASE_URL: postgres://x\n      LOG_LEVEL: info\n")
    assert {"DATABASE_URL", "LOG_LEVEL"} <= deployment_config_keys(tmp_path)


def test_a_compose_environment_list_names_its_keys(tmp_path):
    """compose accepts `- FOO=bar` and a bare `- FOO`; both name the key."""
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    environment:\n      - DATABASE_URL=postgres://x\n      - LOG_LEVEL\n")
    assert {"DATABASE_URL", "LOG_LEVEL"} <= deployment_config_keys(tmp_path)


def test_interpolation_anywhere_in_a_compose_file_counts_as_a_read(tmp_path):
    """`BACKEND_PORT` was reported dangling on wardrowbe and appears only in a port mapping — not in an
    environment block at all. A structural scan alone would still miss it."""
    (tmp_path / "docker-compose.yml").write_text(
        'services:\n  api:\n    image: app:${TAG}\n    ports:\n      - "${BACKEND_PORT:-8000}:8000"\n')
    keys = deployment_config_keys(tmp_path)
    assert "BACKEND_PORT" in keys and "TAG" in keys


def test_a_dockerfile_env_and_arg_name_their_keys(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM x\nARG BUILD_MODE\nENV APP_HOME=/srv\nENV LOG_LEVEL info\n")
    assert {"BUILD_MODE", "APP_HOME", "LOG_LEVEL"} <= deployment_config_keys(tmp_path)


def test_a_kubernetes_env_list_names_its_keys(tmp_path):
    (tmp_path / "deploy.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec:\n  template:\n    spec:\n"
        "      containers:\n        - name: api\n          env:\n            - name: DATABASE_URL\n"
        "              value: postgres://x\n")
    assert "DATABASE_URL" in deployment_config_keys(tmp_path)


def test_a_github_actions_env_mapping_is_not_read_as_kubernetes(tmp_path):
    """`env:` in a workflow is a mapping; in a pod spec it is a list of `{name, value}`. Walking every
    `env:` regardless would pull CI variables into the deployment's configuration surface."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("on: push\nenv:\n  CI_ONLY_TOKEN: abc\njobs: {}\n")
    assert "CI_ONLY_TOKEN" not in deployment_config_keys(tmp_path)


def test_lowercase_and_short_names_are_not_treated_as_env_keys(tmp_path):
    """`${tag}` and `$ID` are not environment keys by convention, and accepting them would drag in
    template placeholders from every compose file."""
    (tmp_path / "docker-compose.yml").write_text("services:\n  api:\n    image: app:${tag}-$ID\n")
    keys = deployment_config_keys(tmp_path)
    assert "tag" not in keys and "ID" not in keys


def test_a_repo_with_no_deployment_files_yields_nothing(tmp_path):
    assert deployment_config_keys(tmp_path) == set()

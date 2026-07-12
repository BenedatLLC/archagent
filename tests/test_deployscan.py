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

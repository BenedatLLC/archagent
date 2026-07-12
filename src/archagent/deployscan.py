"""Deployment topology — the services the system deploys, read from IaC (static, no execution).

Extracts service names from docker-compose, `Procfile`, and Kubernetes manifests, and the declared
`**Services:**` list from the architecture docs. `drift` reports services found in IaC but not
declared (undocumented) and declared but not found (dangling), gated on a declaration existing.

(Service dependency edges — compose `depends_on` vs subsystem `Depends-on` — are a planned next step.)
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv"}
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
_K8S_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job", "Service", "Pod", "ReplicaSet"}
_SERVICES_DOC = re.compile(r"^\s*\*{0,2}Services:?\*{0,2}\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_PROC_LINE = re.compile(r"^([A-Za-z0-9_-]+):\s*\S", re.MULTILINE)


def extract_services(root: Path) -> set[str]:
    return _from_compose(root) | _from_procfile(root) | _from_k8s(root)


def extract_service_edges(root: Path) -> list[tuple[str, str]]:
    """`(service, depends_on)` edges from docker-compose `depends_on` (list or long form)."""
    edges: list[tuple[str, str]] = []
    for name in _COMPOSE_NAMES:
        for p in _find(root, name):
            data = _load(p)
            svc = data.get("services") if isinstance(data, dict) else None
            if not isinstance(svc, dict):
                continue
            for sname, sconf in svc.items():
                if not isinstance(sconf, dict):
                    continue
                dep = sconf.get("depends_on")
                deps = list(dep.keys()) if isinstance(dep, dict) else (dep if isinstance(dep, list) else [])
                edges += [(sname, d) for d in deps if isinstance(d, str)]
    return edges


def services_without_healthcheck(root: Path) -> list[str]:
    """Compose services that declare no `healthcheck` (sorted). Empty if no compose file / no services."""
    missing: list[str] = []
    seen: set[str] = set()
    for name in _COMPOSE_NAMES:
        for p in _find(root, name):
            data = _load(p)
            svc = data.get("services") if isinstance(data, dict) else None
            if not isinstance(svc, dict):
                continue
            for sname, sconf in svc.items():
                if sname in seen:
                    continue
                seen.add(sname)
                if not (isinstance(sconf, dict) and sconf.get("healthcheck")):
                    missing.append(sname)
    return sorted(missing)


def declared_services(doc_text: str) -> set[str]:
    out: set[str] = set()
    for m in _SERVICES_DOC.finditer(doc_text):
        out.update(s.strip().strip("`") for s in re.split(r"[,\s]+", m.group(1).strip()) if s.strip())
    return out


def _find(root: Path, name: str) -> list[Path]:
    return [p for p in root.rglob(name) if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts)]


def _from_compose(root: Path) -> set[str]:
    services: set[str] = set()
    for name in _COMPOSE_NAMES:
        for p in _find(root, name):
            data = _load(p)
            svc = data.get("services") if isinstance(data, dict) else None
            if isinstance(svc, dict):
                services.update(svc.keys())
    return services


def _from_procfile(root: Path) -> set[str]:
    p = root / "Procfile"
    if not p.exists():
        return set()
    try:
        return set(_PROC_LINE.findall(p.read_text()))
    except OSError:
        return set()


def _from_k8s(root: Path) -> set[str]:
    if yaml is None:
        return set()
    services: set[str] = set()
    for ext in ("*.yaml", "*.yml"):
        for p in _find(root, ext):
            if p.name in _COMPOSE_NAMES:
                continue
            for doc in _load_all(p):
                if not isinstance(doc, dict) or "apiVersion" not in doc:
                    continue
                if doc.get("kind") in _K8S_KINDS:
                    name = (doc.get("metadata") or {}).get("name")
                    if isinstance(name, str):
                        services.add(name)
    return services


def _load(p: Path):
    if yaml is None:
        return None
    try:
        return yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError):
        return None


def _load_all(p: Path):
    if yaml is None:
        return []
    try:
        return list(yaml.safe_load_all(p.read_text()))
    except (OSError, yaml.YAMLError):
        return []

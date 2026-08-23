"""Deployment topology — the services the system deploys, read from IaC (static, no execution).

Extracts service names from docker-compose, `Procfile`, and Kubernetes manifests, and the declared
`**Services:**` list from the architecture docs. `drift` reports services found in IaC but not
declared (undocumented) and declared but not found (dangling), gated on a declaration existing.

(Service dependency edges — compose `depends_on` vs subsystem `Depends-on` — are a planned next step.)
"""

from __future__ import annotations

import re
from pathlib import Path

from .mdutil import is_empty_value

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

_SKIP_DIRS = {".git", ".archagent", "__pycache__", "node_modules", ".venv"}
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
_K8S_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job", "Service", "Pod", "ReplicaSet"}
# require the bold `**Services:**` form so a sentence starting with "services" isn't read as a manifest (issue #1)
_SERVICES_DOC = re.compile(r"^\s*\*\*\s*Services\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
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


def declared_services(doc_text: str) -> set[str]:
    out: set[str] = set()
    for m in _SERVICES_DOC.finditer(doc_text):
        if is_empty_value(m.group(1)):
            continue
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


# --- environment keys the DEPLOYMENT reads (issue #24) --------------------------------------

#: `${VAR}`, `${VAR:-default}`, `$VAR` — compose interpolation, and the same syntax in an entrypoint.
_INTERP = re.compile(r"\$\{([A-Z][A-Z0-9_]{2,})(?::[-?+][^}]*)?\}|\$([A-Z][A-Z0-9_]{2,})\b")
#: `ENV FOO=bar`, `ENV FOO bar`, `ARG FOO`, `ARG FOO=bar` — Dockerfile, one key per directive.
_DOCKER_ENV = re.compile(r"^\s*(?:ENV|ARG)\s+([A-Z][A-Z0-9_]{2,})", re.MULTILINE)
_DOCKERFILE_NAMES = ("Dockerfile", "Dockerfile.*", "*.Dockerfile")


def deployment_config_keys(root: Path) -> set[str]:
    """Environment keys the *deployment* consumes, as distinct from the ones application code reads.

    `read_config_keys` scans the configured `source_paths`, which is where application code lives and is
    exactly where deployment configuration does not. So a key consumed only by a compose file, a
    container entrypoint or a reverse proxy read as *declared but never read* — accurate, and not a
    defect. On wardrowbe that was 24 findings at once, every one of them correct: `BACKEND_PORT` appears
    only in `docker-compose.yml`, and `LOCAL_DNS` appears nowhere under the source paths at all.

    Twenty-four correct declarations reported as suspect invites a reader to delete an accurate manifest,
    and buries the finding that matters — a key nothing reads *anywhere*.

    Four sources, all files the tool already opens for other questions. Deliberately **not** reverse-proxy
    configs or systemd units: wardrowbe has both and they are a long tail.
    """
    keys: set[str] = set()
    for name in _COMPOSE_NAMES:
        for p in _find(root, name):
            keys |= _keys_in_compose(p)
    for pattern in _DOCKERFILE_NAMES:
        for p in _find(root, pattern):
            keys |= set(_DOCKER_ENV.findall(_read(p)))
            keys |= _interpolated(_read(p))
    keys |= _keys_in_k8s(root)
    return keys


def _read(p: Path) -> str:
    try:
        return p.read_text()
    except OSError:
        return ""


def _interpolated(text: str) -> set[str]:
    return {a or b for a, b in _INTERP.findall(text)}


def _keys_in_compose(p: Path) -> set[str]:
    """Both halves of a compose file's environment surface.

    The raw text carries `${VAR}` interpolation, which is a *read* wherever it appears — in a port
    mapping, an image tag, a volume path. The parsed structure carries `environment:` keys, which the
    interpolation scan misses when the value is a literal (`environment: [PORT=8080]` names `PORT` and
    interpolates nothing).
    """
    keys = _interpolated(_read(p))
    data = _load(p)
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict):
        return keys
    for svc in services.values():
        if isinstance(svc, dict):
            keys |= _env_names(svc.get("environment"))
    return keys


def _env_names(env) -> set[str]:
    """compose accepts a mapping (`FOO: bar`) or a list (`- FOO=bar`, `- FOO`). Both name the key."""
    if isinstance(env, dict):
        return {k for k in env if isinstance(k, str)}
    if isinstance(env, list):
        return {str(e).split("=", 1)[0].strip() for e in env if isinstance(e, (str, int))}
    return set()


def _keys_in_k8s(root: Path) -> set[str]:
    """`env:` names and `envFrom:` sources in a pod spec, at any nesting depth.

    Walked generically rather than by path. A key is named the same way in a Deployment, a CronJob and a
    bare Pod, and the paths to the pod spec differ in every one of them.
    """
    keys: set[str] = set()
    if yaml is None:
        return keys
    for ext in ("*.yaml", "*.yml"):
        for p in _find(root, ext):
            if p.name in _COMPOSE_NAMES:
                continue
            for doc in _load_all(p):
                _walk_env(doc, keys)
    return keys


def _walk_env(node, keys: set[str]) -> None:
    if isinstance(node, dict):
        env = node.get("env")
        if isinstance(env, list):
            for e in env:
                if isinstance(e, dict) and isinstance(e.get("name"), str):
                    keys.add(e["name"])
        for v in node.values():
            _walk_env(v, keys)
    elif isinstance(node, list):
        for v in node:
            _walk_env(v, keys)

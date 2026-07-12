"""`archagent evaluate` — judge the captured architecture for SYSTEM-LEVEL smells.

Where `drift` asks "does the model still match the code?" and `check` enforces declared invariants,
`evaluate` asks "is the architecture *itself* healthy?" It computes deterministic **candidate signals**
at the subsystem / service / tier level (never class/inheritance shapes) that the `/archagent-evaluate`
skill then judges in context, clusters to roots, and turns into prioritized recommendations.

Grounded in the smell literature (see research/architecture-agent/evaluate-design.md): Arcan's static
formulas (instability `I = Ce/(Ca+Ce)`, `DoUD`, cycle-shape severity), Garcia's model-level smells, and
Taibi's microservice harm ranking. This module is **regime A only** — pure static, from the model + the
structure graph archagent already builds. Git co-change (regime B) and the datastore map (group A) come
in later phases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .datamap import store_touches, table_defs
from .deployscan import extract_service_edges, services_without_healthcheck
from .drift import (
    _covers_globs,
    _depends_on,
    _git_available,
    _glob_files,
    _import_graph,
    _is_subsystem,
    _service_of,
    _source_files,
)

# --- tunable thresholds (documented defaults; the literature's starting points) ------------
HUB_DEGREE = 3          # a subsystem depended-on by >= this many AND depending on >= this many => hub
SIZE_SHARE = 0.35       # a subsystem owning >= this fraction of all covered files => oversized
DOUD_THRESHOLD = 0.30   # Arcan: flag Unstable Dependency when bad/total dependencies >= this
_EPS = 1e-9

_TIER = re.compile(r"^\s*\*{0,2}Tier:?\*{0,2}\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# higher rank = higher-level layer; allowed dependencies point downward (ui -> domain -> infra)
_TIER_RANK = {
    "ui": 4, "presentation": 4, "frontend": 4, "web": 4, "view": 4,
    "api": 3, "app": 3, "application": 3, "interface": 3, "controller": 3, "handler": 3,
    "domain": 2, "service": 2, "core": 2, "business": 2, "logic": 2, "usecase": 2,
    "infra": 1, "infrastructure": 1, "data": 1, "persistence": 1, "storage": 1, "db": 1, "adapter": 1,
}

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?\b")
_URL_WITH_PORT = re.compile(r"https?://([A-Za-z0-9._-]+):\d{2,5}", re.IGNORECASE)  # explicit :port only
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org", "::1"}
_COMMENT_STARTS = ("#", "//", "*", '"""', "'''")


@dataclass
class Finding:
    sign: str            # stable id, e.g. "god-component"
    group: str           # "A" | "B" | "C" | "D"
    severity: str        # "low" | "med" | "high"
    title: str           # human-readable sign name
    subjects: list[str]  # subsystems / services / files involved
    detail: str          # the evidence / metric
    recommendation: str
    regime: str = "static"     # "static" | "history"
    confidence: str = "med"    # "low" | "med" | "high"


@dataclass
class EvaluationResult:
    findings: list[Finding] = field(default_factory=list)
    tier_declared: bool = False
    git_available: bool = False

    @property
    def any(self) -> bool:
        return bool(self.findings)

    def by_group(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for f in sorted(self.findings, key=lambda x: (_SEV_ORDER[x.severity], x.group), reverse=True):
            out.setdefault(f.group, []).append(f)
        return out


_SEV_ORDER = {"low": 0, "med": 1, "high": 2}


# --- subsystem model (reuses drift.py's parsing + graph builders) -------------------------

@dataclass
class _Model:
    subs: list[str]                       # subsystem names
    files: dict[str, set[str]]            # subsystem -> covered files
    tier: dict[str, str]                  # subsystem -> declared tier (if any)
    edges: dict[str, set[str]]            # subsystem -> subsystems it depends on
    rev: dict[str, set[str]]              # subsystem -> subsystems that depend on it
    weight: dict[tuple[str, str], int]    # (a, b) -> number of underlying file-import edges
    service: dict[str, str]               # subsystem -> deployment service (**Service:**), if declared
    import_graph: dict[str, set[str]]     # file -> internal files it imports
    file_subs: dict[str, set[str]]        # file -> subsystems that cover it

    def file_service(self, f: str) -> str | None:
        """The deployment service a file belongs to, via its subsystem's **Service:** (if any)."""
        for sub in self.file_subs.get(f, ()):
            svc = self.service.get(sub)
            if svc:
                return svc
        return None


def _build_model(config: Config) -> _Model:
    root = config.project_root
    arch = root / "architecture"
    source_files = _source_files(config)
    import_graph = _import_graph(root, config, source_files)

    files: dict[str, set[str]] = {}
    tier: dict[str, str] = {}
    service: dict[str, str] = {}
    if arch.is_dir():
        for doc in sorted(arch.rglob("*.md")):
            if doc.name.endswith("_TEMPLATE.md") or not _is_subsystem(doc, arch):
                continue
            text = doc.read_text()
            covered: set[str] = set()
            for glob in _covers_globs(text):
                covered.update(_glob_files(root, glob))
            files[doc.stem] = covered
            t = _tier_of(text)
            if t:
                tier[doc.stem] = t
            svc = _service_of(text)
            if svc:
                service[doc.stem] = svc

    file_subs: dict[str, set[str]] = {}
    for name, fs in files.items():
        for f in fs:
            file_subs.setdefault(f, set()).add(name)

    edges: dict[str, set[str]] = {n: set() for n in files}
    rev: dict[str, set[str]] = {n: set() for n in files}
    weight: dict[tuple[str, str], int] = {}
    for name, fs in files.items():
        for f in fs:
            for tgt in import_graph.get(f, ()):
                for tsub in file_subs.get(tgt, ()):
                    if tsub != name:
                        edges[name].add(tsub)
                        rev[tsub].add(name)
                        weight[(name, tsub)] = weight.get((name, tsub), 0) + 1
    return _Model(list(files), files, tier, edges, rev, weight, service, import_graph, file_subs)


def _tier_of(text: str) -> str | None:
    m = _TIER.search(text)
    if not m:
        return None
    tok = re.split(r"[,\s]+", m.group(1).strip())[0].strip("`").lower()
    return tok or None


# --- entry point --------------------------------------------------------------------------

def evaluate(config: Config) -> EvaluationResult:
    root = config.project_root
    result = EvaluationResult(git_available=_git_available(root))
    model = _build_model(config)
    result.tier_declared = bool(model.tier)

    result.findings += _god_components(model)
    result.findings += _cycles(model.subs, model.edges, model.weight, "subsystem")
    result.findings += _unstable_dependencies(model)
    result.findings += _tier_violations(model)
    result.findings += _group_a(root, model)  # data & source-of-truth (needs >= 2 services)
    result.findings += _shared_libraries(model)

    # service-level (deployment) static signals
    svc_edges = extract_service_edges(root)
    if svc_edges:
        sedges, sweight = _adjacency(svc_edges)
        result.findings += _cycles(sorted(sedges), sedges, sweight, "service")

    result.findings += _hardcoded_endpoints(config)
    result.findings += _missing_healthchecks(root)
    return result


# --- Group C: God Component --------------------------------------------------------------

def _god_components(model: _Model) -> list[Finding]:
    total = sum(len(fs) for fs in model.files.values())
    out: list[Finding] = []
    for name in model.subs:
        fan_in = len(model.rev[name])
        fan_out = len(model.edges[name])
        share = (len(model.files[name]) / total) if total else 0.0
        is_hub = fan_in >= HUB_DEGREE and fan_out >= HUB_DEGREE
        # size-share is only meaningful once there are several subsystems to compare against
        is_big = share >= SIZE_SHARE and len(model.subs) >= 4
        if not (is_hub or is_big):
            continue
        sev = "high" if (is_hub and is_big) else "med"
        bits = []
        if is_hub:
            bits.append(f"fan-in {fan_in}, fan-out {fan_out}")
        if is_big:
            bits.append(f"{len(model.files[name])}/{total} files ({share:.0%})")
        out.append(Finding(
            sign="god-component", group="C", severity=sev,
            title="God Component / Blob",
            subjects=[name], detail="; ".join(bits),
            recommendation=("Split this subsystem along its internal seams; extract the most-depended-on "
                            "responsibilities into their own subsystem with a narrow interface."),
            confidence="med",
        ))
    return out


# --- Group C: cyclic dependencies (subsystem + service) ----------------------------------

def _adjacency(pairs: list[tuple[str, str]]) -> tuple[dict[str, set[str]], dict[tuple[str, str], int]]:
    edges: dict[str, set[str]] = {}
    weight: dict[tuple[str, str], int] = {}
    for a, b in pairs:
        edges.setdefault(a, set()).add(b)
        edges.setdefault(b, set())
        weight[(a, b)] = weight.get((a, b), 0) + 1
    return edges, weight


def _cycles(nodes, edges, weight, level: str) -> list[Finding]:
    out: list[Finding] = []
    for comp in _sccs(list(nodes), edges):
        if len(comp) < 2:
            continue
        cs = set(comp)
        n = len(comp)
        e = sum(1 for a in comp for b in edges.get(a, ()) if b in cs)
        max_w = max((weight.get((a, b), 1) for a in comp for b in edges.get(a, ()) if b in cs), default=1)
        shape = _cycle_shape(n, e)
        sev = "high" if n >= 4 else ("med" if n == 3 else ("high" if level == "service" else "med"))
        rec = ("Break the cycle: introduce an interface/mediator one side depends on, invert one "
               "dependency, or merge members that truly belong together.")
        if level == "service":
            rec = ("Cyclic service dependencies prevent independent deployment (distributed monolith). "
                   "Break with async messaging, an API gateway, or by moving the shared concern.")
        out.append(Finding(
            sign=f"cycle-{level}", group="C", severity=sev,
            title=f"Tangled / circular {level} dependency",
            subjects=sorted(comp),
            detail=f"{n}-node {shape} ({e} edges, max weight {max_w})",
            recommendation=rec, confidence="high",
        ))
    return out


def _cycle_shape(n: int, e: int) -> str:
    if n == 2:
        return "tiny cycle"
    if e >= n * (n - 1):
        return "clique"
    if e == n:
        return "circle"
    return "tangle"


def _sccs(nodes: list[str], edges: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's strongly-connected components (iterative, so deep graphs don't blow the stack)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root_node in nodes:
        if root_node in index:
            continue
        work: list[tuple[str, int]] = [(root_node, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            succs = sorted(edges.get(node, ()))
            for j in range(pi, len(succs)):
                w = succs[j]
                if w not in index:
                    work[-1] = (node, j + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if w in on_stack:
                    low[node] = min(low[node], index[w])
            if recursed:
                continue
            if low[node] == index[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                result.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return result


# --- Group B (static half): Unstable Dependency ------------------------------------------

def _unstable_dependencies(model: _Model) -> list[Finding]:
    inst: dict[str, float] = {}
    for name in model.subs:
        ce, ca = len(model.edges[name]), len(model.rev[name])
        inst[name] = ce / (ce + ca) if (ce + ca) else 0.0
    out: list[Finding] = []
    for name in model.subs:
        targets = model.edges[name]
        if not targets:
            continue
        bad = sorted(t for t in targets if inst[t] > inst[name] + _EPS)
        doud = len(bad) / len(targets)
        if doud < DOUD_THRESHOLD:
            continue
        sev = "high" if doud >= 0.6 else "med"
        out.append(Finding(
            sign="unstable-dependency", group="B", severity=sev,
            title="Unstable Dependency",
            subjects=[name],
            detail=(f"instability {inst[name]:.2f}; depends on less-stable "
                    f"{', '.join(bad)} (DoUD {doud:.0%})"),
            recommendation=("Depend on abstractions, not on more-volatile subsystems. Introduce a stable "
                            "interface for the volatile targets, or invert the dependency."),
            confidence="med",
        ))
    return out


# --- Group B (static half): Leaky Abstraction / layering ---------------------------------

def _tier_violations(model: _Model) -> list[Finding]:
    out: list[Finding] = []
    for a in model.subs:
        ra = _TIER_RANK.get(model.tier.get(a, ""))
        if ra is None:
            continue
        for b in sorted(model.edges[a]):
            rb = _TIER_RANK.get(model.tier.get(b, ""))
            if rb is None:
                continue
            if ra < rb:  # lower layer depends on higher layer => dependency inversion
                out.append(Finding(
                    sign="layer-inversion", group="B", severity="high",
                    title="Leaky abstraction (layer inversion)",
                    subjects=[a, b],
                    detail=f"{a} ({model.tier[a]}) depends up on {b} ({model.tier[b]})",
                    recommendation=("A lower layer must not depend on a higher one. Invert with an interface "
                                    "the higher layer implements, or move the shared type down."),
                    confidence="high",
                ))
            elif ra - rb >= 2:  # skips an intermediate layer => leaky detail knowledge
                out.append(Finding(
                    sign="layer-skip", group="B", severity="med",
                    title="Leaky abstraction (layer skip)",
                    subjects=[a, b],
                    detail=f"{a} ({model.tier[a]}) reaches past a layer to {b} ({model.tier[b]})",
                    recommendation=("Route through the intermediate layer so low-level detail changes don't "
                                    "ripple up; hide the target behind the adjacent layer's abstraction."),
                    confidence="med",
                ))
    return out


# --- Group A: data & source-of-truth (needs >= 2 services) -------------------------------

def _group_a(root: Path, model: _Model) -> list[Finding]:
    services = set(model.service.values())
    if len(services) < 2:  # single-service repo: none of these smells apply — stay quiet
        return []

    # aggregate datastore touch points to the service level
    defs: dict[str, set[str]] = {}    # table -> services that OWN (declare) it
    uses: dict[str, set[str]] = {}    # store id -> services that touch it (owned + queried + connected)
    all_files = {f for fs in model.files.values() for f in fs}
    for f in all_files:
        svc = model.file_service(f)
        if not svc:
            continue
        for t in table_defs(root, f):
            defs.setdefault(t, set()).add(svc)
        for sid in store_touches(root, f):
            uses.setdefault(sid, set()).add(svc)

    out: list[Finding] = []

    # duplicated source of truth: the same table's schema declared by >= 2 services
    for table in sorted(defs):
        owners = defs[table]
        if len(owners) >= 2:
            out.append(Finding(
                sign="duplicated-source-of-truth", group="A", severity="high",
                title="Unclear single source of truth",
                subjects=sorted(owners), detail=f"table '{table}' is declared by {len(owners)} services",
                recommendation=("Two services own the same entity — the schemas will drift. Make one the "
                                "owner and have the other consume it via an API/event, or split the data."),
                confidence="med",
            ))

    # inappropriate service intimacy: a service touches a table another service exclusively owns
    for table in sorted(defs):
        owners = defs[table]
        if len(owners) != 1:
            continue
        owner = next(iter(owners))
        intruders = sorted(uses.get(f"table:{table}", set()) - owners)
        if intruders:
            out.append(Finding(
                sign="service-intimacy", group="A", severity="high",
                title="Inappropriate service intimacy",
                subjects=[*intruders, owner],
                detail=f"{', '.join(intruders)} read '{table}', owned by {owner}",
                recommendation=(f"Reach {owner}'s data through its API/events, not its tables — direct access "
                                "couples the services and lets a schema change break a neighbor."),
                confidence="med",
            ))

    # shared persistency: a store touched by >= 2 services with no single clear owner
    for sid in sorted(uses):
        touchers = uses[sid]
        table = sid[len("table:"):] if sid.startswith("table:") else None
        if table is not None and len(defs.get(table, set())) >= 1:
            continue  # ownership cases are covered by the two signals above
        if len(touchers) >= 2:
            label = table if table is not None else sid[len("store:"):]
            out.append(Finding(
                sign="shared-persistency", group="A", severity="high",
                title="Shared persistency",
                subjects=sorted(touchers), detail=f"{len(touchers)} services share '{label}'",
                recommendation=("Give each service its own store (or a private schema); share data through "
                                "an API/events. A shared datastore couples deploys and hides ownership."),
                confidence="med",
            ))
    return out


def _shared_libraries(model: _Model) -> list[Finding]:
    """An internal module imported by files from >= 2 different services couples their releases."""
    services = set(model.service.values())
    if len(services) < 2:
        return []
    importers_of: dict[str, set[str]] = {}  # imported file -> services importing it
    for f, targets in model.import_graph.items():
        svc = model.file_service(f)
        if not svc:
            continue
        for tgt in targets:
            importers_of.setdefault(tgt, set()).add(svc)
    out: list[Finding] = []
    for tgt, svcs in sorted(importers_of.items()):
        owner = model.file_service(tgt)
        cross = svcs - ({owner} if owner else set())
        if len(svcs) >= 2 and cross:
            out.append(Finding(
                sign="shared-library", group="A", severity="med",
                title="Shared library across services",
                subjects=sorted(svcs), detail=f"{tgt} is imported by {len(svcs)} services",
                recommendation=("A module shared across services forces coordinated releases. Vendor a copy "
                                "for independence, or extract it into its own versioned service/package."),
                confidence="med",
            ))
    return out


# --- Group D: hard-coded endpoints -------------------------------------------------------

def _hardcoded_endpoints(config: Config) -> list[Finding]:
    root = config.project_root
    out: list[Finding] = []
    for rel in sorted(_source_files(config)):
        try:
            text = (root / rel).read_text()
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            hit = _endpoint_in(line)
            if hit:
                out.append(Finding(
                    sign="hardcoded-endpoint", group="D", severity="med",
                    title="Hard-coded endpoint",
                    subjects=[f"{rel}:{lineno}"],
                    detail=hit,
                    recommendation=("Move the address to config / service discovery so it isn't pinned to one "
                                    "environment (a barrier to local development and relocation)."),
                    confidence="high",
                ))
    return out


def _endpoint_in(line: str) -> str | None:
    """A hard-coded *service* endpoint: an IP literal, or a host with an explicit port. Public API
    URLs without a port (api.openai.com, arxiv.org) are normal references, not this smell."""
    if line.lstrip().startswith(_COMMENT_STARTS):
        return None
    for m in _IPV4.finditer(line):
        host = m.group(0).split(":")[0]
        if host not in _LOCAL_HOSTS and not host.startswith(("0.", "127.")):
            return m.group(0)
    for m in _URL_WITH_PORT.finditer(line):
        if m.group(1).lower() not in _LOCAL_HOSTS:
            return m.group(0)
    return None


# --- Group D: missing healthchecks -------------------------------------------------------

def _missing_healthchecks(root: Path) -> list[Finding]:
    missing = services_without_healthcheck(root)
    return [
        Finding(
            sign="no-healthcheck", group="D", severity="low",
            title="Service without a healthcheck",
            subjects=[svc], detail="no healthcheck in docker-compose",
            recommendation=("Add a healthcheck so orchestration and dependents can tell when the service is "
                            "ready — a prerequisite for reliable startup ordering and observability."),
            confidence="high",
        )
        for svc in missing
    ]

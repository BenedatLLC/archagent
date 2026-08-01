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

from .cochange import mine_cochange, tree_newer_than
from .config import Config
from .connscan import sync_call_targets
from .datamap import store_touches, table_defs
from .deployscan import extract_service_edges
from .dupdecide import find_decisions, find_enum_escapes, language_of, type_checked
from .history import HistoryProfile, history_profile
from .hotspots import MAX_REPORTED, find_hotspots
from .mdutil import strip_code_fences
from .obsscan import scan as _obs_scan
from .drift import (
    _SYNC_KINDS,
    _connectors,
    _covers_globs,
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
COCHANGE_THR = 4        # subsystems co-changing >= this many times are coupled (Mo/Cai/Kazman default)
IMPACT_MIN = 3          # an interface depended on by >= this many subsystems has real impact scope
UNSTABLE_DEPENDENTS_MIN = 2  # ... and co-changing with >= this many of them => unstable interface
DECISION_MIN_CHURN = 2  # mean commits per involved file; below this the duplication isn't costing anything
MAX_DECISIONS = 10      # candidates are for a person to triage, not an inventory to work through
_EPS = 1e-9

_TIER = re.compile(r"^\s*\*\*\s*Tier\s*:?\s*\*\*\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
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
    history_analyzed: int = 0  # commits mined for co-change (0 = regime B not run)
    # Coverage of the evaluation itself: which signal families were INACTIVE and why (a group that emits
    # zero findings for lack of metadata is indistinguishable, from the count alone, from a clean one).
    inactive: list[tuple[str, str]] = field(default_factory=list)  # (family label, reason)
    # History hygiene (regime B): so a reader knows whether to trust the co-change signals.
    history_ran: bool = False
    commits_seen: int = 0          # non-merge commits in the window
    bulk_skipped: int = 0          # commits skipped as bulk (mass rename/reformat)
    conventional_pct: int = 0      # share of subjects following Conventional Commits
    history_cautions: list[str] = field(default_factory=list)
    # Signal families whose output was capped. A ranked top-10 read as a complete inventory is the
    # difference between "10 problems" and "10 of 41 problems" — never let that be invisible.
    truncated: list[tuple[str, int, int]] = field(default_factory=list)  # (family, shown, found)
    # The learned per-project bug-fix recognizer the history checks ran with (see history.py).
    history_profile: "HistoryProfile | None" = None
    mining_failed: bool = False    # the git log walk errored or timed out; every history signal is void

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
    connectors: dict[tuple[str, str], str]  # declared (a, b) -> connector kind (**Connects:**)

    def file_service(self, f: str) -> str | None:
        """The deployment service a file belongs to, via its subsystem's **Service:** (if any)."""
        for sub in self.file_subs.get(f, ()):
            svc = self.service.get(sub)
            if svc:
                return svc
        return None


def _build_model(config: Config) -> _Model:
    root = config.project_root
    arch = config.architecture_dir
    source_files = _source_files(config)
    import_graph = _import_graph(root, config, source_files)

    files: dict[str, set[str]] = {}
    tier: dict[str, str] = {}
    service: dict[str, str] = {}
    connectors: dict[tuple[str, str], str] = {}
    if arch.is_dir():
        for doc in sorted(arch.rglob("*.md")):
            if doc.name.endswith("_TEMPLATE.md") or not _is_subsystem(doc, arch):
                continue
            text = strip_code_fences(doc.read_text())  # Mermaid/code can't declare metadata (issue #1)
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
            for target, kind in (_connectors(text) or {}).items():
                connectors[(doc.stem, target)] = kind

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
    return _Model(list(files), files, tier, edges, rev, weight, service, import_graph, file_subs, connectors)


def _tier_of(text: str) -> str | None:
    m = _TIER.search(text)
    if not m:
        return None
    tok = re.split(r"[,\s]+", m.group(1).strip())[0].strip("`").lower()
    return tok or None


# --- entry point --------------------------------------------------------------------------

def evaluate(config: Config, history: bool = True, since: str | None = None,
             until: str | None = None) -> EvaluationResult:
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

    # regime B — git history. Subsystem co-change (shotgun surgery, unstable interface) needs subsystems;
    # the per-file signals below do not, so the miner runs whenever there's a git repo.
    cc = None
    if history and result.git_available:
        profile = history_profile(root, config.architecture_dir, until=until)
        result.history_profile = profile
        cc = mine_cochange(root, model.file_subs, since=since, until=until, fix_re=profile.matcher())
        result.history_ran = True
        result.history_analyzed = cc.commits_analyzed
        result.commits_seen = cc.commits_seen
        result.bulk_skipped = cc.bulk_skipped
        result.mining_failed = cc.mining_failed
        result.conventional_pct = cc.conventional_pct
        result.history_cautions = _history_cautions(cc) + list(profile.cautions)
        if cc.mining_failed:
            result.history_cautions.insert(0, (
                "the git history walk FAILED (timeout or git error) — every history-based signal is "
                "silent for that reason, not because the repository is clean. Re-run; if it persists, "
                "narrow the window with --since."))
        if until and tree_newer_than(root, until):
            # The one failure this whole option invites: history bounded, tree not. Nothing in the output
            # looks wrong — the complexity numbers and branch values just describe code that did not exist
            # in the window being mined.
            result.history_cautions.insert(0, (
                f"history is bounded to {until} but the checked-out tree is newer — the file-content "
                "checks are reading present-day code against past history. Check out the revision you "
                "mean to evaluate (`git worktree add`), or drop --until."))
        if model.subs:
            result.findings += _cochange_smells(model, cc)
        result.findings += _change_prone_files(config, cc, profile, result)
        result.findings += _scattered_truth(config, model, cc, result)

    # The enum-escape check is a pure code scan — the owner is declared, not inferred from history — so
    # unlike the two above it runs with no git at all. Churn only orders the results when it is there.
    result.findings += _enum_escapes(config, cc, result)

    # service-level (deployment) static signals
    svc_edges = extract_service_edges(root)
    if svc_edges:
        sedges, sweight = _adjacency(svc_edges)
        result.findings += _cycles(sorted(sedges), sedges, sweight, "service")

    # connector-typed edge signals (declared **Connects:** kinds + inferred sync-call edges)
    result.findings += _connector_signals(root, model)

    result.findings += _hardcoded_endpoints(config)
    result.findings += _observability(root, model)

    result.inactive = _coverage(model, result, history_requested=history)
    return result


# --- coverage of the evaluation itself (which families were inactive, and why) -------------

_HISTORY_MIN = 20   # below this many analyzed commits, co-change signals are thin
_BULK_PCT_WARN = 25  # skipping this share of commits as bulk means the history dilutes the signal
_CONVENTIONAL_WARN = 50  # below this share of conventional subjects, history discipline is mixed


def _coverage(model: _Model, result: "EvaluationResult", history_requested: bool) -> list[tuple[str, str]]:
    """Which signal families produced no findings because their required metadata is absent — reported so
    'zero findings' is never silently read as 'clean here'. Only inactive families are returned."""
    inactive: list[tuple[str, str]] = []
    services = {s for s in model.service.values() if s}
    tiers = {t for t in model.tier.values() if t}

    if len(services) < 2:
        reason = (f"needs **Service:** on ≥2 subsystems ({len(services)} declared) — data ownership, "
                  "distributed-monolith, and cross-service tracing are all skipped")
        inactive.append(("A — data & source-of-truth / cross-service", reason))
    if len(tiers) < 2:
        inactive.append(("B — layering (leaky abstraction)",
                         f"needs **Tier:** on ≥2 subsystems ({len(tiers)} declared)"))
    if not model.connectors:
        inactive.append(("B/C — connector topology",
                         "no **Connects:** declared (some service edges are still inferred from code)"))
    if not history_requested:
        inactive.append(("B/E/F — git history", "skipped (--no-history)"))
    elif not result.git_available:
        inactive.append(("B/E/F — git history", "git not available"))
    else:
        if getattr(result, "mining_failed", False):
            inactive.append(("B/E/F — git history", "the history walk failed; see the caution above"))
        elif result.history_analyzed == 0:
            inactive.append(("B — subsystem co-change",
                             "no commits mapped to subsystems (declare **Covers:** so files map to "
                             "subsystems); the per-file history checks still ran"))
        prof = result.history_profile
        if prof is not None and not prof.usable:
            inactive.append(("E — bug-fix weighting",
                             "no usable bug-fix commit convention was learned for this repo — "
                             "change-prone files are ranked on total churn only"))
    return inactive


def _history_cautions(cc: "CoChange") -> list[str]:
    """Reasons the co-change signal may be weak, surfaced so a reader doesn't over-trust regime B."""
    out: list[str] = []
    if cc.commits_analyzed < _HISTORY_MIN:
        out.append(f"only {cc.commits_analyzed} commit(s) mapped to subsystems — the *subsystem* "
                   "co-change smells are low-confidence. Per-file churn is unaffected: the "
                   f"change-prone-file and ranking signals still used all {cc.commits_seen} commit(s)")
    if cc.bulk_pct >= _BULK_PCT_WARN:
        out.append(f"{cc.bulk_pct}% of commits skipped as bulk ({cc.bulk_skipped}/{cc.commits_seen}) — "
                   "a mass reformat/regen can dilute the signal")
    if cc.commits_seen and cc.conventional_pct < _CONVENTIONAL_WARN:
        out.append(f"only {cc.conventional_pct}% of commit subjects follow Conventional Commits — "
                   "mixed history discipline")
    return out


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


# --- connector-typed edges (declared **Connects:** kinds) --------------------------------

def _connector_signals(root: Path, model: _Model) -> list[Finding]:
    out: list[Finding] = []

    # Extraneous Adjacent Connector (Garcia): a subsystem pair wired by >= 2 different *declared* connector
    # kinds — the parallel paths cancel each other's guarantees (a sync call *and* an event between the pair).
    kinds_between: dict[frozenset, set[str]] = {}
    for (a, b), kind in model.connectors.items():
        kinds_between.setdefault(frozenset((a, b)), set()).add(kind)
    for pair in sorted(kinds_between, key=sorted):
        kinds = kinds_between[pair]
        if len(kinds) >= 2:
            a, b = sorted(pair)
            out.append(Finding(
                sign="extraneous-adjacent-connector", group="B", severity="med",
                title="Extraneous adjacent connector",
                subjects=[a, b],
                detail=f"{a} ↔ {b} connected by {len(kinds)} kinds: {', '.join(sorted(kinds))}",
                recommendation=("Two connector types between the same pair undercut each other (a synchronous "
                                "call defeats an event's decoupling). Consolidate to one interaction kind."),
                confidence="med",
            ))

    # Distributed monolith: a cycle of *services* with a synchronous connector — they can't deploy
    # independently. Edges come from declared **Connects:** kinds AND sync-call edges inferred from the code
    # (so this fires even with zero declarations). An all-async cycle is event-decoupled → informational.
    svc_edges: dict[str, set[str]] = {}
    svc_kinds: dict[tuple[str, str], set[str]] = {}
    inferred_pairs: set[tuple[str, str]] = set()

    def _add(sa, sb, kind, inferred):
        if sa and sb and sa != sb:
            svc_edges.setdefault(sa, set()).add(sb)
            svc_edges.setdefault(sb, set())
            svc_kinds.setdefault((sa, sb), set()).add(kind)
            if inferred:
                inferred_pairs.add((sa, sb))

    for (a, b), kind in model.connectors.items():
        _add(model.service.get(a), model.service.get(b), kind, False)
    for sa, sb in _inferred_service_edges(root, model):
        _add(sa, sb, "sync-call", True)

    for comp in _sccs(sorted(svc_edges), svc_edges):
        if len(comp) < 2:
            continue
        cs = set(comp)
        cycle_kinds: set[str] = set()
        uses_inferred = False
        for a in comp:
            for b in svc_edges.get(a, ()):
                if b in cs:
                    cycle_kinds |= svc_kinds.get((a, b), set())
                    if (a, b) in inferred_pairs:
                        uses_inferred = True
        synchronous = any(k in _SYNC_KINDS for k in cycle_kinds)
        note = " (inferred from code)" if uses_inferred else ""
        out.append(Finding(
            sign="distributed-monolith", group="C",
            severity="high" if synchronous else "low",
            title="Distributed monolith" if synchronous else "Event-coupled service cycle",
            subjects=sorted(comp),
            detail=f"service cycle via {', '.join(sorted(cycle_kinds))} connector(s){note}",
            recommendation=(
                ("Synchronously-coupled services in a cycle can't deploy independently. Break it with async "
                 "messaging, an API gateway, or by moving the shared concern.")
                if synchronous else
                ("A cycle of event-decoupled services is usually fine — confirm neither side blocks on the "
                 "other so it isn't a hidden synchronous dependency.")),
            confidence="low" if uses_inferred else "med",
        ))
    return out


def _inferred_service_edges(root: Path, model: _Model) -> set[tuple[str, str]]:
    """Cross-service sync-call edges inferred from hard-coded HTTP calls whose host resolves to a known
    subsystem/service name. Conservative — unresolved targets are dropped."""
    names = set(model.subs) | set(model.service.values())
    svc_names = set(model.service.values())
    edges: set[tuple[str, str]] = set()
    for sub in model.subs:
        ssvc = model.service.get(sub)
        if not ssvc:
            continue
        for f in model.files.get(sub, ()):
            for tname in sync_call_targets(root, f, names):
                tsvc = tname if tname in svc_names else model.service.get(tname)
                if tsvc and tsvc != ssvc:
                    edges.add((ssvc, tsvc))
    return edges


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


# --- Group B (history / regime B): co-change smells --------------------------------------

def _cochange_smells(model, cc) -> list[Finding]:
    out: list[Finding] = []

    # shotgun surgery / implicit cross-module dependency: subsystems that co-change often but have
    # no structural dependency between them — a coupling the code doesn't declare.
    seen: set[frozenset] = set()
    for a in model.subs:
        for b in model.subs:
            if a >= b:
                continue
            n = cc.between(a, b)
            if n < COCHANGE_THR:
                continue
            structural = b in model.edges.get(a, set()) or a in model.edges.get(b, set())
            if structural:
                continue  # a declared/real dependency already explains the co-change
            key = frozenset((a, b))
            if key in seen:
                continue
            seen.add(key)
            sev = "high" if n >= 2 * COCHANGE_THR else "med"
            out.append(Finding(
                sign="implicit-coupling", group="B", severity=sev,
                title="Shotgun surgery (implicit cross-module coupling)",
                subjects=[a, b],
                detail=f"{a} and {b} co-change in {n} commits but neither depends on the other",
                recommendation=("A change to one keeps forcing a change to the other with no code link — the "
                                "boundary is in the wrong place. Merge the shared concern, or introduce the "
                                "missing explicit interface between them."),
                regime="history", confidence="med",
            ))

    # unstable interface: a widely-depended-on subsystem that keeps changing with its dependents.
    for s in model.subs:
        dependents = model.rev.get(s, set())
        if len(dependents) < IMPACT_MIN:
            continue
        churny = sorted(d for d in dependents if cc.between(s, d) >= COCHANGE_THR)
        if len(churny) >= UNSTABLE_DEPENDENTS_MIN:
            out.append(Finding(
                sign="unstable-interface", group="B", severity="high",
                title="Unstable interface",
                subjects=[s],
                detail=(f"{len(dependents)} subsystems depend on {s}; it co-changes frequently with "
                        f"{', '.join(churny)}"),
                recommendation=("A high-impact interface that keeps changing forces churn across its "
                                "dependents. Stabilize it: freeze the contract, or split the volatile part "
                                "out from the stable one."),
                regime="history", confidence="med",
            ))
    return out


# --- Group E (history): change-prone complex files ----------------------------------------

def _change_prone_files(config: Config, cc, profile: "HistoryProfile", result=None) -> list[Finding]:
    """Check A — a file that changes constantly *and* is complex, the sign of an abstraction absorbing
    special cases. Per-file, unlike the oversized-subsystem check, and from history rather than structure."""
    root = config.project_root
    spots = find_hotspots(root, _source_files(config), cc.file_commits, cc.file_fix_commits)
    if not spots:
        return []
    thin = cc.commits_seen < _HISTORY_MIN
    if result is not None and len(spots) > MAX_REPORTED:
        result.truncated.append(("E — change-prone complex files", MAX_REPORTED, len(spots)))
    out: list[Finding] = []
    for h in spots[:MAX_REPORTED]:
        # shown whenever a recognizer was learned at all; how much to trust it is the profile's cautions
        fix_note = f", {h.fix_churn} fix-labeled" if profile.fix_patterns else ""
        sev = "high" if h.score >= 0.9 else "med"
        out.append(Finding(
            sign="change-prone-file", group="E", severity=sev,
            title="Change-prone complex file",
            subjects=[h.path],
            detail=(f"{h.churn} commit(s){fix_note}; mean indent {h.complexity} over {h.loc} lines "
                    f"(churn p{h.churn_pct:.0%} × complexity p{h.complexity_pct:.0%})"),
            recommendation=("Changes often and is hard to read — a candidate to refactor or split. Check "
                            "whether it is absorbing special cases that belong behind their own abstraction."),
            regime="history", confidence="low" if thin else "med",
        ))
    return out


# --- Group F (history-ranked): scattered single source of truth ---------------------------

def _scattered_truth(config: Config, model: _Model, cc, result=None) -> list[Finding]:
    """Check B — one decision (a set of domain values) branched on in several files instead of resolved
    once. Found in the code; git history only ranks which duplications actually cost anything."""
    root = config.project_root
    groups = _decision_groups(config, model)
    if not groups:
        return []
    decisions = find_decisions(root, groups, cc.file_commits, cc.file_fix_commits)
    eligible = [d for d in decisions if d.churn / len(d.files) >= DECISION_MIN_CHURN]
    if result is not None and len(eligible) > MAX_DECISIONS:
        result.truncated.append(("F — scattered single source of truth", MAX_DECISIONS, len(eligible)))
    out: list[Finding] = []
    for d in decisions:
        per_file = d.churn / len(d.files)
        if per_file < DECISION_MIN_CHURN:
            continue  # duplicated, but the files sit still — nobody is paying for it yet
        if len(out) >= MAX_DECISIONS:
            break
        shown = ", ".join(d.values[:6]) + (f", +{len(d.values) - 6} more" if len(d.values) > 6 else "")
        others = d.reimplementors
        out.append(Finding(
            sign="scattered-source-of-truth", group="F",
            severity="med" if per_file >= 4 * DECISION_MIN_CHURN else "low",
            title="Scattered single source of truth",
            subjects=[d.owner, *others],
            detail=(f"in {d.subsystem}: {{{shown}}} branched on in {len(d.files)} files; "
                    f"{d.owner} holds {d.owner_coverage:.0%} of the set (likely owner), the rest hold pieces; "
                    f"{d.churn} commit(s) across them, {d.fix_churn} fix-labeled"),
            recommendation=(f"This decision looks re-implemented across {len(others)} file(s) beyond "
                            f"{d.owner}. Check whether they should call the owner instead — or whether this "
                            "is an intended family of implementations behind a shared interface, in which "
                            "case dismiss it."),
            regime="history", confidence="low",
        ))
    return out


def _enum_escapes(config: Config, cc, result=None) -> list[Finding]:
    """The declared-owner half of Check B: an enum is the single source of truth for a set of values,
    and some other file re-decides it by comparing against those values as raw strings."""
    escapes = find_enum_escapes(
        config.project_root, _source_files(config),
        cc.file_commits if cc else None, cc.file_fix_commits if cc else None,
    )
    if result is not None and len(escapes) > MAX_DECISIONS:
        result.truncated.append(("F — enum bypassed by its raw values", MAX_DECISIONS, len(escapes)))
    out: list[Finding] = []
    for e in escapes[:MAX_DECISIONS]:
        where = "; ".join(
            f"{f}:{','.join(str(ln) for ln, _ in e.escapes[f][:3])}" for f in e.files[:4]
        )
        shown = ", ".join(e.values[:6]) + (f", +{len(e.values) - 6} more" if len(e.values) > 6 else "")
        unwrapped = sorted(e.unwrapped)
        cross, same = e.cross_language, e.same_language
        note = (f"; {len(unwrapped)} unwrap it with `.value ==`" if unwrapped else "")
        if cross:
            note += (f"; {len(cross)} of them are {_langs(cross)} while {e.enum} is "
                     f"{e.definer_lang} — no import can cross that boundary")
        out.append(Finding(
            sign="enum-value-escape", group="F",
            severity="med" if unwrapped or len(e.escapes) >= 3 else "low",
            title=("Enum vocabulary duplicated across a language boundary" if cross and not same
                   else "Enum bypassed by its raw values"),
            subjects=[e.definer, *e.files],
            detail=(f"{e.enum} (declared in {e.definer}) is compared as bare strings "
                    f"{{{shown}}} in {len(e.escapes)} other file(s): {where}{note}"),
            recommendation=_escape_advice(e, cross, same),
            # A cross-language escape is the more reliable half of this signal: nothing links the two
            # sides, so there is no compiler or import to explain the match away as coincidence. Every
            # cross-language case in the evaluation pass held up under review.
            regime="static", confidence="med" if (unwrapped or cross) else "low",
        ))
    return out


def _langs(files: list[str]) -> str:
    return "/".join(sorted({language_of(f) or "unknown" for f in files}))


def _escape_advice(e, cross: list[str], same: list[str]) -> str:
    """What to actually do — which differs entirely depending on whether the escapers *could* import
    the enum. Telling a TypeScript file to compare against a Python enum member is not advice."""
    dismissal = ("Dismiss any file reading a value that genuinely arrived serialized (from JSON, a "
                 "database column, a request, a third-party webhook) — comparing that as a string is "
                 "correct.")
    if same and all(type_checked(f) for f in same) and not cross:
        # tsc rejects a comparison between a typed value and a literal outside its type (TS2367), so a
        # stale string here cannot survive a build. What is left is the untyped case, which is worth
        # checking but is a much weaker claim than the same finding in Python.
        return ("TypeScript already rejects a stale literal compared against a typed value (TS2367), so "
                f"this only bites where the compared value arrives untyped — a `string`/`any` field off "
                f"an API response, or an event typed with literal unions rather than {e.enum} itself. "
                f"Confirm that is the case before acting; otherwise the compiler is already the guard. "
                + dismissal)
    in_language = (f"Compare against the {e.enum} member itself, or call the owner's own predicate, so "
                   "adding or renaming a member can't silently leave a stale string behind.")
    across = (f"{e.enum} is {e.definer_lang} and these files are {_langs(cross)}, so they cannot import "
              "it — the second copy of the vocabulary is unavoidable, and nothing on either side will "
              "flag it when the two drift apart. Generate the other language's constants from this enum "
              "(or both from one schema) and compare against those, rather than leaving bare strings "
              "spread across the boundary.")
    if cross and not same:
        return f"{across} {dismissal}"
    if cross:
        return (f"These files re-decide what {e.enum} already owns. For the {len(same)} in "
                f"{e.definer_lang}: {in_language} For the {len(cross)} across the language boundary: "
                f"{across} {dismissal}")
    return f"These files re-decide what {e.enum} already owns. {in_language} {dismissal}"


def _decision_groups(config: Config, model: _Model) -> dict[str, set[str]]:
    """Where to look for a duplicated decision: the declared subsystems, or — when none are declared —
    top-level source directories, so the check still works on a repo with no architecture docs yet."""
    if model.files:
        return {name: fs for name, fs in model.files.items() if fs}
    groups: dict[str, set[str]] = {}
    for rel in _source_files(config):
        parts = rel.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if len(parts) > 1 else ".")
        groups.setdefault(key, set()).add(rel)
    return groups


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


# --- Group D: cross-boundary observability -----------------------------------------------

def _observability(root: Path, model: _Model) -> list[Finding]:
    """Can a request be traced across service boundaries? Needs >= 2 services that actually make
    cross-service calls. Systemic gap (nobody instruments) or per-service gap (a caller with no
    trace/correlation context while others have it)."""
    services = set(model.service.values())
    if len(services) < 2:
        return []

    instrumented: set[str] = set()   # services with a tracing / correlation marker
    calling: set[str] = set()        # services that make outbound cross-service calls
    for f in {f for fs in model.files.values() for f in fs}:
        svc = model.file_service(f)
        if not svc:
            continue
        has_obs, outbound = _obs_scan(root, f)
        if has_obs:
            instrumented.add(svc)
        if outbound:
            calling.add(svc)

    if not calling:  # no cross-service communication seen — can't claim a tracing gap
        return []

    if not instrumented:
        # systemic: services talk to each other but nothing traces or correlates
        return [Finding(
            sign="no-request-tracing", group="D", severity="high",
            title="No request tracing across services",
            subjects=sorted(services),
            detail="services make cross-service calls but no tracing/correlation instrumentation was found",
            recommendation=("Adopt distributed tracing or a propagated correlation ID (e.g. OpenTelemetry, "
                            "or a request-id header threaded through calls) so a request can be followed "
                            "across service boundaries."),
            confidence="med",
        )]

    # per-service gap: a caller with no instrumentation while other services have it
    out: list[Finding] = []
    for svc in sorted(calling - instrumented):
        out.append(Finding(
            sign="trace-chain-gap", group="D", severity="med",
            title="Service breaks the trace chain",
            subjects=[svc],
            detail="makes cross-service calls but carries no trace/correlation context (others do)",
            recommendation=("Propagate the incoming trace/correlation ID on this service's outbound calls "
                            "so requests through it stay traceable end to end."),
            confidence="med",
        ))
    return out



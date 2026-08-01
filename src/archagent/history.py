"""Step 1 — learn *this project's* commit wording (the bug-fix recognizer both history checks lean on).

There is no universal way to spot a bug-fix commit: Django writes `Fixed #12345`, LiteLLM writes
`fix(router): …` (and drifts to `[Fix]`, `Fixes`, bare `fix `), small projects write free-form prose.
Hard-coding one style under-recalls catastrophically on the others — measured at 0% recall on Django's
~16k fix commits and ~40% loss on a repo that *declares* Conventional Commits (see
`research/architecture-agent/feedback/probe-results.md`, probe A). So the recognizer is learned per repo.

The split is the one the rest of `evaluate` uses: **code gathers the evidence, the model judges it.**
`gather_evidence()` is plain and reproducible — commit-guideline docs, a leading-word frequency sample of
real subjects, how well each candidate pattern actually matches, the project's own domain terms.
`infer_profile()` then picks a recognizer deterministically from that evidence, which is what `evaluate`
uses when nothing is cached. The `archagent history-profile` command writes the result to
`.archagent/history-profile.json`, where an agent may sharpen it; a cached profile always wins.

What the recognizer captures is *fix-labeled maintenance*, not pure bugs — Django's `Fixed #NNN` sample was
roughly half real defects and half features/docs/cleanups. That is the intended reading: a file that keeps
generating tickets is the signal, whether or not each ticket was strictly a bug.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .drift import _git

PROFILE_PATH = ".archagent/history-profile.json"
_SUBJECT_SAMPLE = 4000     # subjects sampled to measure candidate patterns
_MIN_SHARE = 0.02          # a candidate must label >= this share of subjects to be believed
_MIN_GAIN = 0.01           # ... and add >= this share of *new* matches over patterns already chosen
_FREEFORM_CEILING = 0.03   # only fall back to the noisy prose matcher below this total coverage
_THIN_HISTORY = 50         # fewer subjects than this and the learned recognizer is a guess

# Candidate recognizers, widest-known style first. Each is tried against this repo's own subjects and kept
# only if it earns its place; none of them is assumed.
_CANDIDATES: list[tuple[str, str]] = [
    # Conventional Commits: `fix:` / `fix(scope):` / `fix!:`
    ("conventional", r"^\s*(?:bug)?fix(?:es|ed)?(?:\([^)]*\))?!?\s*:"),
    # scope-first prose: `router: fix the retry loop`, `evaluate: fixed a false positive`
    ("scoped-verb", r"^\s*[\w./-]+\s*:\s*(?:bug|hot)?fix(?:es|ed)?\b"),
    # bracketed tag: `[Fix]`, `[bugfix]`, `[hotfix] …`
    ("bracket-tag", r"^\s*\[\s*(?:bug|hot)?fix(?:es|ed)?\s*\]"),
    # tracker reference: `Fixed #12345`, `Fixes PROJ-456`. Deliberately *only* the fix verbs. `Refs`,
    # `Closes` and `Resolves` are ticket-lifecycle words that say nothing about the kind of work: on
    # Datasette `closes #N` trails feature and docs commits alike (582 of them, against 353 that the
    # project itself labels `Fix ...`), and including it made the learner pick issue-closing as the
    # repo's "fix" vocabulary. See probe-results.md, evaluation pass.
    ("tracker-ref", r"^\s*(?:fixed|fixes|fix)\b[\s:]*#?(?:[A-Z]+-)?\d+"),
    # leading fix verb with no punctuation convention: `Fix the retry loop`
    ("leading-verb", r"^\s*(?:bug|hot)?fix(?:es|ed)?\b"),
    # trailer anywhere in the subject: `… (fixes #123)` — again fix verbs only, not `closes`/`resolves`
    ("trailer-ref", r"\b(?:fixes|fixed)\s+#\d+"),
    # last resort for free-form histories — noisy, so only used when nothing above matches
    ("free-form", r"\b(?:bug|regression|crash|broken|incorrect|traceback|hotfix)\b"),
]

_GUIDELINE_FILES = (
    "CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING.txt", "CONTRIBUTING",
    "docs/CONTRIBUTING.md", ".github/CONTRIBUTING.md",
    ".github/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md",
    "commitlint.config.js", "commitlint.config.cjs", ".commitlintrc", ".commitlintrc.json",
    ".gitmessage", ".github/commit-template.txt",
    "AGENTS.md", "CLAUDE.md", "README.md",
)
_GUIDELINE_HINT = re.compile(
    r"(commit message|commit-message|conventional commit|commit convention|commit subject|"
    r"^\s*fix\(|Fixed #|ticket|issue number|tracker)",
    re.IGNORECASE | re.MULTILINE,
)
# `**Term** — definition` / `- **Term**: definition` in the architecture docs, i.e. a glossary entry
_GLOSSARY = re.compile(r"^\s*[-*]?\s*\*\*([A-Za-z][\w \-/]{1,40})\*\*\s*[—:-]", re.MULTILINE)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


@dataclass
class HistoryProfile:
    """The learned recognizer plus how much to trust it."""

    style: str = "unknown"                             # label for the dominant commit style
    until: str | None = None                           # the window this was learned over, if bounded
    fix_patterns: list[str] = field(default_factory=list)   # regexes that identify fix-labeled commits
    subjects_sampled: int = 0
    fix_matched: int = 0
    domain_terms: list[str] = field(default_factory=list)
    guideline_sources: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    source: str = "inferred"                           # "inferred" (this module) | "cached" | "model"

    @property
    def fix_share(self) -> float:
        return self.fix_matched / self.subjects_sampled if self.subjects_sampled else 0.0

    @property
    def usable(self) -> bool:
        """Whether the fix-weighted variant of Check A should be trusted at all."""
        return bool(self.fix_patterns) and self.subjects_sampled >= _THIN_HISTORY

    def matcher(self) -> re.Pattern | None:
        """One compiled alternation over the learned patterns, or None if nothing was learned."""
        if not self.fix_patterns:
            return None
        try:
            return re.compile("|".join(f"(?:{p})" for p in self.fix_patterns), re.IGNORECASE)
        except re.error:
            return None

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "until": self.until,
            "fix_patterns": self.fix_patterns,
            "subjects_sampled": self.subjects_sampled,
            "fix_matched": self.fix_matched,
            "fix_share": round(self.fix_share, 4),
            "domain_terms": self.domain_terms,
            "guideline_sources": self.guideline_sources,
            "cautions": self.cautions,
            "source": self.source,
        }


# --- evidence gathering (plain, reproducible — no model) ----------------------------------

def gather_evidence(root: Path, arch_dir: Path | None = None, sample: int = _SUBJECT_SAMPLE,
                    until: str | None = None, since: str | None = None) -> dict:
    """Facts about this repo's commit wording, for `infer_profile` or for a model to judge."""
    subjects = _subjects(root, sample, until, since)
    lead = _leading_words(subjects)
    stats = []
    for name, pattern in _CANDIDATES:
        rx = re.compile(pattern, re.IGNORECASE)
        n = sum(1 for s in subjects if rx.search(s))
        stats.append({
            "name": name, "pattern": pattern, "matches": n,
            "share": round(n / len(subjects), 4) if subjects else 0.0,
        })
    return {
        "subjects_sampled": len(subjects),
        "leading_words": lead[:20],
        "candidate_patterns": stats,
        "examples": subjects[:15],
        "guidelines": _guidelines(root),
        "domain_terms": _domain_terms(arch_dir) if arch_dir else [],
        # the full sample, so inference can re-measure the union of chosen patterns without a second
        # `git log`. Stripped before the evidence is printed — it would swamp the useful part.
        "_subjects": subjects,
    }


def _subjects(root: Path, sample: int, until: str | None = None,
              since: str | None = None) -> list[str]:
    args = ["log", "--no-merges", "-n", str(sample), "--pretty=format:%s"]
    if until:
        args.append(f"--until={until}")
    if since:
        args.append(f"--since={since}")
    out = _git(root, *args)
    return [s for s in (out or "").splitlines() if s.strip()]


def _leading_words(subjects: list[str]) -> list[dict]:
    counts: dict[str, int] = {}
    for s in subjects:
        m = _WORD.search(s)
        if m:
            w = m.group(0).lower()
            counts[w] = counts.get(w, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"word": w, "count": n} for w, n in ordered]


def _guidelines(root: Path) -> list[dict]:
    """Excerpts from files that state the project's commit convention, if any state one."""
    out: list[dict] = []
    for rel in _GUIDELINE_FILES:
        p = root / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        hits = [ln.strip() for ln in lines if _GUIDELINE_HINT.search(ln)]
        if hits:
            out.append({"file": rel, "excerpt": hits[:8]})
    return out


def _domain_terms(arch_dir: Path) -> list[str]:
    """The project's own vocabulary — subsystem names plus glossary entries in the architecture docs.
    A light aid when a model later judges whether a duplicated value set names a real decision."""
    terms: set[str] = set()
    if not arch_dir.is_dir():
        return []
    subs = arch_dir / "subsystems"
    if subs.is_dir():
        terms.update(p.stem for p in subs.glob("*.md") if not p.name.endswith("_TEMPLATE.md"))
    for doc in sorted(arch_dir.rglob("*.md")):
        try:
            text = doc.read_text(errors="replace")
        except OSError:
            continue
        terms.update(m.group(1).strip() for m in _GLOSSARY.finditer(text))
    return sorted(t for t in terms if 2 <= len(t) <= 40)


# --- deterministic inference from the evidence -------------------------------------------

def infer_profile(evidence: dict) -> HistoryProfile:
    """Pick this repo's fix recognizer from the gathered evidence.

    Greedy by *added* coverage: the widest-matching candidate first, then any candidate that labels a
    meaningful slice the chosen ones miss. That is what lets a repo using both `Fixed #123` and bare
    `Fix the thing` end up with both patterns, without a repo that uses neither inheriting either.
    """
    total = evidence.get("subjects_sampled", 0)
    profile = HistoryProfile(subjects_sampled=total)
    profile.domain_terms = list(evidence.get("domain_terms", []))
    profile.guideline_sources = [g["file"] for g in evidence.get("guidelines", [])]
    if not total:
        profile.cautions.append("no commit subjects available — bug-fix weighting is off")
        return profile

    stats = {s["name"]: s for s in evidence.get("candidate_patterns", [])}
    subjects = evidence.get("_subjects") or evidence.get("examples", [])

    ranked = sorted(
        (s for s in stats.values() if s["name"] != "free-form" and s["share"] >= _MIN_SHARE),
        key=lambda s: -s["matches"],
    )
    chosen: list[dict] = []
    covered = 0
    for cand in ranked:
        # a candidate earns its place only by matching commits the already-chosen patterns miss; without
        # this, `tracker-ref` and `leading-verb` (which overlap on `Fixed #123`) would both be kept blindly
        gain = cand["matches"] - covered
        if chosen and gain / total < _MIN_GAIN:
            continue
        chosen.append(cand)
        covered = max(covered, cand["matches"])

    if not chosen:
        free = stats.get("free-form")
        if free and free["share"] >= _FREEFORM_CEILING:
            chosen = [free]
            covered = free["matches"]
            profile.cautions.append(
                "no fix-labeling convention found — falling back to prose keywords, which over-matches")
        else:
            profile.cautions.append(
                "no recognizable bug-fix commit convention — bug-fix weighting is off for this repo")

    profile.fix_patterns = [c["pattern"] for c in chosen]
    profile.style = "+".join(c["name"] for c in chosen) if chosen else "none"
    matcher = profile.matcher()
    # re-measure against the union rather than trusting `covered`, which is only the widest single pattern
    profile.fix_matched = sum(1 for s in subjects if matcher.search(s)) if matcher else 0

    if total < _THIN_HISTORY:
        profile.cautions.append(
            f"thin history — only {total} commit subject(s) sampled; the learned recognizer is a guess")
    if matcher and profile.fix_share > 0.6:
        profile.cautions.append(
            f"{profile.fix_share:.0%} of subjects look like fixes — the recognizer is probably over-matching")
    return profile


# --- cache -------------------------------------------------------------------------------

def load_profile(root: Path) -> HistoryProfile | None:
    """The cached profile, if one was written by `archagent history-profile` (or by an agent)."""
    p = root / PROFILE_PATH
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    patterns = [x for x in data.get("fix_patterns", []) if isinstance(x, str) and _valid(x)]
    return HistoryProfile(
        style=str(data.get("style", "unknown")),
        fix_patterns=patterns,
        subjects_sampled=int(data.get("subjects_sampled") or 0),
        fix_matched=int(data.get("fix_matched") or 0),
        domain_terms=[str(t) for t in data.get("domain_terms", [])],
        guideline_sources=[str(s) for s in data.get("guideline_sources", [])],
        cautions=[str(c) for c in data.get("cautions", [])],
        until=(str(data["until"]) if data.get("until") else None),
        source=str(data.get("source") or "cached"),
    )


def _valid(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def save_profile(root: Path, profile: HistoryProfile) -> Path:
    p = root / PROFILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile.to_dict(), indent=2) + "\n")
    return p


def history_profile(root: Path, arch_dir: Path | None = None, use_cache: bool = True,
                    until: str | None = None, since: str | None = None) -> HistoryProfile:
    """The profile `evaluate` runs with: a cached one if present, otherwise inferred in memory.

    `evaluate` never writes the cache — it stays read-only. `archagent history-profile` is what persists
    a profile (and is where an agent can sharpen the recognizer).

    **A bounded run ignores the cache.** A profile cached from a full-history run was learned from commits
    made after the cutoff, and using it to label commits from before is leakage — small in its effect on
    accuracy, and fatal to a study whose premise is that nothing after the cutoff informs the signal. The
    window is recorded on the profile so a future cache can be matched rather than merely bypassed.
    """
    if use_cache and not (until or since):
        cached = load_profile(root)
        if cached:
            return cached
    profile = infer_profile(gather_evidence(root, arch_dir, until=until, since=since))
    profile.until = until
    return profile

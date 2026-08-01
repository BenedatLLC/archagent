"""Pinned-corpus regression — running the checks against real repositories at fixed revisions.

`test_golden.py` pins behaviour on ~40 hand-written files. It is fast, it runs in CI, and it cannot
notice that a change broke Django. This is the other half: clone a real project at a pinned tag, run
`evaluate` as of that tag, and compare against a recorded expectation.

Two things it deliberately does not do.

**No shallow clone.** `--depth` truncates history, and churn, fix-churn and co-change are all computed
from the full log — a shallow clone would quietly produce different numbers rather than an error. The
cache is a blobless partial clone (`--filter=blob:none`): every commit and tree is present, file *contents*
arrive on demand.

That last part has a cost worth knowing about. The first `git log --name-only` walk over a fresh blobless
clone fetches trees lazily and took 23 seconds on litellm — long enough that the miner's original 30-second
timeout was within reach, and a timeout there produced an *empty history that looked like a clean one*.
`warm_clone` does that walk once at clone time so no measured run pays for it.

**No branch names.** A revision is a tag or a SHA. A branch would make the expectation drift under us,
which is the whole thing this is meant to prevent.

The checkouts under `~/research/architecture-agent/test-repositories` are *not* used: they sit at
arbitrary revisions and are the measurement baseline for the manual corpus pass. This harness clones its
own copies so a result is reproducible on another machine.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

HERE = Path(__file__).parent
MANIFEST = HERE / "corpus_manifest.toml"
EXPECTED_DIR = HERE / "corpus"


def cache_dir() -> Path:
    base = os.environ.get("ARCHAGENT_CORPUS_CACHE")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(xdg) / "archagent" / "corpus"


def load_manifest() -> list[dict]:
    return tomllib.loads(MANIFEST.read_text())["repo"]


def _git(root: Path | None, *args: str, check: bool = True) -> str:
    cmd = ["git"] + (["-C", str(root)] if root else []) + list(args)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def ensure_clone(entry: dict) -> Path:
    """The cached blobless clone for a repository, fetched once and reused."""
    dest = cache_dir() / f"{entry['name']}.git"
    if not (dest / "HEAD").exists() and not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(None, "clone", "--filter=blob:none", "--no-checkout", entry["url"], str(dest))
    if not _rev_present(dest, entry["rev"]):
        _git(dest, "fetch", "--tags", "origin")
    warm_clone(dest, entry["rev"])
    return dest


def warm_clone(clone: Path, rev: str) -> None:
    """Walk the history once from `rev` so the lazy tree fetches happen outside any measured run.

    Warming at one revision is not enough for the defect study, which walks 3000 commits back from a
    cutoff a year earlier than `head` — on a busy repository that is a different set of trees, and the
    miner times out again. So the marker records *which* revisions have been warmed.
    """
    marker = clone / ".archagent-warmed"
    done = set(marker.read_text().split()) if marker.exists() else set()
    sha = _git(clone, "rev-parse", rev, check=False)
    if sha in done:
        return
    _git(clone, "log", "--no-merges", "--name-only", "-n", "3000", "--pretty=format:", rev, check=False)
    marker.write_text("\n".join(sorted(done | {sha})) + "\n")


def _rev_present(clone: Path, rev: str) -> bool:
    try:
        _git(clone, "rev-parse", "--verify", f"{rev}^{{commit}}")
        return True
    except RuntimeError:
        return False


def _write_config(root: Path, entry: dict) -> None:
    paths = entry.get("paths", {})
    langs = ", ".join(f'"{lang}"' for lang in paths)
    body = f"[project]\nlanguages = [{langs}]\n"
    for lang, dirs in paths.items():
        section = "ts" if lang in ("ts", "typescript", "js") else lang
        listed = ", ".join(f'"{d}"' for d in dirs)
        body += f"\n[{section}]\nsource_paths = [{listed}]\n"
    (root / "archagent.toml").write_text(body)


def run_entry(entry: dict, work: Path) -> dict:
    """Check the pinned revision out into `work` and return the projected evaluate result."""
    from test_golden import project   # noqa: E402  (same directory; keeps one projection definition)

    from archagent.config import load_config
    from archagent.evaluate import evaluate

    clone = ensure_clone(entry)
    if work.exists():
        shutil.rmtree(work)
    _git(clone, "worktree", "add", "--detach", str(work), entry["rev"])
    try:
        _write_config(work, entry)
        # `--as-of` from the revision itself: the tree is checked out to match, so the history window and
        # the file contents describe the same moment and no mismatch warning should appear.
        until = _git(clone, "log", "-1", "--format=%cI", entry["rev"])
        result = evaluate(load_config(work), until=until)
        assert not any("checked-out tree is newer" in c for c in result.history_cautions), (
            "the worktree and the history window disagree — the harness checked out the wrong revision")
        return project(result)
    finally:
        _git(clone, "worktree", "remove", "--force", str(work), check=False)


def expectation_path(entry: dict) -> Path:
    return EXPECTED_DIR / f"{entry['name']}.json"


def needs_recording(entry: dict) -> bool:
    """Whether this entry has no expectation yet. Checked *before* any network work: a repository
    declared in the manifest but not yet recorded should cost nothing, not a multi-minute clone that
    ends in a skip."""
    return not expectation_path(entry).exists() and not os.environ.get("ARCHAGENT_UPDATE_CORPUS")


def summarise_diff(expected: dict, actual: dict) -> str:
    """A readable account of what moved. The raw JSON is thousands of lines; a reviewer needs to see
    which findings appeared or vanished, because a *vanished* one is the failure that matters most."""
    def key(f):
        return (f["sign"], f["subjects"][0] if f["subjects"] else "")

    exp = {key(f): f for f in expected.get("findings", [])}
    act = {key(f): f for f in actual.get("findings", [])}
    lines: list[str] = []
    for k in sorted(exp.keys() - act.keys()):
        lines.append(f"  LOST     {k[0]:28} {k[1]}")
    for k in sorted(act.keys() - exp.keys()):
        lines.append(f"  NEW      {k[0]:28} {k[1]}")
    for k in sorted(exp.keys() & act.keys()):
        before, after = exp[k], act[k]
        moved = [
            f"{field}: {before[field]} -> {after[field]}"
            for field in ("severity", "confidence", "values", "subjects")
            if before[field] != after[field]
        ]
        if moved:
            lines.append(f"  CHANGED  {k[0]:28} {k[1]}\n             " + "\n             ".join(moved))
    for section in ("inactive", "truncated", "history"):
        if expected.get(section) != actual.get(section):
            lines.append(f"  {section.upper()}: {expected.get(section)!r}\n        -> {actual.get(section)!r}")
    return "\n".join(lines) or "  (no difference in the projected fields)"


def check_or_update(entry: dict, actual: dict) -> str | None:
    """None if it matches (or was just recorded); otherwise a readable diff."""
    path = expectation_path(entry)
    text = json.dumps(actual, indent=2) + "\n"
    if os.environ.get("ARCHAGENT_UPDATE_CORPUS"):
        EXPECTED_DIR.mkdir(exist_ok=True)
        path.write_text(text)
        return None
    if not path.exists():
        return (f"no expectation recorded for {entry['name']} — run with ARCHAGENT_UPDATE_CORPUS=1 "
                f"to record one")
    expected = json.loads(path.read_text())
    if expected == actual:
        return None
    return summarise_diff(expected, actual)

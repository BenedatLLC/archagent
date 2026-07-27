"""Deterministic fixture repositories for the golden-output tests.

A *builder*, not a committed directory. Two reasons. The checks need real git history, and a directory
committed inside archagent's own repo cannot have its own; and building the history in code makes the
**commit messages** part of the fixture, which matters because the bug with the worst measured impact so
far was in the commit-wording learner, not in either check.

Everything here is deliberately hand-shaped so that each case has a known verdict. `main_repo` carries one
instance of every signal — including the ones that must be *rejected*, which is the half a snapshot of
real output cannot pin. `tracker_repo` exists only to hold a second commit convention.

Dates are pinned so nothing in the output can depend on when the suite ran.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from archagent.config import Config, PythonConfig, TSConfig

STATES = ["initial", "paid", "shipped", "refunded", "cancelled"]
DIALECT = ["autoincrement", "returning", "upsert", "window_functions"]
KEYS = ["ArrowUp", "ArrowDown", "Enter", "Escape"]
MEMBERS = [f"ProviderKind.{m}" for m in ("GITHUB", "GITLAB", "BITBUCKET", "AZURE", "GITEA")]
JOB_STATES = ["queued", "running", "succeeded", "failed", "retrying"]
MODES = ["canary", "bluegreen", "rolling", "direct"]
GRANT = ["authorization_code", "refresh_token", "client_credentials"]
HUES = ["crimson", "cerulean", "chartreuse"]
_EPOCH = 1700000000


def _git(root: Path, *args: str, n: int = 0) -> None:
    stamp = f"{_EPOCH + n * 60} +0000"
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _branches(values, var="s", body="pass"):
    return "".join(f'if {var} == "{v}":\n    {body}\n' for v in values)


def _member_branches(values):
    return "".join(f"if kind == {v}:\n    pass\n" for v in values)


def _pieces(values):
    """Three partial re-implementations, each missing a different value."""
    return [[v for v in values if v != values[i]] for i in range(3)]


def _nested(lines=40, depth=5):
    pad = " " * (depth * 4)
    return "".join(f"{pad}value_{i} = {i}\n" for i in range(lines))


def _flat(lines=40):
    return "".join(f"value_{i} = {i}\n" for i in range(lines))


def _revise(rel: str, text: str, n: int) -> str:
    """The same file, one commit later. A trailing marker changes the content without disturbing the
    branch values or the indentation profile the checks actually measure."""
    mark = "//" if rel.endswith((".ts", ".tsx")) else "#"
    return f"{text}{mark} rev {n}\n"


def _files() -> dict[str, str]:
    """The fixture's source tree. Each block is one labelled case."""
    f: dict[str, str] = {}

    # CONFIRMED duplicated decision: one owner holding the whole set, three files holding pieces.
    f["src/orders/state.py"] = _branches(STATES)
    for name, piece in zip(("api", "report", "email"), _pieces(STATES)):
        f[f"src/orders/{name}.py"] = _branches(piece)

    # INTENDED FAMILY: per-backend adapters branching on the same set by design. The tool cannot tell
    # this from the case above and is not meant to — it surfaces, a reviewer dismisses. Pinned so that
    # if suppression is ever added, the golden diff shows it.
    f["src/backends/base.py"] = _branches(DIALECT)
    for name, piece in zip(("postgres", "mysql", "sqlite"), _pieces(DIALECT)):
        f[f"src/backends/{name}.py"] = _branches(piece)

    # REJECTED — chain-shaped grab-bag: a ring where each file shares values only with its neighbours,
    # so union-find strings them into one cluster that no coherent decision would produce.
    pool = [f"tok{i}" for i in range(10)]
    for i in range(10):
        f[f"src/chain/f{i}.py"] = _branches([pool[(i + k) % 10] for k in range(3)])

    # REJECTED — keyboard keys: platform vocabulary, so no file here could own it.
    for name in ("list", "scroll", "menu"):
        f[f"src/ui/{name}.tsx"] = _branches(KEYS, var="e.key")

    # ENUM ESCAPES, one file per variant so each finding stays single-purpose. The value sets are
    # deliberately disjoint from the decision cases above: sharing them made the orders files bleed into
    # the escape finding and left the golden hard to read.
    f["src/enums/workflow.py"] = (
        "from enum import Enum\n\n\nclass JobState(Enum):\n"
        + "".join(f'    {s.upper()} = "{s}"\n' for s in JOB_STATES)
    )
    # (a) same-language Python: nothing checks this, so it is the strongest same-language case
    f["src/enums/consumer.py"] = _branches(JOB_STATES[:3], var="job.state.value")
    f["src/enums/mode.py"] = (
        "from enum import Enum\n\n\nclass DeployMode(Enum):\n"
        + "".join(f'    {m.upper()} = "{m}"\n' for m in MODES)
    )
    # (b) purely cross-language: a Python enum, a TypeScript escaper, no import possible either way
    f["src/web/deploy.tsx"] = _branches(MODES[:3], var="mode")
    f["src/web/kinds.ts"] = (
        "export enum Kind {\n" + "".join(f"  K{i} = 'kind{i}',\n" for i in range(4)) + "}\n"
    )
    # (c) purely TypeScript: tsc already rejects a stale literal here, so the finding must say so
    f["src/web/view.tsx"] = _branches([f"kind{i}" for i in range(4)], var="kind")

    # ENUM MEMBER DISPATCH: the well-behaved form, invisible to the string scan.
    f["src/dispatch/kind.py"] = (
        "from enum import Enum\n\n\nclass ProviderKind(Enum):\n"
        + "".join(f"    {m.split('.')[1]} = {i}\n" for i, m in enumerate(MEMBERS))
    )
    f["src/dispatch/router.py"] = _member_branches(MEMBERS)
    for name, piece in zip(("auth", "webhook", "sync"), _pieces(MEMBERS)):
        f[f"src/dispatch/{name}.py"] = _member_branches(piece)

    # THE BRIDGING CASE: two unrelated string clusters in one group, where every file *also* branches on
    # an enum member. Clustered together, that member is a high-degree node union-find will use as a
    # bridge, merging both into one incoherent blob that the cohesion bar then drops — silently
    # destroying two real findings. This is the exact shape of the regression this fixture exists for,
    # and it only reproduces when members and strings share a group, which is why the tidy
    # one-case-per-directory layout above was not enough.
    f["src/mixed/mode.py"] = (
        "from enum import Enum\n\n\nclass RunMode(Enum):\n    ACTIVE = 1\n    IDLE = 2\n    PAUSED = 3\n"
    )
    for i in range(4):
        vals = GRANT if i == 0 else GRANT[: 2 + (i % 2)]
        f[f"src/mixed/auth{i}.py"] = _branches(vals) + "if mode == RunMode.ACTIVE:\n    pass\n"
    for i in range(4):
        vals = HUES if i == 0 else HUES[: 2 + (i % 2)]
        f[f"src/mixed/theme{i}.py"] = _branches(vals) + "if mode == RunMode.ACTIVE:\n    pass\n"

    # HOTSPOTS: the scored pool. Only these files clear MIN_LOC, so the percentiles are computed over a
    # small, legible set — one file high on both axes, and one high on each axis alone.
    f["src/perf/hot.py"] = _nested()             # churny AND complex -> flagged
    f["src/perf/churny_flat.py"] = _flat()       # churny, not complex
    f["src/perf/nested_stable.py"] = _nested()   # complex, not churny
    f["src/perf/middling.py"] = _flat()
    f["src/perf/quiet.py"] = _flat()

    # EXCLUDED: neither should contribute a finding despite holding a textbook duplicated decision.
    f["src/vendor/lib.py"] = _branches(STATES)
    f["src/app/emitted.py"] = "# @generated by a tool\n" + _branches(STATES)
    return f


def _commits() -> list[tuple[str, list[str]]]:
    """`(subject, paths)` per commit. Conventional Commits, so the learner should pick that style."""
    out: list[tuple[str, list[str]]] = [("chore: initial import", [])]  # [] = everything
    for i in range(1, 9):   # drive hot.py and churny_flat.py to the top of the churn axis
        out.append((f"fix(perf): tune the hot path ({i})", ["src/perf/hot.py", "src/perf/churny_flat.py"]))
    for i in range(1, 4):
        out.append((f"fix(orders): correct state handling ({i})",
                    [f"src/orders/{n}.py" for n in ("state", "api", "report", "email")]))
    for i in range(1, 4):
        out.append((f"feat(backends): extend the dialect table ({i})",
                    [f"src/backends/{n}.py" for n in ("base", "postgres", "mysql", "sqlite")]))
    for i in range(1, 4):
        out.append((f"feat(dispatch): extend routing ({i})",
                    [f"src/dispatch/{n}.py" for n in ("router", "auth", "webhook", "sync")]))
    for i in range(1, 4):
        out.append((f"fix(ui): key handling ({i})", [f"src/ui/{n}.tsx" for n in ("list", "scroll", "menu")]))
    for i in range(1, 4):
        out.append((f"refactor(chain): shuffle tokens ({i})", [f"src/chain/f{j}.py" for j in range(10)]))
    for i in range(1, 4):
        out.append((f"fix(mixed): correct grant and theme handling ({i})",
                    [f"src/mixed/{n}{j}.py" for n in ("auth", "theme") for j in range(4)]))
    out.append(("docs: describe the layout", ["src/perf/middling.py"]))
    return out


def _build(root: Path, files: dict[str, str], commits: list[tuple[str, list[str]]]) -> Path:
    _git(root, "init", "-q")
    for n, (subject, paths) in enumerate(commits):
        if not paths:
            for rel, text in files.items():
                _write(root, rel, text)
        else:
            for rel in paths:
                _write(root, rel, _revise(rel, files[rel], n))
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", subject, n=n)
    return root


def main_repo(root: Path) -> Config:
    """One instance of every signal, with a Conventional Commits history."""
    _build(root, _files(), _commits())
    return Config(
        project_root=root, languages=["python", "ts"],
        python=PythonConfig(root_package=None, source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def tracker_repo(root: Path) -> Config:
    """A second commit convention, and the trap that produced the worst measured bug: issue-closing
    trailers out-number the real fix vocabulary, and must not be read as fixes."""
    files = {"src/pkg/a.py": _flat(), "src/pkg/b.py": _nested()}
    commits: list[tuple[str, list[str]]] = [("Initial import", [])]
    for i in range(1, 7):
        commits.append((f"Add the widget ({i}), closes #{100 + i}", ["src/pkg/a.py"]))
    for i in range(1, 4):
        commits.append((f"Document the thing ({i}), resolves #{200 + i}", ["src/pkg/a.py"]))
    for i in range(1, 5):
        commits.append((f"Fixed #{300 + i} -- the retry loop ({i})", ["src/pkg/b.py"]))
    commits.append(("Fix the rounding error", ["src/pkg/b.py"]))
    _build(root, files, commits)
    return Config(
        project_root=root, languages=["python"],
        python=PythonConfig(root_package=None, source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )

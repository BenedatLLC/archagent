"""archagent evaluate — regime B (git co-change): shotgun surgery + unstable interface."""

import subprocess

from archagent.cochange import mine_cochange
from archagent.config import Config, PythonConfig, TSConfig
from archagent.evaluate import evaluate


def _git(tmp, *args):
    subprocess.run(["git", "-C", str(tmp), *args], check=True, capture_output=True)


def _cfg(tmp):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _sub(cfg, name, covers):
    (cfg.project_root / "architecture" / "subsystems" / f"{name}.md").write_text(
        f"# {name}\n\n**Covers:** `{covers}`\n")


def _commit(cfg, msg, files: dict):
    root = cfg.project_root
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def _cochange_n(cfg, files, n, prefix="c"):
    """Commit the given files together n times, changing content each time."""
    for i in range(n):
        _commit(cfg, f"{prefix}{i}", {f: f"v{i}\n" for f in files})


def _of(result, sign):
    return [f for f in result.findings if f.sign == sign]


def test_miner_counts_pairs_and_skips_bulk(tmp_path):
    cfg = _cfg(tmp_path)
    file_subs = {"src/pkg/x.py": {"x"}, "src/pkg/y.py": {"y"}, "src/pkg/z.py": {"z"}}
    _cochange_n(cfg, ["src/pkg/x.py", "src/pkg/y.py"], 3)   # x,y together x3
    _commit(cfg, "solo", {"src/pkg/z.py": "only-z\n"})       # z alone
    cc = mine_cochange(tmp_path, file_subs)
    assert cc.between("x", "y") == 3
    assert cc.between("x", "z") == 0
    assert cc.sub_commits["x"] == 3 and cc.sub_commits["z"] == 1


def test_bulk_commit_excluded(tmp_path):
    cfg = _cfg(tmp_path)
    file_subs = {f"src/pkg/f{i}.py": {"x" if i == 0 else "y"} for i in range(60)}
    big = {f"src/pkg/f{i}.py": "v\n" for i in range(60)}   # 60 files > cap => ignored
    _commit(cfg, "bulk", big)
    cc = mine_cochange(tmp_path, file_subs, max_commit_files=50)
    assert cc.between("x", "y") == 0


def test_shotgun_surgery_flagged(tmp_path):
    cfg = _cfg(tmp_path)
    # x and y never import each other, but keep changing together
    _sub(cfg, "x", "src/pkg/x.py")
    _sub(cfg, "y", "src/pkg/y.py")
    _cochange_n(cfg, ["src/pkg/x.py", "src/pkg/y.py"], 5)
    r = evaluate(cfg)
    imp = _of(r, "implicit-coupling")
    assert imp and sorted(imp[0].subjects) == ["x", "y"]
    assert r.history_analyzed >= 5


def test_structural_dependency_suppresses_shotgun(tmp_path):
    cfg = _cfg(tmp_path)
    _sub(cfg, "x", "src/pkg/x.py")
    _sub(cfg, "y", "src/pkg/y.py")
    # x imports y => their co-change is explained by a real dependency
    _cochange_n(cfg, ["src/pkg/x.py", "src/pkg/y.py"], 5)
    (tmp_path / "src/pkg/x.py").write_text("from pkg import y\n")
    _commit(cfg, "link", {"src/pkg/x.py": "from pkg import y\n"})
    assert "implicit-coupling" not in {f.sign for f in evaluate(cfg).findings}


def test_unstable_interface_flagged(tmp_path):
    cfg = _cfg(tmp_path)
    for n in ("a", "b", "c"):
        _sub(cfg, n, f"src/pkg/{n}.py")
    _sub(cfg, "core", "src/pkg/core.py")
    # a, b, c all depend on core; core keeps changing with a and b
    base = {f"src/pkg/{n}.py": "from pkg import core\n" for n in ("a", "b", "c")}
    base["src/pkg/core.py"] = "x = 0\n"
    _commit(cfg, "init", base)
    _cochange_n(cfg, ["src/pkg/core.py", "src/pkg/a.py"], 4, prefix="ca")
    _cochange_n(cfg, ["src/pkg/core.py", "src/pkg/b.py"], 4, prefix="cb")
    # keep a, b importing core after the churn
    (tmp_path / "src/pkg/a.py").write_text("from pkg import core\n")
    (tmp_path / "src/pkg/b.py").write_text("from pkg import core\n")
    _commit(cfg, "relink", {"src/pkg/a.py": "from pkg import core\n", "src/pkg/b.py": "from pkg import core\n"})
    ui = _of(evaluate(cfg), "unstable-interface")
    assert ui and ui[0].subjects == ["core"]


def test_no_history_flag_skips_regime_b(tmp_path):
    cfg = _cfg(tmp_path)
    _sub(cfg, "x", "src/pkg/x.py")
    _sub(cfg, "y", "src/pkg/y.py")
    _cochange_n(cfg, ["src/pkg/x.py", "src/pkg/y.py"], 5)
    r = evaluate(cfg, history=False)
    assert r.history_analyzed == 0
    assert "implicit-coupling" not in {f.sign for f in r.findings}

"""How `status` presents coverage — the number was never wrong, only the confidence it projected.

Round 1's user tester read "100%" in a full-width green bar, found the depth table below marking the same
subsystem `thin` at 3.6 words per file, and rated completeness 2 of 5 (#35). Round 5 had found the same
defect one level up and fixed the *artifact* that quoted the number rather than the tool presenting it,
so the next artifact would have made the same claim.
"""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.described import described as run_described
from archagent.drift import _source_files
from archagent.status import status as run_status


def _cfg(tmp):
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="pkg", source_paths=["src"]),
                  ts=TSConfig(source_paths=["src"]))


def _src(cfg, rel, text=""):
    """A module `described` will actually consider — it skips anything under `MIN_LINES`, on the grounds
    that a ten-line module is a thing a reader scrolls past."""
    p = cfg.project_root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text or "".join(f"v_{i} = {i}\n" for i in range(20)))


def _sub(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / f"{name}.md").write_text(text)


def _overstated(cfg) -> bool:
    """The predicate `cli.status` uses to decide whether the bar may read as green."""
    r = run_status(cfg)
    d = run_described(cfg, _source_files(cfg))
    return bool(r.thin) or bool(d.considered and d.pct < 80)


def test_a_glob_claiming_everything_does_not_read_as_green(tmp_path):
    """The httpx shape: one glob claims every file, the document names almost none of them."""
    cfg = _cfg(tmp_path)
    for i in range(8):
        _src(cfg, f"pkg/mod{i}.py")
    _sub(cfg, "everything", "# Everything\n\n**Covers:** `src/pkg/**`\n\nIt does things.\n")
    assert run_status(cfg).packages[0].pct == 100, "the claim really is 100% — that part was never wrong"
    assert _overstated(cfg), "and it must not be presented as health"


def test_a_genuinely_described_artifact_still_reads_as_green(tmp_path):
    """The guard must not make green unreachable, or it stops carrying information. archagent's own
    artifact is the reference case: 0 thin documents, 100% described."""
    cfg = _cfg(tmp_path)
    for i in range(3):
        _src(cfg, f"pkg/mod{i}.py")
    _sub(cfg, "core", "# Core\n\n**Covers:** `src/pkg/**`\n\n"
                      "The `mod0` module does one thing, `mod1` another, and `mod2` a third. "
                      "Each is described here at enough length that the document is not thin, which "
                      "requires prose rather than a bare list of names to sit above the median density.\n")
    assert not _overstated(cfg)


def test_the_table_says_what_it_counts(tmp_path):
    """The column was headed "Coverage", which is the reading the tester took and the tool cannot
    support. It counts files a glob matches."""
    import inspect
    from archagent import cli
    src = inspect.getsource(cli.status)
    assert "files claimed by a `**Covers:**` glob" in src
    assert "Claimed" in src
    # and the correction must sit with the number, not forty lines below it
    i_table = src.index("console.print(table)")
    i_caveat = src.index("Claimed counts files a glob matches")
    i_depth = src.index("Subsystem depth")
    assert i_table < i_caveat < i_depth

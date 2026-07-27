"""archagent evaluate — the two history-based checks end to end (change-prone files, scattered SSoT)."""

import subprocess

from archagent.config import Config, PythonConfig, TSConfig
from archagent.evaluate import evaluate

STATES = ["pending", "paid", "shipped", "refunded", "cancelled"]


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


def _of(result, sign):
    return [f for f in result.findings if f.sign == sign]


def _nested(lines=60, depth=4, salt=0):
    pad = " " * (depth * 4)
    return f"# {salt}\n" + "".join(f"{pad}v_{i} = {i}\n" for i in range(lines))


def _flat(lines=60, salt=0):
    return f"# {salt}\n" + "".join(f"v_{i} = {i}\n" for i in range(lines))


# --- Check A ------------------------------------------------------------------------------

def test_change_prone_file_flagged(tmp_path):
    cfg = _cfg(tmp_path)
    _commit(cfg, "init", {
        "src/pkg/hot.py": _nested(), "src/pkg/flat.py": _flat(),
        "src/pkg/cold.py": _nested(), "src/pkg/other.py": _flat(),
    })
    for i in range(1, 9):  # hot.py and flat.py churn; cold.py and other.py don't
        _commit(cfg, f"Fixed #{i} -- tweak", {"src/pkg/hot.py": _nested(salt=i),
                                              "src/pkg/flat.py": _flat(salt=i)})
    found = _of(evaluate(cfg), "change-prone-file")
    assert [f.subjects[0] for f in found] == ["src/pkg/hot.py"]
    assert found[0].group == "E" and found[0].regime == "history"
    assert "fix-labeled" in found[0].detail  # the learned recognizer picked up `Fixed #N`


def test_change_prone_check_needs_no_subsystems(tmp_path):
    """Check A is per-file, so it must not depend on **Covers:** declarations the way co-change does."""
    cfg = _cfg(tmp_path)
    _commit(cfg, "init", {"src/pkg/hot.py": _nested(), "src/pkg/b.py": _flat(),
                          "src/pkg/c.py": _flat()})
    for i in range(1, 7):
        _commit(cfg, f"c{i}", {"src/pkg/hot.py": _nested(salt=i)})
    result = evaluate(cfg)
    assert result.history_analyzed == 0          # nothing maps to a subsystem
    assert _of(result, "change-prone-file")      # ... and the per-file check still ran


def test_no_history_flag_skips_both_new_checks(tmp_path):
    cfg = _cfg(tmp_path)
    _commit(cfg, "init", {"src/pkg/hot.py": _nested(), "src/pkg/b.py": _flat()})
    for i in range(1, 7):
        _commit(cfg, f"c{i}", {"src/pkg/hot.py": _nested(salt=i)})
    signs = {f.sign for f in evaluate(cfg, history=False).findings}
    assert "change-prone-file" not in signs and "scattered-source-of-truth" not in signs


# --- Check B ------------------------------------------------------------------------------

def _owner_src(values=STATES):
    return "".join(f'if state == "{v}":\n    pass\n' for v in values)


def _piece_src(values, skip):
    return "".join(f'if s == "{v}":\n    pass\n' for v in values if v != skip)


def _decision_files():
    files = {"src/orders/state.py": _owner_src()}
    for i, name in enumerate(("api", "report", "email")):
        files[f"src/orders/{name}.py"] = _piece_src(STATES, STATES[i])
    return files


def _churn_the_decision(cfg, rounds=4):
    for i in range(rounds):
        _commit(cfg, f"Fixed #{i} -- order state", {
            "src/orders/state.py": _owner_src() + f"# {i}\n",
            "src/orders/api.py": _piece_src(STATES, STATES[0]) + f"# {i}\n",
            "src/orders/report.py": _piece_src(STATES, STATES[1]) + f"# {i}\n",
        })


def test_scattered_source_of_truth_flagged(tmp_path):
    cfg = _cfg(tmp_path)
    _sub(cfg, "orders", "src/orders/*.py")
    _commit(cfg, "init", _decision_files())
    _churn_the_decision(cfg)

    found = _of(evaluate(cfg), "scattered-source-of-truth")
    assert len(found) == 1
    f = found[0]
    assert f.group == "F" and f.confidence == "low"
    assert f.subjects[0] == "src/orders/state.py"
    assert set(f.subjects[1:]) == {"src/orders/api.py", "src/orders/report.py", "src/orders/email.py"}
    assert "pending" in f.detail and "likely owner" in f.detail


def test_untouched_duplication_is_ranked_out(tmp_path):
    """The duplication is real, but the files sit still — history is what says whether it costs anything."""
    cfg = _cfg(tmp_path)
    _sub(cfg, "orders", "src/orders/*.py")
    _commit(cfg, "init", _decision_files())
    assert _of(evaluate(cfg), "scattered-source-of-truth") == []


def test_falls_back_to_directories_when_no_subsystems_declared(tmp_path):
    cfg = _cfg(tmp_path)
    _commit(cfg, "init", _decision_files())
    _churn_the_decision(cfg)
    found = _of(evaluate(cfg), "scattered-source-of-truth")
    assert found and found[0].detail.startswith("in src/orders:")


# --- the enum-value escape, and what it recommends -----------------------------------------

STATE_ENUM = ('from enum import Enum\n\n\nclass WorkflowState(Enum):\n'
              '    INITIAL = "initial"\n    SUMMARIZED = "summarized"\n'
              '    SEM_SEARCH = "sem-search"\n    RESEARCH = "research"\n')


def _escaper(values):
    return "".join(f'if name == "{v}":\n    pass\n' for v in values)


def _escape_finding(cfg, files):
    _commit(cfg, "init", files)
    return _of(evaluate(cfg), "enum-value-escape")


def test_same_language_escape_says_import_the_member(tmp_path):
    cfg = _cfg(tmp_path)
    found = _escape_finding(cfg, {
        "src/pkg/state.py": STATE_ENUM,
        "src/pkg/service.py": _escaper(["summarized", "sem-search", "research"]),
    })
    assert len(found) == 1
    f = found[0]
    assert f.title == "Enum bypassed by its raw values"
    assert "Compare against the WorkflowState member itself" in f.recommendation
    assert "cannot import" not in f.recommendation


def test_cross_language_escape_recommends_generating_the_other_side(tmp_path):
    """Telling a TypeScript file to compare against a Python enum member is not advice."""
    cfg = _cfg(tmp_path)
    cfg.languages = ["python", "ts"]
    found = _escape_finding(cfg, {
        "src/api/state.py": STATE_ENUM,
        "src/web/panel.tsx": _escaper(["summarized", "sem-search", "research"]),
    })
    assert len(found) == 1
    f = found[0]
    assert f.title == "Enum vocabulary duplicated across a language boundary"
    assert "cannot import" in f.recommendation
    assert "Generate the other language's constants" in f.recommendation
    assert "Compare against the WorkflowState member itself" not in f.recommendation
    assert "no import can cross that boundary" in f.detail
    # nothing links the two sides, so a match can't be coincidence the way a same-language one might
    assert f.confidence == "med"


def test_mixed_escape_gives_both_recommendations(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.languages = ["python", "ts"]
    found = _escape_finding(cfg, {
        "src/api/state.py": STATE_ENUM,
        "src/api/service.py": _escaper(["summarized", "sem-search", "research"]),
        "src/web/panel.tsx": _escaper(["summarized", "sem-search", "research"]),
    })
    rec = found[0].recommendation
    assert "For the 1 in python:" in rec and "For the 1 across the language boundary:" in rec
    assert found[0].title == "Enum bypassed by its raw values"  # not purely cross-language


# --- coverage reporting: a capped list must not read as a complete inventory ----------------

def test_truncated_lists_are_reported(tmp_path):
    """`showing 10 of 78` and `10 findings` are very different claims. Never let the cap be silent."""
    cfg = _cfg(tmp_path)
    # 15 nested + churny against 35 flat + stable: the 15 tie at the top of both axes, so all of them
    # clear the top-quartile bar and more than MAX_REPORTED qualify
    hot = [f"src/pkg/hot{i}.py" for i in range(15)]
    cold = {f"src/pkg/cold{i}.py": _flat() for i in range(35)}
    _commit(cfg, "init", {**cold, **{h: _nested() for h in hot}})
    for i in range(1, 6):
        _commit(cfg, f"c{i}", {h: _nested(salt=i) for h in hot})
    result = evaluate(cfg)
    fams = {fam: (shown, found) for fam, shown, found in result.truncated}
    assert "E — change-prone complex files" in fams
    shown, found = fams["E — change-prone complex files"]
    assert shown == 10 and found > 10
    assert len(_of(result, "change-prone-file")) == shown


def test_nothing_is_reported_as_truncated_when_it_fits(tmp_path):
    cfg = _cfg(tmp_path)
    _commit(cfg, "init", {"src/pkg/hot.py": _nested(), "src/pkg/b.py": _flat(), "src/pkg/c.py": _flat()})
    for i in range(1, 5):
        _commit(cfg, f"c{i}", {"src/pkg/hot.py": _nested(salt=i)})
    assert evaluate(cfg).truncated == []


def test_thin_subsystem_mapping_caution_does_not_disown_per_file_churn(tmp_path):
    """The caution used to read as though the whole history were thin, which would wrongly discount the
    change-prone-file findings that in fact used every commit in the window."""
    cfg = _cfg(tmp_path)   # no **Covers:** anywhere, so nothing maps to a subsystem
    _commit(cfg, "init", {"src/pkg/hot.py": _nested(), "src/pkg/b.py": _flat()})
    for i in range(1, 8):
        _commit(cfg, f"c{i}", {"src/pkg/hot.py": _nested(salt=i)})
    result = evaluate(cfg)
    caution = next(c for c in result.history_cautions if "mapped to subsystems" in c)
    assert "*subsystem* co-change" in caution
    assert "Per-file churn is unaffected" in caution


def test_typescript_only_escape_defers_to_the_compiler(tmp_path):
    """tsc rejects a comparison between a typed value and a literal outside its type (TS2367) — verified
    for string enums, union types, `as const` unions and switch arms alike. So a stale string cannot
    survive a TS build, and the finding is only real where the compared value arrives untyped."""
    cfg = _cfg(tmp_path)
    cfg.languages = ["ts"]
    found = _escape_finding(cfg, {
        "src/web/kinds.ts": "export enum Kind {\n  A = 'alpha',\n  B = 'bravo',\n  C = 'charlie',\n}\n",
        "src/web/panel.tsx": 'if (k === "alpha") {}\nif (k === "bravo") {}\nif (k === "charlie") {}\n',
    })
    assert len(found) == 1
    assert "TS2367" in found[0].recommendation
    assert "arrives untyped" in found[0].recommendation
    assert found[0].confidence == "low"


def test_python_escape_keeps_the_stronger_claim(tmp_path):
    """Python has no equivalent check, so the same shape there is a real defect, not a compiler note."""
    cfg = _cfg(tmp_path)
    found = _escape_finding(cfg, {
        "src/pkg/state.py": STATE_ENUM,
        "src/pkg/service.py": _escaper(["summarized", "sem-search", "research"]),
    })
    assert "TS2367" not in found[0].recommendation
    assert "Compare against the WorkflowState member itself" in found[0].recommendation


def test_cross_language_escape_is_not_softened_by_the_compiler_note(tmp_path):
    """Neither compiler sees the other side, so nothing guards a cross-language escape."""
    cfg = _cfg(tmp_path)
    cfg.languages = ["python", "ts"]
    found = _escape_finding(cfg, {
        "src/api/state.py": STATE_ENUM,
        "src/web/panel.tsx": _escaper(["summarized", "sem-search", "research"]),
    })
    assert "TS2367" not in found[0].recommendation
    assert found[0].confidence == "med"

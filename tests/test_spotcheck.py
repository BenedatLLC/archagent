"""Human spot-check and calibration — the properties that decide whether the labels mean anything."""

import pytest

from spotcheck import (
    Label,
    LabelStore,
    agreement,
    finding_key,
    parse_worksheet,
    precision_by_sign,
    render_worksheet,
    stratified_sample,
    values_of,
    wilson,
)


def _item(key, repo="litellm", sign="scattered-source-of-truth", conf="low", claim=None):
    return {"key": key, "repo": repo, "rev": "v1", "sign": sign, "confidence": conf,
            "evidence": f"- owner: `{key}.py`\n- churn: 40", "tool_claim": claim or {"severity": "med"}}


# --- identity ---------------------------------------------------------------------------------

def test_the_key_survives_things_that_move_between_runs():
    """Labels are the expensive input; a key that changed with churn counts would spend each one once."""
    a = finding_key("change-prone-file", ["src/a.py"], None)
    b = finding_key("change-prone-file", ["src/a.py"], None)
    assert a == b


def test_the_key_distinguishes_different_value_sets():
    a = finding_key("scattered-source-of-truth", ["src/a.py"], ["paid", "shipped"])
    b = finding_key("scattered-source-of-truth", ["src/a.py"], ["red", "green"])
    assert a != b


def test_value_order_does_not_change_the_key():
    assert (finding_key("s", ["a.py"], ["b", "a"]) == finding_key("s", ["a.py"], ["a", "b"]))


def test_values_are_read_out_of_the_detail_text():
    assert values_of("in x: {paid, shipped, +3 more} branched on") == ["paid", "shipped"]
    assert values_of("40 commits; mean indent 9.1") is None


# --- blinding ---------------------------------------------------------------------------------

def test_the_tools_claim_is_absent_from_the_worksheet():
    """Shown up front, severity and confidence anchor the reviewer and the exercise measures agreement
    with our own prior instead of with the code."""
    sheet, withheld = render_worksheet([_item("k1", claim={"severity": "high", "confidence": "med",
                                                           "recommendation": "Split this file"})])
    assert "high" not in sheet and "Split this file" not in sheet
    assert withheld["k1"]["severity"] == "high"


def test_the_worksheet_still_carries_the_evidence():
    sheet, _ = render_worksheet([_item("k1")])
    assert "owner: `k1.py`" in sheet and "churn: 40" in sheet


# --- parsing ----------------------------------------------------------------------------------

def test_a_filled_sheet_round_trips():
    sheet, _ = render_worksheet([_item("k1"), _item("k2")])
    filled = sheet.replace("verdict:\nwhy:", "verdict: confirm\nwhy: real duplication", 1)
    parsed = parse_worksheet(filled)
    assert parsed["k1"] == {"verdict": "confirm", "why": "real duplication"}
    assert "k2" not in parsed, "unanswered items are skipped, never guessed at"


def test_the_parser_is_lenient_about_how_people_write():
    sheet, _ = render_worksheet([_item("k1")])
    filled = sheet.replace("verdict:\nwhy:", "Verdict:  Dismiss — intended family\nwhy: adapters", 1)
    assert parse_worksheet(filled)["k1"]["verdict"] == "dismiss"


def test_an_unrecognised_verdict_is_skipped_rather_than_guessed():
    sheet, _ = render_worksheet([_item("k1")])
    assert parse_worksheet(sheet.replace("verdict:", "verdict: maybe?", 1)) == {}


# --- the store --------------------------------------------------------------------------------

def _label(store, key, verdict, reviewer="jf", **kw):
    return store.record(Label(key=key, repo="litellm", sign="s", verdict=verdict, why="because",
                              reviewer=reviewer, dated="2026-08-01", **kw))


def test_labels_persist_and_reload(tmp_path):
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    assert store.load("litellm")["k1"].verdict == "confirm"


def test_changing_a_verdict_requires_a_note(tmp_path):
    """Otherwise labels drift toward whatever the tool currently claims and the calibration they feed
    becomes circular."""
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    with pytest.raises(ValueError, match="requires a note"):
        _label(store, "k1", "dismiss")


def test_a_changed_verdict_keeps_the_one_it_replaced(tmp_path):
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    store.record(Label(key="k1", repo="litellm", sign="s", verdict="dismiss", why="on reflection",
                       reviewer="jf", dated="2026-08-02"), note="re-read the code; adapters by design")
    kept = store.load("litellm")["k1"]
    assert kept.verdict == "dismiss"
    assert kept.history[0]["verdict"] == "confirm"
    assert "adapters" in kept.history[0]["changed_because"]


def test_relabelling_the_same_verdict_needs_no_note(tmp_path):
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    _label(store, "k1", "confirm")            # must not raise


def test_evidence_that_changed_marks_the_label_stale(tmp_path):
    """The verdict was about the evidence as it stood; silently reusing it against different evidence
    would be inventing a judgement nobody made."""
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm", evidence="5 files, 40 churn")
    assert store.stale("litellm", {"k1": "12 files, 400 churn"}) == ["k1"]
    assert store.stale("litellm", {"k1": "5 files, 40 churn"}) == []


# --- sampling ---------------------------------------------------------------------------------

def test_sampling_spreads_across_strata_rather_than_taking_the_biggest():
    items = [_item(f"a{i}", sign="change-prone-file") for i in range(50)] + \
            [_item(f"b{i}", sign="enum-value-escape") for i in range(3)]
    picked = stratified_sample(items, cap=10)
    signs = {p["sign"] for p in picked}
    assert signs == {"change-prone-file", "enum-value-escape"}


def test_sampling_is_reproducible():
    items = [_item(f"a{i}") for i in range(40)]
    assert [p["key"] for p in stratified_sample(items, cap=8)] == \
           [p["key"] for p in stratified_sample(items, cap=8)]


def test_sampling_respects_the_cap():
    assert len(stratified_sample([_item(f"a{i}") for i in range(40)], cap=7)) == 7


# --- statistics -------------------------------------------------------------------------------

def test_wilson_stays_inside_zero_and_one_at_small_n():
    """The normal approximation runs past the ends at the sample sizes this exercise produces."""
    lo, hi = wilson(5, 5)
    assert 0.0 <= lo <= hi <= 1.0 and lo > 0.4


def test_wilson_of_nothing_is_the_whole_interval():
    assert wilson(0, 0) == (0.0, 1.0)


def test_precision_excludes_unsure_from_the_denominator():
    """`unsure` is missing data, not a dismissal — counting it either way invents a judgement."""
    labels = [Label("k1", "r", "sX", "confirm", "", "jf", "d"),
              Label("k2", "r", "sX", "dismiss", "", "jf", "d"),
              Label("k3", "r", "sX", "unsure", "", "jf", "d")]
    out = precision_by_sign(labels)["sX"]
    assert out["n"] == 2 and out["precision_strict"] == pytest.approx(0.5) and out["unsure"] == 1


def test_agreement_reports_the_direction_of_disagreement():
    """A single rate would hide a judge that systematically over-confirms."""
    human = {"a": "dismiss", "b": "dismiss", "c": "confirm"}
    judge = {"a": "confirm", "b": "confirm", "c": "confirm"}
    out = agreement(human, judge)
    assert out["n"] == 3 and out["judge_over_confirms"] == 2 and out["judge_over_dismisses"] == 0


def test_agreement_ignores_items_only_one_side_rated():
    assert agreement({"a": "confirm"}, {"b": "confirm"})["n"] == 0


# --- partial, the verdict a reviewer reached for unprompted ------------------------------------

def test_partial_confirm_is_recognised():
    """A reviewer used "partial confirm" on 3 of 10 enum items to mean "something real is here, but not
    what the finding claims". The original parser dropped unrecognised verdicts silently, so the most
    informative labels in the round were nearly lost."""
    sheet, _ = render_worksheet([_item("k1")])
    filled = sheet.replace("verdict:\nwhy:", "verdict: partial confirm\nwhy: right escape, wrong enum", 1)
    assert parse_worksheet(filled)["k1"]["verdict"] == "partial"


def test_partial_is_not_swallowed_by_the_confirm_prefix():
    sheet, _ = render_worksheet([_item("k1")])
    for phrasing in ("partial", "Partial confirm", "partially confirmed"):
        filled = sheet.replace("verdict:\nwhy:", f"verdict: {phrasing}\nwhy: x", 1)
        assert parse_worksheet(filled)["k1"]["verdict"] == "partial", phrasing


def test_precision_is_reported_strictly_and_leniently():
    """One number would hide a signal that is usually pointing at something true while mis-attributing it."""
    labels = [Label(f"k{i}", "r", "sX", v, "", "jf", "d") for i, v in
              enumerate(["confirm", "confirm", "partial", "dismiss"])]
    out = precision_by_sign(labels)["sX"]
    assert out["precision_strict"] == pytest.approx(0.5)
    assert out["precision_lenient"] == pytest.approx(0.75)
    assert (out["confirmed"], out["partial"], out["dismissed"]) == (2, 1, 1)


# --- scoping a round to signal groups (B/C have never been labelled) --------------------------------

def test_groups_resolve_to_signs():
    from spotcheck import signs_in
    assert "layer-inversion" in signs_in("B")
    assert "god-component" in signs_in("C")
    assert set(signs_in("B,C")) == set(signs_in("B")) | set(signs_in("C"))


def test_an_unknown_group_is_refused_rather_than_returning_nothing():
    """An empty tuple would generate a worksheet with no items and read as "nothing left to label",
    which is the opposite of what a typo means."""
    from spotcheck import signs_in
    with pytest.raises(ValueError, match="unknown group"):
        signs_in("B,Z")


def test_every_sign_belongs_to_exactly_one_group():
    from spotcheck import GROUPS
    seen = [s for signs in GROUPS.values() for s in signs]
    assert len(seen) == len(set(seen))


def test_the_group_table_covers_every_sign_evaluate_emits():
    """A signal added to `evaluate` and forgotten here is invisible to `--groups`, so a round scoped by
    group would silently never ask about it."""
    import re
    from pathlib import Path

    from spotcheck import GROUPS
    src = (Path(__file__).resolve().parents[1] / "src" / "archagent" / "evaluate.py").read_text()
    emitted = set(re.findall(r'sign="([a-z0-9-]+)"', src))
    known = {s for signs in GROUPS.values() for s in signs}
    assert emitted <= known, sorted(emitted - known)


# --- refusing items a reviewer could not judge ------------------------------------------------------

def test_a_finding_with_only_subject_names_is_not_askable():
    """The pinned corpus keeps only fields that must not change, so it strips `detail`. A group B finding
    read from there is two subsystem names — asking about it would have the reviewer reconstruct the
    finding and then grade their own reconstruction."""
    from spotcheck import evidence_is_usable
    assert not evidence_is_usable("- owner: `backend-core`\n- also: `backend-domain`")


def test_a_finding_carrying_its_measurement_is_askable():
    from spotcheck import evidence_is_usable
    assert evidence_is_usable("- owner: `drift`\n- measured: 2-node tiny cycle (2 edges, max weight 5)")


def test_a_short_measurement_is_still_askable():
    """`70/122 files (57%)` is the whole of a god-component finding and is immediately judgeable. A first
    version required six words and rejected it — length was never the question."""
    from spotcheck import evidence_is_usable
    assert evidence_is_usable("- owner: `frontend-app`\n- measured: 70/122 files (57%)")


def test_a_value_set_is_askable_without_a_measurement():
    """How group F items have always arrived."""
    from spotcheck import evidence_is_usable
    assert evidence_is_usable("- owner: `a.py`\n- values: eu, us")


# --- worksheet instructions must match the sheet's contents -----------------------------------------

def _sheet(signs):
    from spotcheck import render_worksheet
    items = [{"key": f"{s}:x:0", "repo": "demo", "rev": "v1", "sign": s,
              "evidence": f"- owner: `x`\n- measured: {s} detail"} for s in signs]
    return render_worksheet(items)[0]


def test_partial_is_offered_to_the_reviewer():
    """It is accepted by the parser and was the most informative verdict in round 1, and the instructions
    did not mention it — a reviewer could only use it by guessing it existed."""
    text = _sheet(["layer-inversion"])
    assert "`partial`" in text and "not what the finding claims" in text


def test_guidance_covers_the_signs_present_and_no_others():
    """The guidance was one hardcoded paragraph about change-prone-file. On a group B/C sheet it told the
    reviewer to go read a file when the claim to check was two `**Tier:**` declarations."""
    text = _sheet(["layer-inversion"])
    assert "**Tier:**" in text
    assert "change-prone file" not in text.lower()


def test_a_change_prone_sheet_still_gets_its_own_guidance():
    assert "absorbing special cases" in _sheet(["change-prone-file"])


def test_guidance_is_not_repeated_when_two_signs_share_it():
    text = _sheet(["layer-inversion", "layer-skip"])
    assert text.count("half of this claim lives in the architecture documents") == 1


def test_the_reviewer_is_told_the_measurement_comes_first():
    assert "is the measurement true?" in _sheet(["god-component"])


def test_an_accepted_finding_is_still_a_confirm():
    """Items 1 and 2 of round 2 are the drift/extraction cycle recorded in ADR 0003. Scoring a true
    finding as a dismissal because it was accepted would teach the calibration that correct findings are
    wrong."""
    assert "real but already accepted" in _sheet(["cycle-subsystem"])


def test_every_sign_on_a_worksheet_has_reading_guidance():
    """A signal with no guidance is one the reviewer gets no help on, which is how a round returns
    `unsure` for a whole class."""
    from spotcheck import GROUPS, _GUIDANCE
    labelled = {s for g in ("B", "C", "E", "F") for s in GROUPS[g]}
    missing = labelled - set(_GUIDANCE)
    assert missing <= {"unstable-dependency", "implicit-coupling", "extraneous-adjacent-connector",
                       "distributed-monolith"}, sorted(missing)


# --- the review kit handed to an outside reviewer ---------------------------------------------------

def _kit_module():
    """`do_kit` lives in `scripts/`, which is where the runners live; import it directly."""
    import importlib.util
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    # `scripts/spotcheck.py` resolves its own imports off sys.path at module scope, and `evalhome` lives
    # in `scripts/`. Under pytest only `tests/` is on the path.
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("spotcheck_cli", root / "scripts" / "spotcheck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _tiny_repo(path):
    import subprocess
    path.mkdir(parents=True)
    (path / "a.py").write_text("x = 1\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one"]):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _worksheet_pair(tmp_path, repo, rev):
    import json as _json
    ws = tmp_path / "worksheet-x.md"
    ws.write_text("# sheet\n\n## Getting the code\n\nclone it yourself\n\n---\n\n"
                  "## item 1 - `layer-skip:a:0`\n\nverdict:\n")
    ws.with_suffix("").with_suffix(".withheld.json").write_text(_json.dumps({
        "items": {"layer-skip:a:0": {"key": "layer-skip:a:0", "repo": repo, "rev": rev,
                                     "sign": "layer-skip", "evidence": "- measured: x"}},
        "withheld": {"layer-skip:a:0": {"severity": "high"}}}))
    return ws


def test_a_kit_never_contains_the_withheld_claims(tmp_path):
    """The one property that would invalidate the whole exercise. A reviewer who has seen the tool's
    severity is measuring agreement with us rather than with the code."""
    src = tmp_path / "src-repo"
    rev = _tiny_repo(src)
    ws = _worksheet_pair(tmp_path, "src-repo", rev)
    out = tmp_path / "kit"
    _kit_module().do_kit(ws, out, {"src-repo": src})
    assert not list(out.rglob("*withheld*"))
    assert "high" not in (out / ws.name).read_text()


def test_a_kit_repo_is_a_real_clone_not_a_worktree(tmp_path):
    """A `git worktree` leaves a pointer file at `.git` naming the repository it came from, so every git
    command in the kit fails the moment it is copied to another machine — and the failure reads as a
    corrupt kit rather than as a packaging mistake."""
    src = tmp_path / "src-repo"
    rev = _tiny_repo(src)
    out = tmp_path / "kit"
    _kit_module().do_kit(_worksheet_pair(tmp_path, "src-repo", rev), out, {"src-repo": src})
    assert (out / "repos" / "src-repo" / ".git").is_dir()


def test_a_kit_checks_out_the_revision_the_finding_was_judged_at(tmp_path):
    import subprocess
    src = tmp_path / "src-repo"
    rev = _tiny_repo(src)
    (src / "b.py").write_text("y = 2\n")            # a later commit the kit must NOT be at
    for args in (["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "two"]):
        subprocess.run(["git", "-C", str(src), *args], check=True, capture_output=True)
    out = tmp_path / "kit"
    _kit_module().do_kit(_worksheet_pair(tmp_path, "src-repo", rev), out, {"src-repo": src})
    assert not (out / "repos" / "src-repo" / "b.py").exists()


def test_the_kit_sheet_drops_instructions_for_work_the_kit_already_did(tmp_path):
    """Left in, "Getting the code" would send the reviewer to clone into /tmp and judge a checkout other
    than the one sitting beside the sheet."""
    src = tmp_path / "src-repo"
    rev = _tiny_repo(src)
    ws = _worksheet_pair(tmp_path, "src-repo", rev)
    out = tmp_path / "kit"
    _kit_module().do_kit(ws, out, {"src-repo": src})
    text = (out / ws.name).read_text()
    assert "Getting the code" not in text and "item 1" in text


# --- getting a completed sheet back ------------------------------------------------------------------

def test_a_sheet_carries_the_id_of_the_run_that_made_it():
    from spotcheck import render_worksheet, sheet_id
    text = render_worksheet([{"key": "a:b:0", "repo": "r", "rev": "v", "sign": "layer-skip",
                              "evidence": "- measured: x"}], sheet="worksheet-2026-08-22")[0]
    assert sheet_id(text) == "worksheet-2026-08-22"


def test_a_renamed_sheet_still_names_its_run():
    """The reviewer will rename it — adding their own name to a file they spent two hours on is the most
    natural thing in the world, and it used to silently break the match back to the withheld claims."""
    from spotcheck import render_worksheet, sheet_id
    text = render_worksheet([{"key": "a:b:0", "repo": "r", "rev": "v", "sign": "layer-skip",
                              "evidence": "- measured: x"}], sheet="worksheet-2026-08-22")[0]
    # renaming is a filesystem act; the identity travels inside the file, so it survives untouched
    assert sheet_id(text + "\n\n## item 1 - `a:b:0`\n\nverdict: confirm\n") == "worksheet-2026-08-22"


def test_a_sheet_with_no_marker_falls_back_to_the_sibling_rule(tmp_path):
    """Old sheets, and any file whose header a reviewer edited away, must still ingest."""
    m = _kit_module()
    ws = tmp_path / "worksheet-2026-08-01.md"
    ws.write_text("# no marker here\n")
    (tmp_path / "worksheet-2026-08-01.withheld.json").write_text("{}")
    assert m._side_file(ws).name == "worksheet-2026-08-01.withheld.json"


def test_the_kit_keeps_the_generated_filename(tmp_path):
    """So a sheet whose marker was stripped still lands beside its side file. Naming it `worksheet.md`
    guaranteed a mismatch for every reviewer who saved it straight out of the kit."""
    src = tmp_path / "src-repo"
    rev = _tiny_repo(src)
    ws = _worksheet_pair(tmp_path, "src-repo", rev)
    out = tmp_path / "kit"
    _kit_module().do_kit(ws, out, {"src-repo": src})
    assert (out / ws.name).is_file()

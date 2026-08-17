"""The recurrence suite — does an entry actually fail on the artifact it was written against?

The suite's whole value rests on one property: an entry derived from a confirmed defect must *fail* on the
artifact that contained that defect. An entry that passes there is worse than no entry, because it reports
a clean run on known-bad input — the silent-failure shape this project has hit twice already (a `require`
satisfied by `GET /{user_id}/{filename}` in a routes table, and a `forbid` whose proximity guess was twelve
characters too tight).

So there are two kinds of test here. The synthetic ones check the mechanism. The one over the real entries
checks the entries, and it is the one that matters: it is skipped, not passed, when the evaluation data
repo is absent, because a skip is honest and a pass is not.
"""

import textwrap

import pytest

from recurrence import Entry, artifact_text, check, load


def _artifact(tmp_path, **docs):
    arch = tmp_path / "architecture"
    (arch / "subsystems").mkdir(parents=True)
    for name, text in docs.items():
        (arch / name.replace("__", "/")).write_text(textwrap.dedent(text))
    return arch


def _entry(**kw):
    base = dict(id="e", target="t", rev="r", ground_truth="the truth")
    return Entry(**{**base, **kw})


# --- forbid: a claim the target contradicts -------------------------------------------------------

def test_a_restated_claim_fails(tmp_path):
    arch = _artifact(tmp_path, **{"index.md": "The store sits behind one sync.Mutex."})
    r = check([_entry(forbid=("one `?sync\\.Mutex",))], arch)[0]
    assert not r.ok and r.restated

def test_matching_is_case_insensitive(tmp_path):
    arch = _artifact(tmp_path, **{"index.md": "Sixty-Four GO Files under observer/."})
    assert not check([_entry(forbid=("64 go files|sixty-four go files",))], arch)[0].ok

def test_a_claim_the_artifact_does_not_make_passes(tmp_path):
    arch = _artifact(tmp_path, **{"index.md": "Nothing relevant here."})
    assert check([_entry(forbid=("one `?sync\\.Mutex",))], arch)[0].ok


# --- require: the omission half -------------------------------------------------------------------

def test_silence_on_a_required_topic_fails(tmp_path):
    """The reason `require` exists. A `forbid`-only entry is passed by an artifact that says nothing, and
    saying nothing is exactly how the CORS finding and the ownership gap got past two reviewers."""
    arch = _artifact(tmp_path, **{"index.md": "The server serves HTTP."})
    r = check([_entry(require=("Allow-Origin|CheckOrigin|CORS",))], arch)[0]
    assert not r.ok and r.missing

def test_a_required_topic_that_is_addressed_passes(tmp_path):
    arch = _artifact(tmp_path, **{"index.md": "CORS is `*` at handler.go:283."})
    assert check([_entry(require=("Allow-Origin|CheckOrigin|CORS",))], arch)[0].ok


# --- scope: the whole artifact, not one document --------------------------------------------------

def test_a_claim_counts_wherever_it_appears(tmp_path):
    """Which document carries a claim is the author's choice and moves between runs. An entry asks whether
    the *artifact* says a thing."""
    arch = _artifact(tmp_path, **{"index.md": "See the subsystems.",
                                  "subsystems__store.md": "Behind one sync.Mutex."})
    assert not check([_entry(forbid=("one `?sync\\.Mutex",))], arch)[0].ok

def test_templates_are_not_read(tmp_path):
    """A template ships the placeholder prose an entry might forbid; it is not a claim about the target."""
    arch = _artifact(tmp_path, **{"SUBSYSTEM_TEMPLATE.md": "Behind one sync.Mutex."})
    assert check([_entry(forbid=("one `?sync\\.Mutex",))], arch)[0].ok

def test_entries_for_other_targets_are_skipped(tmp_path):
    arch = _artifact(tmp_path, **{"index.md": "Behind one sync.Mutex."})
    assert check([_entry(target="other", forbid=("Mutex",))], arch, target="t") == []


# --- reporting ------------------------------------------------------------------------------------

def test_the_explanation_carries_the_ground_truth_not_just_the_regex(tmp_path):
    """Whoever reads a failure months later needs the fact, not the pattern. The regex says what matched;
    only the ground truth says why that is wrong."""
    arch = _artifact(tmp_path, **{"index.md": "Behind one sync.Mutex."})
    e = _entry(ground_truth="store.go:313-332 declares four locks.",
               forbid=("one `?sync\\.Mutex",), found_by="blind judge, round 2")
    text = check([e], arch)[0].explain()
    assert "four locks" in text and "RESTATED" in text and "blind judge" in text


# --- the entries themselves -----------------------------------------------------------------------

def _pairs():
    """(entries file, the artifact it was written against). Both live in the evaluation data repo."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from evalhome import eval_home
    home = eval_home()
    out = []
    for f in sorted((home / "recurrence").glob("*.toml")):
        art = home / "selfeval" / f.stem / "artifact"
        if art.is_dir():
            out.append(pytest.param(f, art, id=f.stem))
    return out


_PAIRS = _pairs()


@pytest.mark.skipif(not _PAIRS, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("entries_file,artifact", _PAIRS)
def test_every_entry_fires_on_the_artifact_it_came_from(entries_file, artifact):
    """The suite's self-check. Each of these entries was written from a defect confirmed in this exact
    artifact, which is left unfixed as evidence — so a passing entry means the entry is broken, not that
    the artifact is clean. Two were caught this way on the first run."""
    results = check(load(entries_file), artifact, target=entries_file.stem)
    assert results, f"no entries for {entries_file.stem}"
    passing = [r.entry.id for r in results if r.ok]
    assert not passing, (
        f"{len(passing)} entr{'y' if len(passing) == 1 else 'ies'} did not fire on the known-bad "
        f"artifact — the pattern is wrong, not the artifact: {passing}")


@pytest.mark.skipif(not _PAIRS, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("entries_file,artifact", _PAIRS)
def test_every_forbid_has_a_require_where_the_topic_is_load_bearing(entries_file, artifact):
    """§13's second rule, checked loosely: a `serious` entry with only negative assertions can be passed
    by deleting the paragraph. Minor factual corrections do not need the pair, and `kind = "guard"` entries
    are exempt by definition — for those, silence is the correct outcome."""
    naked = [e.id for e in load(entries_file)
             if e.severity == "serious" and e.kind == "claim" and e.forbid and not e.require]
    assert not naked, f"serious forbid-only entries (silence passes them): {naked}"


@pytest.mark.skipif(not _PAIRS, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("entries_file,artifact", _PAIRS)
def test_no_entry_splits_one_obligation_across_several_require_patterns(entries_file, artifact):
    """`require` is conjunctive, which reads wrongly to anyone writing one pattern per phrasing.

    An entry once demanded both word orders of the same pair as separate patterns, meaning "either will
    do" and enforcing "both must match" — an artifact that covered the topic properly, with its own ADR,
    was reported as silent on it. Second entry defect on record, and like the first it cried wolf.
    """
    from recurrence import ambiguous_requires
    bad = [(e.id, ambiguous_requires(e)) for e in load(entries_file)]
    bad = [(i, why) for i, why in bad if why]
    assert not bad, "\n".join(f"{i}: {why}" for i, why in bad)

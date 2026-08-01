"""The pinned-corpus regression, as opt-in tests.

Marked `corpus` and excluded from the default suite (see `pyproject.toml`): these clone real
repositories over the network and take minutes, where the rest of the suite takes seconds.

    uv run pytest -m corpus                      # check against recorded expectations
    ARCHAGENT_UPDATE_CORPUS=1 uv run pytest -m corpus    # record/refresh them — read the diff first

A change here is *expected* whenever a check genuinely improves. The workflow is the same as the golden
fixtures: read the summarised diff, confirm it is only what you meant, then re-record.
"""

import pytest

from corpus import check_or_update, load_manifest, needs_recording, run_entry

MANIFEST = load_manifest()


@pytest.mark.corpus
@pytest.mark.parametrize("entry", MANIFEST, ids=[e["name"] for e in MANIFEST])
def test_pinned_repo_output_is_unchanged(entry, tmp_path):
    if needs_recording(entry):
        pytest.skip(f"{entry['name']}: declared in the manifest, no expectation recorded yet — "
                    f"ARCHAGENT_UPDATE_CORPUS=1 uv run pytest -m corpus -k {entry['name']}")
    actual = run_entry(entry, tmp_path / entry["name"])
    diff = check_or_update(entry, actual)
    assert diff is None, (
        f"\n{entry['name']} @ {entry['rev']} changed:\n\n{diff}\n\n"
        f"If that is the change you meant, re-record with:\n"
        f"  ARCHAGENT_UPDATE_CORPUS=1 uv run pytest -m corpus -k {entry['name']}\n"
    )

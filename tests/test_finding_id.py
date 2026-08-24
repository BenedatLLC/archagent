"""`finding_id` must distinguish findings that differ (#36).

From user test round 2: the tester saw `layer-inversion:transports:da39a3ee` on distinct candidates and
named it as a reason trust dropped. `da39a3ee` is `sha1("")[:8]` — only group F passes a value set, so
every other sign hashed the empty string and the id collapsed to `sign:subjects[0]`.

The id keys the spot-check label store, `investigations/`, and `archagent investigate <id>`, so a
collision does not merely look untidy: a recorded verdict can answer a finding nobody investigated.
"""

import hashlib

from archagent.evaluate import finding_id


def test_pair_findings_out_of_one_subsystem_get_distinct_ids():
    """The exact reported case."""
    a = finding_id("layer-inversion", ["transports", "interfaces"])
    b = finding_id("layer-inversion", ["transports", "foundation"])
    assert a != b
    assert not a.endswith("da39a3ee") and not b.endswith("da39a3ee")


def test_direction_is_part_of_the_identity():
    """`a -> b` and `b -> a` are different claims about the architecture, so subject order is preserved
    while values stay sorted — values are a set, subjects are not."""
    assert finding_id("implicit-coupling", ["a", "b"]) != finding_id("implicit-coupling", ["b", "a"])


def test_a_value_set_is_still_order_independent():
    """The property the original digest existed for: the same vocabulary discovered in a different order
    is the same finding."""
    assert finding_id("enum-value-escape", ["x.py"], ["b", "a"]) == \
           finding_id("enum-value-escape", ["x.py"], ["a", "b"])


def test_single_subject_ids_are_unchanged_by_the_fix():
    """151 of the 176 ids recorded across the evaluation data are single-subject and none were
    ambiguous. Invalidating a correct human label to fix an unrelated bug costs real review work, so the
    encoding is chosen to leave them byte-identical: exactly the broken ids move."""
    legacy = hashlib.sha1(b"").hexdigest()[:8]
    assert finding_id("change-prone-file", ["a/b.py"]) == f"change-prone-file:a/b.py:{legacy}"
    assert finding_id("god-component", ["adapters"]) == f"god-component:adapters:{legacy}"


def test_subjects_and_values_cannot_be_confused_for_each_other():
    """A separator collision would let a finding with subjects (a, b) collide with one whose value set
    happens to read the same way."""
    assert finding_id("s", ["x", "a"], []) != finding_id("s", ["x"], ["a"])


def test_a_third_subject_still_changes_the_id():
    """Cycles carry more than two subjects, and truncating at two would reintroduce the collision for
    exactly the sign that produces the longest subject lists."""
    assert finding_id("cycle-subsystem", ["a", "b", "c"]) != finding_id("cycle-subsystem", ["a", "b"])

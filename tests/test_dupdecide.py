"""Check B — scattered single source of truth (dupdecide.py)."""

from archagent.dupdecide import branch_values, cluster, find_decisions

STATES = ["pending", "paid", "shipped", "refunded", "cancelled"]


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _owner(values=STATES):
    """A resolver that branches on the whole decision."""
    return "".join(f'    if state == "{v}":\n        return {i}\n' for i, v in enumerate(values))


def _piece(values):
    return "".join(f'if s == "{v}":\n    pass\n' for v in values)


def _pieces(values):
    """Three partial re-implementations, each missing a different value — so every value of the decision
    is branched on in enough files to count as duplicated, and no piece holds the whole set."""
    return [[v for v in values if v != values[i]] for i in range(3)]


def test_branch_values_reads_equality_case_and_membership():
    text = (
        'if status == "shipped":\n'
        '    pass\n'
        'elif "refunded" != status:\n'
        '    pass\n'
        'case "paid":\n'
        'if kind in ("pending", "cancelled"):\n'
        '    pass\n'
    )
    assert branch_values(text) == {"shipped", "refunded", "paid", "pending", "cancelled"}


def test_branch_values_skips_comments_and_boilerplate_literals():
    text = ('# if x == "commented_out":\n'
            'if encoding == "utf-8" or flag == "true" or name == "id":\n'
            '    pass\n'
            'if state == "shipped":\n')
    assert branch_values(text) == {"shipped"}


def test_finds_a_decision_with_its_owner_and_reimplementors(tmp_path):
    _write(tmp_path, "src/orders/state.py", _owner())
    for name, values in zip(("api", "report", "email"), _pieces(STATES)):
        _write(tmp_path, f"src/orders/{name}.py", _piece(values))
    found = find_decisions(tmp_path, {"orders": {
        "src/orders/state.py", "src/orders/api.py", "src/orders/report.py", "src/orders/email.py"}})
    assert len(found) == 1
    d = found[0]
    assert d.values == sorted(STATES)
    assert d.owner == "src/orders/state.py" and d.owner_coverage == 1.0
    assert d.reimplementors == ["src/orders/api.py", "src/orders/email.py", "src/orders/report.py"]


def test_ranks_by_the_churn_of_the_files_involved(tmp_path):
    for group, values in (("hot", STATES), ("cold", ["alpha", "beta", "gamma", "delta"])):
        _write(tmp_path, f"src/{group}/owner.py", _owner(values))
        for name, piece in zip(("a", "b", "c"), _pieces(values)):
            _write(tmp_path, f"src/{group}/{name}.py", _piece(piece))
    groups = {g: {f"src/{g}/{n}.py" for n in ("owner", "a", "b", "c")} for g in ("hot", "cold")}
    churn = {f"src/hot/{n}.py": 25 for n in ("owner", "a", "b", "c")}
    churn.update({f"src/cold/{n}.py": 1 for n in ("owner", "a", "b", "c")})
    found = find_decisions(tmp_path, groups, churn, {"src/hot/owner.py": 9})
    assert [d.subsystem for d in found] == ["hot", "cold"]
    assert found[0].churn == 100 and found[0].fix_churn == 9


def test_loose_grab_bags_are_rejected(tmp_path):
    """Values that pile up across files with nobody holding most of the set are not one decision."""
    pool = [f"tok{i}" for i in range(10)]
    files = set()
    for i in range(10):
        rel = f"src/app/f{i}.py"
        # a ring: each file branches on three neighbouring values, so every value is duplicated and the
        # values chain into one big cluster — but no file holds more than 30% of it
        _write(tmp_path, rel, _piece([pool[(i + k) % 10] for k in range(3)]))
        files.add(rel)
    assert find_decisions(tmp_path, {"app": files}) == []


def test_a_pair_of_values_is_not_a_decision(tmp_path):
    for i in range(4):
        _write(tmp_path, f"src/app/f{i}.py", _piece(["create", "edit"]))
    assert find_decisions(tmp_path, {"app": {f"src/app/f{i}.py" for i in range(4)}}) == []


def test_one_reimplementor_is_not_scattered(tmp_path):
    _write(tmp_path, "src/app/state.py", _owner())
    _write(tmp_path, "src/app/api.py", _piece(STATES[:3]))
    _write(tmp_path, "src/app/other.py", _piece(["unrelated_one", "unrelated_two"]))
    assert find_decisions(tmp_path, {"app": {
        "src/app/state.py", "src/app/api.py", "src/app/other.py"}}) == []


def test_vendored_and_generated_files_are_skipped(tmp_path):
    _write(tmp_path, "src/vendor/lib.py", _owner())
    _write(tmp_path, "src/app/gen.py", "# @generated\n" + _piece(STATES[:4]))
    _write(tmp_path, "src/app/a.py", _piece(STATES[:3]))
    _write(tmp_path, "src/app/b.py", _piece(STATES[1:4]))
    files = {"src/vendor/lib.py", "src/app/gen.py", "src/app/a.py", "src/app/b.py"}
    assert find_decisions(tmp_path, {"app": files}) == []


def test_duplication_is_looked_for_within_a_group_not_across(tmp_path):
    _write(tmp_path, "src/a/state.py", _owner())
    _write(tmp_path, "src/b/api.py", _piece(STATES[:3]))
    _write(tmp_path, "src/c/report.py", _piece(STATES[1:4]))
    groups = {"a": {"src/a/state.py"}, "b": {"src/b/api.py"}, "c": {"src/c/report.py"}}
    assert find_decisions(tmp_path, groups) == []


def test_cluster_separates_two_unrelated_decisions(tmp_path):
    colors = ["red", "green", "blue", "violet", "amber"]
    per_file = {"state.py": set(STATES), "theme.py": set(colors)}
    for i, (s, c) in enumerate(zip(_pieces(STATES), _pieces(colors))):
        per_file[f"s{i}.py"] = set(s)
        per_file[f"c{i}.py"] = set(c)
    found = cluster(per_file, subsystem="app")
    assert {d.owner for d in found} == {"state.py", "theme.py"}
    assert {tuple(d.values) for d in found} == {tuple(sorted(STATES)), tuple(sorted(colors))}

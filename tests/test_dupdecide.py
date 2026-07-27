"""Check B — scattered single source of truth (dupdecide.py)."""

from archagent.dupdecide import (
    branch_values,
    cluster,
    enum_defs,
    find_decisions,
    find_enum_escapes,
)

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


# --- the enum-value escape (the declared-owner half of Check B) ----------------------------

STATE_ENUM = '''from enum import Enum


class WorkflowState(Enum):
    """States in the workflow."""
    INITIAL = "initial"
    SELECT_NEW = "select-new"
    SUMMARIZED = "summarized"
    SEM_SEARCH = "sem-search"
    RESEARCH = "research"
'''


def _escaper(values, unwrap=False):
    lhs = "self.machine.current_state.value" if unwrap else "name"
    return "".join(f'if {lhs} == "{v}":\n    pass\n' for v in values)


def test_reads_string_valued_enum_members(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM)
    defs = enum_defs(tmp_path, {"src/app/state.py"})
    assert [d.name for d in defs] == ["WorkflowState"]
    assert defs[0].members["SEM_SEARCH"] == "sem-search"
    assert len(defs[0].members) == 5


def test_value_less_enums_are_indexed_but_cannot_be_escaped(tmp_path):
    """`RED = auto()` has no string value, so no string comparison can escape it — but the *name* is
    still needed, because other files may branch on `Color.RED` itself."""
    _write(tmp_path, "src/app/e.py",
           "from enum import Enum, auto\n\n\nclass Color(Enum):\n    RED = auto()\n    BLUE = 2\n")
    _write(tmp_path, "src/app/use.py", 'if c == Color.RED:\n    pass\n')
    defs = enum_defs(tmp_path, {"src/app/e.py"})
    assert [(d.name, d.members) for d in defs] == [("Color", {})]
    assert find_enum_escapes(tmp_path, {"src/app/e.py", "src/app/use.py"}) == []


def test_reads_typescript_enums(tmp_path):
    _write(tmp_path, "src/app/kinds.ts",
           "export enum Kind {\n  Alpha = 'alpha',\n  Beta = 'beta',\n  Gamma = 'gamma',\n}\n")
    defs = enum_defs(tmp_path, {"src/app/kinds.ts"})
    assert defs[0].name == "Kind" and defs[0].members["Beta"] == "beta"


def test_flags_a_file_comparing_against_the_raw_values(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM)
    _write(tmp_path, "src/app/chat.py", _escaper(["summarized", "sem-search", "research"]))
    found = find_enum_escapes(tmp_path, {"src/app/state.py", "src/app/chat.py"})
    assert len(found) == 1
    e = found[0]
    assert e.enum == "WorkflowState" and e.definer == "src/app/state.py"
    assert e.files == ["src/app/chat.py"]
    assert e.values == ["research", "sem-search", "summarized"]


def test_the_declaring_file_is_never_its_own_escaper(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM + '\n' + _escaper(["summarized", "research"]))
    assert find_enum_escapes(tmp_path, {"src/app/state.py"}) == []


def test_one_matching_word_is_treated_as_coincidence(tmp_path):
    """LiteLLM has a `Role` enum containing "system"; a hundred files compare a payload's role to
    "system" without knowing it exists. One value is never enough."""
    _write(tmp_path, "src/app/state.py", STATE_ENUM)
    _write(tmp_path, "src/app/other.py", _escaper(["research"]))
    assert find_enum_escapes(tmp_path, {"src/app/state.py", "src/app/other.py"}) == []


def test_two_values_need_to_be_half_the_enum(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM)                       # 5 members
    _write(tmp_path, "src/app/other.py", _escaper(["research", "summarized"]))   # 2/5 = 40%
    assert find_enum_escapes(tmp_path, {"src/app/state.py", "src/app/other.py"}) == []

    _write(tmp_path, "src/app/pair.py", "from enum import Enum\n\n\nclass Mode(Enum):\n"
                                        '    ON = "engaged"\n    OFF = "disengaged"\n')
    _write(tmp_path, "src/app/uses.py", _escaper(["engaged", "disengaged"]))     # 2/2 = 100%
    found = find_enum_escapes(tmp_path, {"src/app/pair.py", "src/app/uses.py"})
    assert [e.enum for e in found] == ["Mode"]


def test_unwrapping_with_dot_value_is_enough_on_its_own(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM)
    _write(tmp_path, "src/app/chat.py", _escaper(["summarized"], unwrap=True))
    found = find_enum_escapes(tmp_path, {"src/app/state.py", "src/app/chat.py"})
    assert found and found[0].unwrapped == {"src/app/chat.py"}


def test_dot_value_outside_python_is_an_ordinary_property(tmp_path):
    """Vue compares a Babel node's `key.value` to 'set', which has nothing to do with the enum that
    also happens to have a `set` member — so `.value` only counts as unwrapping in Python."""
    _write(tmp_path, "src/app/ops.ts", "export enum TriggerOpTypes {\n  SET = 'set',\n"
                                       "  ADD = 'add',\n  DELETE = 'delete',\n  CLEAR = 'clear',\n}\n")
    _write(tmp_path, "src/app/compile.ts", "if (p.key.value === 'set') {\n  run()\n}\n")
    assert find_enum_escapes(tmp_path, {"src/app/ops.ts", "src/app/compile.ts"}) == []


def test_a_value_two_enums_share_is_not_attributed(tmp_path):
    _write(tmp_path, "src/app/a.py", "from enum import Enum\n\n\nclass A(Enum):\n"
                                     '    X = "shared"\n    Y = "alpha"\n')
    _write(tmp_path, "src/app/b.py", "from enum import Enum\n\n\nclass B(Enum):\n"
                                     '    X = "shared"\n    Z = "beta"\n')
    _write(tmp_path, "src/app/uses.py", _escaper(["shared", "alpha", "beta"]))
    found = find_enum_escapes(tmp_path, {"src/app/a.py", "src/app/b.py", "src/app/uses.py"})
    assert all("shared" not in e.values for e in found)


def test_escapes_are_ranked_by_churn(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM)
    _write(tmp_path, "src/app/quiet.py", "from enum import Enum\n\n\nclass Quiet(Enum):\n"
                                         '    A = "alpha"\n    B = "bravo"\n    C = "charlie"\n')
    _write(tmp_path, "src/app/hot.py", _escaper(["summarized", "sem-search", "research"]))
    _write(tmp_path, "src/app/cold.py", _escaper(["alpha", "bravo", "charlie"]))
    files = {"src/app/state.py", "src/app/quiet.py", "src/app/hot.py", "src/app/cold.py"}
    found = find_enum_escapes(tmp_path, files, {"src/app/hot.py": 40, "src/app/cold.py": 1},
                              {"src/app/hot.py": 12})
    assert [e.enum for e in found] == ["WorkflowState", "Quiet"]
    assert found[0].churn == 40 and found[0].fix_churn == 12


def test_vendored_and_test_files_are_not_scanned(tmp_path):
    _write(tmp_path, "src/app/state.py", STATE_ENUM)
    _write(tmp_path, "tests/test_chat.py", _escaper(["summarized", "sem-search", "research"]))
    _write(tmp_path, "src/vendor/x.py", _escaper(["summarized", "sem-search", "research"]))
    assert find_enum_escapes(tmp_path, {"src/app/state.py", "tests/test_chat.py",
                                        "src/vendor/x.py"}) == []


def test_cross_language_escapers_are_identified(tmp_path):
    """A Python enum whose escapers are TypeScript is still a real duplicated vocabulary, but it cannot
    be fixed by importing the enum — there is no import across that boundary."""
    _write(tmp_path, "api/models.py", STATE_ENUM)
    _write(tmp_path, "web/panel.tsx", _escaper(["summarized", "sem-search", "research"]))
    _write(tmp_path, "api/service.py", _escaper(["summarized", "sem-search", "research"]))
    found = find_enum_escapes(tmp_path, {"api/models.py", "web/panel.tsx", "api/service.py"})
    e = found[0]
    assert e.definer_lang == "python"
    assert e.cross_language == ["web/panel.tsx"]
    assert e.same_language == ["api/service.py"]


def test_same_language_escapers_are_not_flagged_as_cross(tmp_path):
    _write(tmp_path, "api/models.py", STATE_ENUM)
    _write(tmp_path, "api/service.py", _escaper(["summarized", "sem-search", "research"]))
    e = find_enum_escapes(tmp_path, {"api/models.py", "api/service.py"})[0]
    assert e.cross_language == [] and e.same_language == ["api/service.py"]


def test_related_extensions_count_as_one_language(tmp_path):
    """`.ts` and `.tsx` can import each other, so an escape between them is not cross-language."""
    _write(tmp_path, "web/kinds.ts",
           "export enum Kind {\n  A = 'alpha',\n  B = 'bravo',\n  C = 'charlie',\n}\n")
    _write(tmp_path, "web/panel.tsx", _escaper(["alpha", "bravo", "charlie"]))
    e = find_enum_escapes(tmp_path, {"web/kinds.ts", "web/panel.tsx"})[0]
    assert e.cross_language == []


# --- cohesion: a decision is a dense cluster, not a chain ----------------------------------

def test_a_chain_of_coincidences_is_not_one_decision(tmp_path):
    """Union-find merges a-b, b-c, c-d into one cluster although a and d never co-occur. A large enough
    file can then 'own' most of it and clear the tightness bar. Real clusters are dense; this is not."""
    pairs = [("alpha", "bravo"), ("bravo", "charlie"), ("charlie", "delta"), ("delta", "echo")]
    per_file = {}
    for i, (a, b) in enumerate(pairs):
        for k in range(3):  # each adjacent pair co-occurs in 3 files, so union-find links the chain
            per_file[f"link{i}_{k}.py"] = {a, b}
    per_file["big.py"] = {"alpha", "bravo", "charlie", "delta", "echo"}  # touches everything
    assert cluster(per_file) == []
    loose = cluster(per_file, cohesion=0.0)
    assert loose and loose[0].cohesion < 0.6   # it is only the cohesion bar that rejects it


def test_a_dense_cluster_keeps_its_high_cohesion(tmp_path):
    per_file = {"state.py": set(STATES)}
    for i, piece in enumerate(_pieces(STATES)):
        per_file[f"p{i}.py"] = set(piece)
    found = cluster(per_file)
    assert len(found) == 1 and found[0].cohesion == 1.0


def test_keyboard_key_names_are_not_domain_values():
    """Several components each handling their own keys is ordinary event handling, and the vocabulary
    belongs to the DOM, not to this system — no file here could be its owner."""
    text = ('if key == "ArrowUp":\n    pass\n'
            'if key == "Escape":\n    pass\n'
            'if key == "shipped":\n    pass\n')
    assert branch_values(text) == {"shipped"}


def test_a_cluster_of_only_key_names_disappears(tmp_path):
    keys = ["ArrowUp", "ArrowDown", "Enter", "Escape"]
    _write(tmp_path, "src/ui/list.tsx", _piece(keys))
    _write(tmp_path, "src/ui/scroll.tsx", _piece(keys[:3]))
    _write(tmp_path, "src/ui/menu.tsx", _piece(keys[1:]))
    files = {"src/ui/list.tsx", "src/ui/scroll.tsx", "src/ui/menu.tsx"}
    assert find_decisions(tmp_path, {"ui": files}) == []


# --- the languages _CODE_EXTS advertises ---------------------------------------------------

def test_extracts_branch_values_from_go():
    assert {"pending", "shipped"} <= branch_values(
        'if kind == "pending" {\n}\nswitch kind {\ncase "shipped":\n}\n')


def test_extracts_branch_values_from_ruby():
    assert {"pending", "shipped"} <= branch_values(
        'if kind == "pending"\nend\ncase kind\nwhen "shipped"\nend\n')


def test_extracts_branch_values_from_java():
    """Java compares strings with .equals(), not ==, so the == forms alone would miss its idiom."""
    assert {"pending", "shipped"} <= branch_values(
        'if (kind.equals("pending")) { }\nswitch (kind) {\n  case "shipped": break;\n}\n')


def test_extracts_match_arms_from_kotlin_and_rust():
    kotlin = 'when (kind) {\n    "shipped" -> a()\n    "pending" -> b()\n}\n'
    rust = 'match kind {\n    "shipped" => 1,\n    "pending" => 2,\n}\n'
    assert {"pending", "shipped"} <= branch_values(kotlin)
    assert {"pending", "shipped"} <= branch_values(rust)


def test_arrow_functions_are_not_read_as_match_arms():
    """The arm pattern must not fire on JS/TS arrows, which are everywhere."""
    assert branch_values('const f = (x) => x + 1\nitems.map((i) => i.id)\nconst h = () => "shipped"\n') == set()


def test_enum_declarations_are_python_and_ts_only(tmp_path):
    """Go has no enum construct; Java/Kotlin enum bodies carry constructor args this parser can't read.
    Those files can still *escape* an enum — they just can't declare one."""
    _write(tmp_path, "src/app/status.go", 'type Status string\nconst (\n\tShipped Status = "shipped"\n)\n')
    _write(tmp_path, "src/app/Status.java", 'enum Status { SHIPPED("shipped"), PAID("paid"); }')
    defs = enum_defs(tmp_path, {"src/app/status.go", "src/app/Status.java"})
    assert all(d.members == {} for d in defs)   # no string values parsed, so nothing to escape
    assert find_enum_escapes(tmp_path, {"src/app/status.go", "src/app/Status.java"}) == []


# --- branching on enum members, not just their values ---------------------------------------

def test_branch_values_reads_enum_members_when_the_enum_is_known():
    text = ('if state == WorkflowState.SUMMARIZED:\n    pass\n'
            'if state is WorkflowState.RESEARCH:\n    pass\n'
            'case WorkflowState.INITIAL:\n'
            'if state in (WorkflowState.PAID, WorkflowState.SHIPPED):\n    pass\n')
    got = branch_values(text, {"WorkflowState"})
    assert got == {f"enum:WorkflowState.{m}" for m in
                   ("SUMMARIZED", "RESEARCH", "INITIAL", "PAID", "SHIPPED")}


def test_dotted_names_that_are_not_declared_enums_are_ignored():
    """The qualifier is checked against enums the project actually declares — otherwise every
    `self.config.DEBUG` and `os.path.sep` in the repo would become a 'decision'."""
    text = ('if x == self.config.DEBUG:\n    pass\n'
            'if y == os.sep:\n    pass\n'
            'if state == WorkflowState.DONE:\n    pass\n')
    assert branch_values(text, {"WorkflowState"}) == {"enum:WorkflowState.DONE"}
    assert branch_values(text) == set()          # without the index, none of them count


def test_enum_members_are_only_read_in_branch_positions():
    """Assigning or returning a member is not deciding on it."""
    text = ('state = WorkflowState.INITIAL\n'
            'return WorkflowState.DONE\n'
            'self.x = WorkflowState.PAID\n')
    assert branch_values(text, {"WorkflowState"}) == set()


def test_a_decision_dispatched_through_enum_members_is_found(tmp_path):
    """The well-behaved form of the shape: no raw strings anywhere, so the string scan sees nothing."""
    members = [f"WorkflowState.{m}" for m in ("INITIAL", "PAID", "SHIPPED", "REFUNDED", "CANCELLED")]
    _write(tmp_path, "src/app/state.py",
           "from enum import Enum\n\n\nclass WorkflowState(Enum):\n"
           + "".join(f"    {m.split('.')[1]} = {i}\n" for i, m in enumerate(members)))
    _write(tmp_path, "src/app/owner.py", "".join(f"if s == {m}:\n    pass\n" for m in members))
    for i, piece in enumerate(_pieces(members)):
        _write(tmp_path, f"src/app/p{i}.py", "".join(f"if s == {m}:\n    pass\n" for m in piece))
    files = {"src/app/state.py", "src/app/owner.py", *(f"src/app/p{i}.py" for i in range(3))}
    found = find_decisions(tmp_path, {"app": files})
    assert len(found) == 1
    assert found[0].values == sorted(members)
    assert found[0].owner == "src/app/owner.py"


def test_enum_members_do_not_bridge_unrelated_string_clusters(tmp_path):
    """A member used across many files is a high-degree node. Clustered together with strings it acts as
    a bridge, merging unrelated clusters into one incoherent blob that then fails the cohesion bar —
    which is how enabling member extraction first *destroyed* a real, confirmed litellm cluster."""
    oauth = ["authorization_code", "refresh_token", "client_credentials"]
    per_file = {}
    for i in range(4):  # a tight, real cluster of its own
        per_file[f"oauth{i}.py"] = set(oauth if i == 0 else oauth[: 2 + (i % 2)])
    colors = ["crimson", "cerulean", "chartreuse"]
    for i in range(4):  # a second, unrelated tight cluster
        per_file[f"theme{i}.py"] = set(colors if i == 0 else colors[: 2 + (i % 2)])
    for rel in per_file:  # a member touching *everything* — the bridge
        per_file[rel].add("enum:Mode.ACTIVE")
    owners = {d.owner for d in cluster(per_file)}
    values = {tuple(d.values) for d in cluster(per_file)}
    assert values == {tuple(sorted(oauth)), tuple(sorted(colors))}
    assert owners == {"oauth0.py", "theme0.py"}

"""The compact rule DSL parser."""

import pytest

from archagent.rules import RuleError, parse_boundary, parse_pattern, parse_property


def test_boundary_single():
    r = parse_boundary("forbid a.b -> c.d")
    assert r.sources == ["a.b"] and r.targets == ["c.d"]


def test_boundary_multiple_sources_and_targets():
    r = parse_boundary("forbid a, b -> c, d")
    assert r.sources == ["a", "b"] and r.targets == ["c", "d"]


@pytest.mark.parametrize("rule", ["forbid a b", "nope a -> b", "forbid  -> b", "forbid a ->"])
def test_boundary_errors(rule):
    with pytest.raises(RuleError):
        parse_boundary(rule)


def test_pattern_plain():
    r = parse_pattern("forbid-pattern print($$$)")
    assert r.pattern == "print($$$)" and r.scope_mode == "all" and r.scope is None


def test_pattern_in_scope():
    r = parse_pattern("forbid-pattern print($$$) in src/app/domain")
    assert (r.pattern, r.scope_mode, r.scope) == ("print($$$)", "in", "src/app/domain")


def test_pattern_outside_scope_dotted_module():
    r = parse_pattern("forbid-pattern os.environ['X'] outside app.config")
    assert (r.pattern, r.scope_mode, r.scope) == ("os.environ['X']", "outside", "app.config")


def test_pattern_with_in_keyword_is_not_treated_as_scope():
    # A pattern that itself contains " in $Y" must not be split as a scope
    # ($Y is a metavar, not a scope token).
    r = parse_pattern("forbid-pattern for $X in $Y")
    assert r.scope_mode == "all" and r.pattern == "for $X in $Y"


@pytest.mark.parametrize("rule", ["forbid-pattern ", "nope"])
def test_pattern_errors(rule):
    with pytest.raises(RuleError):
        parse_pattern(rule)


def test_property():
    assert parse_property("property tests/t.py::test_x").target == "tests/t.py::test_x"


@pytest.mark.parametrize("rule", ["nope", "property "])
def test_property_errors(rule):
    with pytest.raises(RuleError):
        parse_property(rule)

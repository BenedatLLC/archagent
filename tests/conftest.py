"""Shared test setup.

The only thing here is colour, and it is here because it cost a debugging session: the suite passed on one
machine and failed on another with `assert True is False`, because `FORCE_COLOR=3` was set in one shell.
Two different failures came out of that single variable — a CLI test asserting on a substring that rich had
split with escape codes, and a real defect where import-linter's coloured output made `check` report a
broken contract as a clean run (`tests/test_check_sample.py`).

Tests must not depend on the developer's terminal settings, so the variables are cleared for every test. A
test that is *about* colour sets them back itself with `monkeypatch.setenv`, which runs after this.
"""

import os

import pytest

# At import time, not only in the fixture below. `rich.Console` samples the environment when it is
# constructed, and the CLI constructs its console at module import — which happens during collection,
# before any fixture runs. Setting this in a fixture alone left the CLI tests still coloured.
os.environ.pop("FORCE_COLOR", None)
os.environ.pop("CLICOLOR_FORCE", None)
os.environ["NO_COLOR"] = "1"
os.environ["TERM"] = "dumb"


@pytest.fixture(autouse=True)
def _no_ambient_colour(monkeypatch):
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")

"""Configuration surface: env keys read in code vs a declared manifest."""

from archagent.configscan import declared_config_keys, read_config_keys


def test_read_python_and_js_env_keys(tmp_path):
    (tmp_path / "a.py").write_text(
        "import os\n"
        "x = os.getenv('DOC_HOME')\n"
        "y = os.environ['DATABASE_URL']\n"
        "z = os.environ.get('LOG_LEVEL', 'info')\n"
    )
    (tmp_path / "b.ts").write_text("const k = process.env.OPENAI_API_KEY;\nconst j = process.env['PORT'];\n")
    keys = read_config_keys(tmp_path, {"a.py", "b.ts"})
    assert keys == {"DOC_HOME", "DATABASE_URL", "LOG_LEVEL", "OPENAI_API_KEY", "PORT"}


def test_declared_from_env_example_and_doc(tmp_path):
    (tmp_path / ".env.example").write_text("# sample\nDOC_HOME=/data\nexport DATABASE_URL=postgres://x\n")
    doc = "# Deployment\n\n**Config:** OPENAI_API_KEY, PORT\n"
    assert declared_config_keys(tmp_path, doc) == {"DOC_HOME", "DATABASE_URL", "OPENAI_API_KEY", "PORT"}


def test_no_manifest_returns_empty(tmp_path):
    assert declared_config_keys(tmp_path, "# doc with no config line\n") == set()


def test_non_bold_config_line_is_not_a_manifest(tmp_path):
    # issue #1: only the bold **Config:** form declares keys; prose must not
    doc = ("# Deploy\n\n**Config:** REAL_KEY\n\n"
           "Configuration values are read from the environment.\n")  # sentence starting with 'Config'
    assert declared_config_keys(tmp_path, doc) == {"REAL_KEY"}


def test_config_empty_placeholder_ignored(tmp_path):
    assert declared_config_keys(tmp_path, "**Config:** _(none)_\n") == set()


# --- config read through a helper wrapper -----------------------------------------------------------

_WRAPPER_SRC = '''
import os

def get_bool_from_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true")

def get_int_from_env(name, default):
    return int(os.environ.get(name, default))

DEBUG = get_bool_from_env("PAPERLESS_DEBUG", False)
WORKERS = get_int_from_env("PAPERLESS_TASK_WORKERS", 1)
DIRECT = os.getenv("PAPERLESS_REDIS")
'''


def test_keys_read_through_a_helper_wrapper_are_found(tmp_path):
    """The blind spot calibration round 4 exposed, and it did more than hide keys.

    paperless-ngx reads 79 of its ~185 settings through `get_bool_from_env("PAPERLESS_X", ...)` and
    siblings, so those names never appear as a literal argument to `os.getenv`. A literal-only scan found
    exactly 98 keys, the artifact declared exactly those 98 — because it was written from archagent's own
    view of the surface — and `drift` then reported zero config drift in both directions, **certifying an
    incomplete list as complete**.
    """
    (tmp_path / "settings.py").write_text(_WRAPPER_SRC)
    keys = read_config_keys(tmp_path, {"settings.py"})
    assert "PAPERLESS_DEBUG" in keys, "key read through a one-hop wrapper was missed"
    assert "PAPERLESS_TASK_WORKERS" in keys
    assert "PAPERLESS_DIRECT" not in keys
    assert "PAPERLESS_REDIS" in keys           # the literal path still works
    assert "name" not in keys and "default" not in keys   # parameters are not keys


def test_a_function_that_merely_takes_a_name_is_not_a_wrapper(tmp_path):
    """Only a function that actually reaches the environment with its own parameter counts. Treating any
    `f("SOME_CONST")` as a config read would turn every string constant in the tree into a key."""
    (tmp_path / "a.py").write_text(
        "def label(name):\n    return name.title()\n\nX = label('NOT_A_KEY')\n")
    assert read_config_keys(tmp_path, {"a.py"}) == set()


def test_unresolved_reads_are_reported_rather_than_dropped(tmp_path):
    """Whatever the scanner learns to parse, some project will read config another way. Saying '98 found,
    N calls unresolved' turns a silent false negative into a stated limit — the rule `check` already
    follows when it refuses to call an unchecked artifact clean."""
    (tmp_path / "a.py").write_text(
        "import os\n"
        "KEY = 'DYNAMIC_' + suffix\n"
        "val = os.getenv(KEY)\n"
        "other = os.environ[compute()]\n"
        "fine = os.getenv('LITERAL_KEY')\n")
    keys, unresolved = read_config_keys(tmp_path, {"a.py"}, report_unresolved=True)
    assert keys == {"LITERAL_KEY"}
    assert unresolved == 2, "a non-literal read must be counted, not silently dropped"


def test_config_read_only_in_a_test_is_not_part_of_the_surface(tmp_path):
    """A test exercising `get_float_from_env("FLOAT_VAR")` is not declaring deployment configuration.

    This only bit once wrapper calls became visible: paperless-ngx's own tests for those helpers arrived
    as seven junk keys in a list of 94. Same locations `originscan` already skips.
    """
    (tmp_path / "settings.py").write_text(
        "import os\ndef get_int_from_env(name, d):\n    return int(os.getenv(name, d))\n"
        "X = get_int_from_env('REAL_KEY', 1)\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_settings.py").write_text(
        "from settings import get_int_from_env\nget_int_from_env('INT_VAR', 1)\n")
    keys = read_config_keys(tmp_path, {"settings.py", "tests/test_settings.py"})
    assert keys == {"REAL_KEY"}

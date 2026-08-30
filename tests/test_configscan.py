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
    keys, cov = read_config_keys(tmp_path, {"a.py"}, with_coverage=True)
    assert keys == {"LITERAL_KEY"}
    assert cov.seen == 3 and cov.resolved == 1, "two non-literal reads, counted rather than dropped"
    assert not cov.sound, "the surface it reports is incomplete by a known amount"
    assert "2 of 3" in cov.describe()


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


# --- pydantic-settings (issue #10) -------------------------------------------------------------------

_SETTINGS = '''
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    POSTGRES_SERVER: str
    _private: str = "x"

    @computed_field
    @property
    def dsn(self) -> str:
        return "..."
'''


def test_pydantic_settings_fields_are_config_keys(tmp_path):
    """The blind spot the issue is about. pydantic-settings populates typed class attributes from the
    environment at import time, so there is no call to read — and a scanner looking for `os.getenv`
    concludes nothing reads them. On `fastapi-template` that made `drift` report all 18 declared keys as
    dangling, and made `undocumented_config` unable to fire in the other direction."""
    (tmp_path / "config.py").write_text(_SETTINGS)
    keys = read_config_keys(tmp_path, {"config.py"})
    assert {"API_V1_STR", "SECRET_KEY", "POSTGRES_SERVER"} <= keys


def test_class_machinery_is_not_a_config_key(tmp_path):
    (tmp_path / "config.py").write_text(_SETTINGS)
    keys = read_config_keys(tmp_path, {"config.py"})
    for junk in ("model_config", "_private", "dsn", "Settings"):
        assert junk not in keys, junk


def test_env_prefix_is_applied(tmp_path):
    (tmp_path / "c.py").write_text(
        'from pydantic_settings import BaseSettings, SettingsConfigDict\n'
        'class S(BaseSettings):\n'
        '    model_config = SettingsConfigDict(env_prefix="PAPERLESS_")\n'
        '    debug: bool = False\n')
    keys = read_config_keys(tmp_path, {"c.py"})
    assert "PAPERLESS_DEBUG" in keys and "DEBUG" not in keys


def test_the_older_inner_config_class_prefix_is_applied(tmp_path):
    """pydantic v1 style, still everywhere."""
    (tmp_path / "c.py").write_text(
        'from pydantic import BaseSettings\n'
        'class S(BaseSettings):\n'
        '    debug: bool = False\n'
        '    class Config:\n'
        '        env_prefix = "APP_"\n')
    assert "APP_DEBUG" in read_config_keys(tmp_path, {"c.py"})


def test_a_lowercase_field_is_reported_as_the_env_name(tmp_path):
    """pydantic matches env vars case-insensitively, so a field `debug` is set by `DEBUG`. Reporting only
    the lowercase form would make every declared key look undeclared."""
    (tmp_path / "c.py").write_text(
        'from pydantic_settings import BaseSettings\n'
        'class S(BaseSettings):\n'
        '    debug: bool = False\n')
    assert "DEBUG" in read_config_keys(tmp_path, {"c.py"})


def test_a_subclass_of_a_settings_class_is_also_scanned(tmp_path):
    (tmp_path / "c.py").write_text(
        'from pydantic_settings import BaseSettings\n'
        'class Base(BaseSettings):\n'
        '    SHARED: str = ""\n'
        'class Prod(Base):\n'
        '    EXTRA: str = ""\n')
    keys = read_config_keys(tmp_path, {"c.py"})
    assert {"SHARED", "EXTRA"} <= keys


def test_an_unrelated_class_whose_name_ends_in_settings_is_not_scanned(tmp_path):
    """The precision risk. A dataclass called `WorkerSettings` is not a pydantic settings class, and
    treating every annotated attribute in the tree as an env key would be worse than the blind spot."""
    (tmp_path / "c.py").write_text(
        'from dataclasses import dataclass\n'
        '@dataclass\nclass WorkerSettings:\n'
        '    job_timeout: int = 300\n'
        '    NOT_AN_ENV_KEY: str = "x"\n')
    assert read_config_keys(tmp_path, {"c.py"}) == set()


def test_an_explicit_alias_wins_over_the_field_name(tmp_path):
    (tmp_path / "c.py").write_text(
        'from pydantic import Field\n'
        'from pydantic_settings import BaseSettings\n'
        'class S(BaseSettings):\n'
        '    token: str = Field(default="", alias="GITHUB_TOKEN")\n')
    keys = read_config_keys(tmp_path, {"c.py"})
    assert "GITHUB_TOKEN" in keys and "TOKEN" not in keys


def test_vite_env_reads_are_found(tmp_path):
    """`import.meta.env` is how a Vite frontend reads configuration — the only way. Missing it reported
    `VITE_API_URL` as declared-but-unread on `fastapi-template` while `main.tsx:16` reads it."""
    (tmp_path / "main.tsx").write_text(
        'OpenAPI.BASE = import.meta.env.VITE_API_URL\n'
        'const m = import.meta.env["VITE_MODE"]\n')
    assert {"VITE_API_URL", "VITE_MODE"} <= read_config_keys(tmp_path, {"main.tsx"})


# --- a key written for another process to read (issue #29) -------------------------------------------

def test_an_env_assignment_counts_as_configuration(tmp_path):
    """obstudio's TypeScript extension writes `env.WEAVER_PATH = weaver` to configure the Go binary it
    spawns. The reader is invisible — archagent does not parse Go — but the writer is right there, and
    the key was reported as declared-but-never-read. A write is arguably better evidence than a read:
    whoever wrote it knew the name mattered."""
    from archagent.configscan import read_config_keys
    (tmp_path / "a.ts").write_text("const env = {...process.env};\nenv.WEAVER_PATH = weaver;\n")
    assert "WEAVER_PATH" in read_config_keys(tmp_path, {"a.ts"})


def test_an_env_object_handed_to_a_spawn_counts(tmp_path):
    """Anchored on `env:` and brace-matched. obstudio's block is fourteen keys and the one that mattered
    sat past any reasonable fixed window from the `spawn(`."""
    from archagent.configscan import read_config_keys
    (tmp_path / "a.ts").write_text(
        "spawn(bin, args, {\n  env: {\n    OTLP_HOST: h,\n    PORT: String(p),\n"
        "    ...(x ? { OBSTUDIO_WORKSPACE_ROOT: root } : {}),\n  },\n  stdio: 'pipe',\n});\n")
    keys = read_config_keys(tmp_path, {"a.ts"})
    assert {"OTLP_HOST", "PORT", "OBSTUDIO_WORKSPACE_ROOT"} <= keys


def test_an_ordinary_object_is_not_read_as_configuration(tmp_path):
    """`{ FOO: bar }` on its own is a dictionary. The `env:` label is what makes this specific rather
    than a sweep for shouting keys."""
    from archagent.configscan import read_config_keys
    (tmp_path / "a.ts").write_text("const HTTP_CODES = { NOT_FOUND: 404, SERVER_ERROR: 500 };\n")
    assert read_config_keys(tmp_path, {"a.ts"}) == set()


def test_a_lowercase_or_short_name_is_not_an_env_key(tmp_path):
    from archagent.configscan import read_config_keys
    (tmp_path / "a.ts").write_text("env.path = p;\nenv.ID = i;\n")
    assert read_config_keys(tmp_path, {"a.ts"}) == set()


def test_python_environ_writes_count_too(tmp_path):
    from archagent.configscan import read_config_keys
    (tmp_path / "a.py").write_text(
        "import os\nos.environ['CUDA_VISIBLE_DEVICES'] = '0'\nos.environ.setdefault('TOKENIZERS', '1')\n")
    assert {"CUDA_VISIBLE_DEVICES", "TOKENIZERS"} <= read_config_keys(tmp_path, {"a.py"})


def test_a_whitespace_padded_literal_read_is_not_counted_as_opaque(tmp_path):
    """`os.getenv( "KEY" )` is a literal read, however it is spaced.

    The pattern was `\\(\\s*(?!['"])`, which matches it anyway: the engine backtracks `\\s*` to zero
    characters, looks ahead at the space and succeeds. Harmless while the count was internal, and wrong
    once #46 put it in front of a reader as "this scan was incomplete"."""
    (tmp_path / "a.py").write_text(
        "import os\n"
        "a = os.getenv( 'PADDED' )\n"
        "b = os.environ[ 'ALSO_PADDED' ]\n"
        "c = os.getenv(computed)\n")
    keys, cov = read_config_keys(tmp_path, {"a.py"}, with_coverage=True)
    assert {"PADDED", "ALSO_PADDED"} <= keys
    assert cov.seen - cov.resolved == 1, "only the computed read is opaque"

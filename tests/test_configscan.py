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

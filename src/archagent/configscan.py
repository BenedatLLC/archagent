"""Configuration surface — the environment keys the code reads vs. what's declared.

Extraction is static (regex, no execution):
  - Python: `os.getenv("X")`, `os.environ["X"]`, `os.environ.get("X")`.
  - JS/TS:  `process.env.X`, `process.env["X"]`.

The *declared* config is a committed manifest when one exists — `.env.example` / `.env.sample` /
`.env.template` (the `KEY=` names) — plus any `**Config:**` lines in the architecture docs. `drift`
reports keys read-but-undeclared (undocumented) and declared-but-unread (dangling), gated on a manifest
existing so it stays low-noise.
"""

from __future__ import annotations

import re
from pathlib import Path

_KEY = r"([A-Za-z_][A-Za-z0-9_]*)"
_ENV_READS = [
    re.compile(r"os\.getenv\(\s*['\"]" + _KEY),
    re.compile(r"os\.environ\.get\(\s*['\"]" + _KEY),
    re.compile(r"os\.environ\[\s*['\"]" + _KEY),
    re.compile(r"process\.env\." + _KEY),
    re.compile(r"process\.env\[\s*['\"]" + _KEY),
]
_ENV_FILE = re.compile(r"^\s*(?:export\s+)?" + _KEY + r"\s*=", re.MULTILINE)
_CONFIG_DOC = re.compile(r"^\s*\*{0,2}Config:?\*{0,2}\s*[:：]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_MANIFEST_GLOBS = (".env.example", ".env.sample", ".env.template", "*.env.example")
_CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def read_config_keys(root: Path, source_files: set[str]) -> set[str]:
    keys: set[str] = set()
    for rel in source_files:
        if not rel.endswith(_CODE_EXTS):
            continue
        try:
            text = (root / rel).read_text()
        except OSError:
            continue
        for pat in _ENV_READS:
            keys.update(pat.findall(text))
    return keys


def declared_config_keys(root: Path, doc_text: str) -> set[str]:
    keys: set[str] = set()
    for glob in _MANIFEST_GLOBS:
        for p in root.glob(glob):
            if p.is_file():
                try:
                    keys.update(_ENV_FILE.findall(p.read_text()))
                except OSError:
                    pass
    for m in _CONFIG_DOC.finditer(doc_text):
        keys.update(k.strip().strip("`") for k in re.split(r"[,\s]+", m.group(1).strip()) if k.strip())
    return keys

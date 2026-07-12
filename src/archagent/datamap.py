"""Datastore touch-point extraction (static, no execution) — the input for `evaluate` group A.

For each source file, find which persistent stores it touches: relational tables (SQLAlchemy /
Django ORM declarations + raw SQL), document collections (Mongo), and datastore connection keys
(`*_DB_URL`-style env vars). We distinguish a **definition** (the file that declares the ORM mapping —
the owner of that data) from a **use** (a query / raw SQL / connection). `evaluate` aggregates these to
the service level (via subsystem `**Service:**`) to flag shared persistence, duplicated sources of
truth, and inappropriate cross-service data access.

Deliberately conservative regexes over a handful of common patterns — recall isn't the goal, low-noise
high-precision signals are. Python + JS/TS text; no framework imported, no DB touched.
"""

from __future__ import annotations

import re
from pathlib import Path

# --- ORM ownership: the file that declares the table/mapping owns that data ---------------
_TABLENAME = re.compile(r"""__tablename__\s*=\s*["']([A-Za-z_]\w*)["']""")          # SQLAlchemy ORM
_DB_TABLE = re.compile(r"""db_table\s*=\s*["']([A-Za-z_]\w*)["']""")                # Django Meta.db_table
_TABLE_CTOR = re.compile(r"""\bTable\(\s*["']([A-Za-z_]\w*)["']""")                 # SQLAlchemy Core Table("x")

# --- uses: raw SQL + document-collection access -------------------------------------------
_SQL_TABLE = re.compile(r"""\b(?:FROM|JOIN|INTO|UPDATE)\s+["'`]?([A-Za-z_]\w*)["'`]?""", re.IGNORECASE)
_COLLECTION = re.compile(
    r"""\.(?:get_collection|collection)\(\s*["']([A-Za-z_]\w*)["']"""   # db.get_collection("x")
    r"""|\bdb\[\s*["']([A-Za-z_]\w*)["']\s*\]""",                        # db["x"]
)

# --- datastore connection keys (a coarse store identity two services can share) ------------
_ENV_KEY = re.compile(
    r"""os\.getenv\(\s*["']([A-Z0-9_]+)["']"""
    r"""|os\.environ(?:\.get\()?\[?\s*["']([A-Z0-9_]+)["']"""
    r"""|process\.env\.([A-Za-z0-9_]+)"""
    r"""|process\.env\[\s*["']([A-Za-z0-9_]+)["']\s*\]""",
)
_DBISH = re.compile(r"DB|DATABASE|POSTGRES|MYSQL|MONGO|REDIS|SQL|DSN|DATASTORE", re.IGNORECASE)
_SQL_KEYWORD_NOISE = {"select", "where", "table", "values", "set", "as", "on"}
# a language import statement also contains the word "from" — don't read it as SQL `FROM <table>`
_IMPORT_LINE = re.compile(r"""^\s*(?:from\s+\S+\s+import\b|import\b|export\b.*\bfrom\b|.*\brequire\()""")


def table_defs(root: Path, rel: str) -> set[str]:
    """Tables this file *owns* — declares an ORM mapping / schema for."""
    text = _read(root, rel)
    if text is None:
        return set()
    out: set[str] = set()
    for rx in (_TABLENAME, _DB_TABLE, _TABLE_CTOR):
        out.update(m.group(1) for m in rx.finditer(text))
    return out


def store_touches(root: Path, rel: str) -> set[str]:
    """Every persistent store this file references: owned tables + raw-SQL tables + collections +
    datastore connection keys. Store ids are prefixed so a table `orders` and an env key `ORDERS_DB`
    can't collide: `table:orders`, `store:ORDERS_DB_URL`."""
    text = _read(root, rel)
    if text is None:
        return set()
    tables: set[str] = set(table_defs(root, rel))
    sql_text = "\n".join(ln for ln in text.splitlines() if not _IMPORT_LINE.match(ln))
    tables.update(m.group(1) for m in _SQL_TABLE.finditer(sql_text) if m.group(1).lower() not in _SQL_KEYWORD_NOISE)
    for m in _COLLECTION.finditer(text):
        tables.add(m.group(1) or m.group(2))
    out = {f"table:{t}" for t in tables}
    for m in _ENV_KEY.finditer(text):
        key = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if key and _DBISH.search(key):
            out.add(f"store:{key}")
    return out


def _read(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text()
    except OSError:
        return None

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
# Capture the SQL keyword (group 1) alongside the table (group 2) so we can require the *companion* verb of
# a real statement nearby before trusting the match. Without that gate, `FROM`/`INTO` — common English words
# — matched ordinary prose (docstrings, LLM-prompt strings) as tables named "the"/"its" (see the datamap
# false-positive bug: 77% of one real run's findings). A match is only a table reference when the statement's
# other half is present: SELECT/DELETE before FROM/JOIN, INSERT before INTO, SET after UPDATE.
_SQL_TABLE = re.compile(r"""\b(FROM|JOIN|INTO|UPDATE)\s+["'`]?([A-Za-z_]\w*)["'`]?""", re.IGNORECASE)
_SELECT_DELETE = re.compile(r"\b(?:SELECT|DELETE)\b", re.IGNORECASE)
_INSERT = re.compile(r"\bINSERT\b", re.IGNORECASE)
_SET_KW = re.compile(r"\bSET\b", re.IGNORECASE)
_SQL_CTX_WINDOW = 200  # chars around the match to look for the companion verb
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
# A backstop for the residual "companion verb happens to appear in the same sentence" case (e.g. "Select the
# winner from the candidates"): pure English function words are never real table/collection names. Kept to
# closed-class words so a plausible table like `events`/`cache` is not filtered.
_ENGLISH_STOPWORDS = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "their", "them", "they", "his", "her",
    "our", "your", "my", "any", "all", "each", "every", "some", "no", "one", "two", "both", "other",
    "and", "or", "but", "if", "then", "than", "so", "as", "of", "to", "in", "into", "onto", "at", "by",
    "for", "with", "from", "up", "out", "off", "over", "under", "inside", "within", "per", "via",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "has", "have", "had",
    "here", "there", "where", "when", "which", "who", "what", "how", "why", "not", "such", "same",
}
# a language import statement also contains the word "from" — don't read it as SQL `FROM <table>`
_IMPORT_LINE = re.compile(r"""^\s*(?:from\s+\S+\s+import\b|import\b|export\b.*\bfrom\b|.*\brequire\()""")


def _sql_context_ok(text: str, m: "re.Match[str]") -> bool:
    """True if a `_SQL_TABLE` match sits in a real SQL statement: the companion verb is nearby. SELECT/DELETE
    before FROM/JOIN, INSERT before INTO, SET after UPDATE — all within a small window. This is the gate that
    keeps English prose ("download from the bucket into its workspace") from being read as table references."""
    kw = m.group(1).upper()
    before = text[max(0, m.start() - _SQL_CTX_WINDOW):m.start()]
    after = text[m.end():m.end() + _SQL_CTX_WINDOW]
    if kw in ("FROM", "JOIN"):
        return bool(_SELECT_DELETE.search(before))
    if kw == "INTO":
        return bool(_INSERT.search(before))
    if kw == "UPDATE":
        return bool(_SET_KW.search(after))
    return False


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
    for m in _SQL_TABLE.finditer(sql_text):
        name = m.group(2)
        low = name.lower()
        if low in _SQL_KEYWORD_NOISE or low in _ENGLISH_STOPWORDS:
            continue
        if _sql_context_ok(sql_text, m):  # require a real SQL statement, not prose with "from"/"into"
            tables.add(name)
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

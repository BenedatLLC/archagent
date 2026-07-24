"""archagent datamap — static datastore touch-point extraction (input for evaluate group A)."""

from archagent.datamap import store_touches, table_defs


def _w(tmp, rel, text):
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return rel


def test_table_defs_across_orms(tmp_path):
    _w(tmp_path, "sa.py", 'class Order(Base):\n    __tablename__ = "orders"\n')
    _w(tmp_path, "dj.py", 'class Meta:\n    db_table = "customers"\n')
    _w(tmp_path, "core.py", 't = Table("invoices", metadata)\n')
    assert table_defs(tmp_path, "sa.py") == {"orders"}
    assert table_defs(tmp_path, "dj.py") == {"customers"}
    assert table_defs(tmp_path, "core.py") == {"invoices"}


def test_store_touches_includes_sql_collections_and_db_keys(tmp_path):
    _w(tmp_path, "q.py",
       'sql = "SELECT * FROM orders JOIN lines ON x"\n'
       'c = db.get_collection("events")\n'
       'u = os.getenv("ORDERS_DB_URL")\n'
       'log = os.getenv("LOG_LEVEL")\n')  # not DB-ish -> excluded
    touches = store_touches(tmp_path, "q.py")
    assert "table:orders" in touches
    assert "table:lines" in touches
    assert "table:events" in touches
    assert "store:ORDERS_DB_URL" in touches
    assert "store:LOG_LEVEL" not in touches


def test_sql_keywords_not_treated_as_tables(tmp_path):
    _w(tmp_path, "q.py", 'sql = "UPDATE set x = 1"\n')  # "set" is noise, not a table
    assert "table:set" not in store_touches(tmp_path, "q.py")


def test_import_statements_are_not_read_as_sql(tmp_path):
    _w(tmp_path, "py.py", "from pkg import shared\n")          # Python import, not SQL FROM
    _w(tmp_path, "js.ts", "import x from 'orders'\n")           # JS import, not SQL FROM
    assert store_touches(tmp_path, "py.py") == set()
    assert store_touches(tmp_path, "js.ts") == set()


def test_english_prose_is_not_read_as_sql(tmp_path):
    # the datamap FP bug: prose with "from"/"into"/"update" and no companion SQL verb must yield nothing
    _w(tmp_path, "prompts.py",
       'PROMPT = """\n'
       'Download the file from the bucket into its own workspace.\n'
       'Generate a PDF report from these results, then update the record.\n'
       'Getting data from one agent to another keeps it consistent.\n'
       '"""\n')
    assert store_touches(tmp_path, "prompts.py") == set()


def test_real_sql_still_detected(tmp_path):
    _w(tmp_path, "q.py",
       'a = "SELECT * FROM orders"\n'
       'b = "DELETE FROM sessions WHERE id = 1"\n'
       'c = "INSERT INTO audit_log (x) VALUES (1)"\n'
       'd = "UPDATE customers SET name = 2"\n'
       'e = "SELECT a FROM invoices JOIN lines ON invoices.id = lines.invoice_id"\n')
    touches = store_touches(tmp_path, "q.py")
    assert {"table:orders", "table:sessions", "table:audit_log",
            "table:customers", "table:invoices", "table:lines"} <= touches


def test_into_without_insert_is_prose(tmp_path):
    _w(tmp_path, "p.py", 's = "copy the payload into the wrapper"\n')   # INTO but no INSERT -> not a table
    assert store_touches(tmp_path, "p.py") == set()


def test_from_without_select_is_prose(tmp_path):
    _w(tmp_path, "p.py", 's = "read bytes from the stream"\n')          # FROM but no SELECT/DELETE
    assert store_touches(tmp_path, "p.py") == set()


def test_stopword_table_name_filtered_even_with_verb(tmp_path):
    # "Select the winner from the candidates" — SELECT precedes FROM, but "the" is a stopword, not a table
    _w(tmp_path, "p.py", 's = "Select the winner from the candidates list"\n')
    assert "table:the" not in store_touches(tmp_path, "p.py")

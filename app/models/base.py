"""Database access and the one rule of this system.

Every model module imports from here. No SQL anywhere else in the app.

The rule: a fact may be read only after its known_at moment. `visible()`
wraps a table in that filter, and every query that touches a fact table
goes through it. Break this and the replay silently starts seeing the
future, which is the one mistake that would invalidate the whole demo.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

from config import get_config

_cfg = get_config()
_lock = threading.Lock()
_SCHEMA = Path(__file__).with_name("schema.sql")

# Tables carrying a known_at column: only these may be wrapped by visible().
FACT_TABLES = {
    "prices": "known_at",
    "events": "known_at",
    "news_articles": "known_at",
}


_conn: duckdb.DuckDBPyConnection | None = None


def _root() -> duckdb.DuckDBPyConnection:
    """One connection per process, opened read-write.

    DuckDB refuses to open the same file twice in one process with
    different settings, so a mix of read-only and read-write handles blows
    up the moment a request reads and then writes. Holding a single
    connection and handing out cursors is the supported pattern: cursors
    are independent enough for Flask's threads, and there is only ever one
    configuration.
    """
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
                _conn = duckdb.connect(str(_cfg.DB_PATH))
    return _conn


def init_db() -> None:
    """Create the file and every table. Safe to run repeatedly."""
    with connect() as con:
        con.execute(_SCHEMA.read_text())


@contextmanager
def connect(read_only: bool = False):
    """A cursor on the shared connection.

    read_only is accepted so existing call sites keep working, but it no
    longer opens a second handle; it is documentation of intent only.
    """
    cur = _root().cursor()
    try:
        yield cur
    finally:
        cur.close()


def visible(table: str, as_of: str, alias: str | None = None) -> str:
    """The gate. Returns a subquery of `table` holding only rows already
    public at the end of `as_of`. Use it in place of the table name:

        sql = f"SELECT * FROM {visible('prices', as_of, 'p')} WHERE p.ticker = ?"
    """
    if table not in FACT_TABLES:
        raise ValueError(f"{table} has no known_at column; do not wrap it")
    col = FACT_TABLES[table]
    sub = f"(SELECT * FROM {table} WHERE {col} <= TIMESTAMP '{as_of} 23:59:59')"
    return f"{sub} AS {alias}" if alias else sub


def query(sql: str, params: list | tuple | None = None) -> pd.DataFrame:
    with connect(read_only=True) as con:
        return con.execute(sql, params or []).df()


def query_one(sql: str, params: list | tuple | None = None):
    with connect(read_only=True) as con:
        row = con.execute(sql, params or []).fetchone()
    return row


def execute(sql: str, params: list | tuple | None = None) -> None:
    # writes are serialized: DuckDB allows one writer at a time
    with _lock, connect() as con:
        con.execute(sql, params or [])


def execute_many(sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with _lock, connect() as con:
        con.executemany(sql, rows)


def insert_df(table: str, df: pd.DataFrame, replace: bool = False) -> int:
    """Insert a DataFrame whose columns match the table's, in order."""
    if df.empty:
        return 0
    bad = [c for c in df.columns
           if df[c].map(lambda v: isinstance(v, (pd.Series, pd.DataFrame, dict, list))).any()]
    if bad:
        raise ValueError(
            f"insert into {table}: columns {bad} contain non-scalar values "
            "(usually a duplicated pandas index turning .loc into a Series)")
    with _lock, connect() as con:
        if replace:
            con.execute(f"DELETE FROM {table}")
        con.register("_incoming", df)
        cols = ", ".join(df.columns)
        con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _incoming")
        con.unregister("_incoming")
    return len(df)


def truncate(*tables: str) -> None:
    with _lock, connect() as con:
        for t in tables:
            con.execute(f"DELETE FROM {t}")


def table_counts() -> dict[str, int]:
    with connect(read_only=True) as con:
        names = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        return {n: con.execute(f"SELECT count(*) FROM {n}").fetchone()[0] for n in names}
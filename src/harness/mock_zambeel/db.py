"""SQLite connection and schema setup for data/harness.db."""

import os
import sqlite3
from importlib.resources import files
from pathlib import Path

DEFAULT_DB_PATH = Path("data/harness.db")


def db_path() -> Path:
    """HARNESS_DB if set, else data/harness.db."""
    return Path(os.environ.get("HARNESS_DB") or DEFAULT_DB_PATH)


def connect(path: str | Path | None = None, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """check_same_thread=False only for a connection handed between threads but never shared at the same time
    (the HTTP API: FastAPI may run a request's dependency and its endpoint on different worker threads)."""
    path = Path(path) if path is not None else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(files("harness.mock_zambeel").joinpath("schema.sql").read_text())


def reset_db(path: str | Path | None = None) -> sqlite3.Connection:
    """Delete the DB file and recreate the empty schema. Returns an open connection."""
    path = Path(path) if path is not None else db_path()
    path.unlink(missing_ok=True)
    conn = connect(path)
    init_schema(conn)
    return conn

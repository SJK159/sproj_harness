"""SQLite connection and schema setup for data/harness.db."""

import os
import sqlite3
from importlib.resources import files
from pathlib import Path

DEFAULT_DB_PATH = Path("data/harness.db")


def db_path() -> Path:
    """HARNESS_DB if set, else data/harness.db."""
    return Path(os.environ.get("HARNESS_DB") or DEFAULT_DB_PATH)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path is not None else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
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

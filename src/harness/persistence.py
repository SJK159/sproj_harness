"""Backends, filesystem permissions, the checkpointer and the long-term store.

Virtual filesystem the agent sees (CompositeBackend routes, prefix stripped before forwarding):
  /skills/...    -> repo skills/ folder (read-only)
  /rules/...     -> repo seed/ folder (read-only; standing rules)
  /memories/...  -> StoreBackend on the SqliteStore, one namespace per student (read-only to file tools;
                    notes are added by save_case_note, see harness.memory)
  anything else  -> StateBackend: per-thread scratch files kept in graph state

Two kinds of persistence:
  checkpointer (data/checkpoints.db): short-term, one thread's state, so a paused case can resume.
  store (data/store.db): long-term, shared across threads, keyed by namespace (here: per student).
"""

import os
import sqlite3
from pathlib import Path

from deepagents import FilesystemPermission
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.base import BaseStore
from langgraph.store.sqlite import SqliteStore

from harness.memory import memory_namespace

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_DB = REPO_ROOT / "data" / "checkpoints.db"
STORE_DB = REPO_ROOT / "data" / "store.db"

# Skills, standing rules and memory notes cannot be written with file tools.
READ_ONLY = [
    FilesystemPermission(operations=["write"], paths=["/skills/**", "/rules/**", "/memories/**"], mode="deny"),
]


def build_backend(store: BaseStore) -> CompositeBackend:
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=REPO_ROOT / "skills", virtual_mode=True),
            "/rules/": FilesystemBackend(root_dir=REPO_ROOT / "seed", virtual_mode=True),
            "/memories/": StoreBackend(namespace=memory_namespace, store=store),
        },
    )


def open_checkpointer(path: Path = CHECKPOINT_DB) -> SqliteSaver:
    """SQLite checkpointer: each thread's state survives process restarts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def store_path() -> Path:
    return Path(os.environ.get("HARNESS_STORE") or STORE_DB)


def open_store(path: Path | None = None) -> SqliteStore:
    """SQLite long-term store (survives restarts). Same connection settings as SqliteStore.from_conn_string."""
    path = Path(path) if path is not None else store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(sqlite3.connect(path, check_same_thread=False, isolation_level=None))
    store.setup()
    return store

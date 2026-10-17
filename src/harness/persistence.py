"""Backends, filesystem permissions and the checkpointer.

Virtual filesystem the agent sees (CompositeBackend routes, prefix stripped before forwarding):
  /skills/...  -> repo skills/ folder (read-only)
  /rules/...   -> repo seed/ folder (read-only; standing rules)
  anything else -> StateBackend: per-thread scratch files kept in graph state
"""

import sqlite3
from pathlib import Path

from deepagents import FilesystemPermission
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from langgraph.checkpoint.sqlite import SqliteSaver

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_DB = REPO_ROOT / "data" / "checkpoints.db"

# Skills and standing rules are fixed by the operators; the agent may read them, never change them.
READ_ONLY = [FilesystemPermission(operations=["write"], paths=["/skills/**", "/rules/**"], mode="deny")]


def build_backend() -> CompositeBackend:
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=REPO_ROOT / "skills", virtual_mode=True),
            "/rules/": FilesystemBackend(root_dir=REPO_ROOT / "seed", virtual_mode=True),
        },
    )


def open_checkpointer(path: Path = CHECKPOINT_DB) -> SqliteSaver:
    """SQLite checkpointer: each thread's state survives process restarts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))

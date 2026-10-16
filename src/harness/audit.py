"""Append-only audit log writer (FR-10, CLAUDE.md invariant 4).

`audit_events` rejects UPDATE and DELETE at the database level (triggers in schema.sql).
"""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any


def write_event(
    conn: sqlite3.Connection,
    case_id: str,
    actor: str,
    action: str,
    from_state: str | None = None,
    to_state: str | None = None,
    detail: dict[str, Any] | None = None,
) -> int:
    """Insert one audit row and return its event_id.

    Never commits: it runs inside the caller's transaction, so the audit row and the
    change it describes are written together or not at all.
    """
    cur = conn.execute(
        """INSERT INTO audit_events (case_id, actor, action, from_state, to_state, timestamp, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            case_id,
            actor,
            action,
            from_state,
            to_state,
            datetime.now(UTC).isoformat(timespec="microseconds"),
            json.dumps(detail) if detail is not None else None,
        ),
    )
    return cur.lastrowid

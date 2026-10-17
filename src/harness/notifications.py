"""Notifications to students and instructors: a table standing in for email or a portal inbox."""

import sqlite3
from datetime import UTC, datetime
from typing import Any


def notify(conn: sqlite3.Connection, recipient_id: str, case_id: str | None, kind: str, message: str) -> int:
    """Insert one notification. Never commits: it joins the caller's transaction."""
    cur = conn.execute(
        "INSERT INTO notifications (recipient_id, case_id, kind, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (recipient_id, case_id, kind, message, datetime.now(UTC).isoformat(timespec="seconds")),
    )
    return cur.lastrowid


def unread(conn: sqlite3.Connection, recipient_id: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM notifications WHERE recipient_id = ? AND read_at IS NULL ORDER BY notification_id",
        (recipient_id,),
    )]


def mark_read(conn: sqlite3.Connection, notification_ids: list[int]) -> None:
    with conn:
        conn.executemany(
            "UPDATE notifications SET read_at = ? WHERE notification_id = ?",
            [(datetime.now(UTC).isoformat(timespec="seconds"), i) for i in notification_ids],
        )

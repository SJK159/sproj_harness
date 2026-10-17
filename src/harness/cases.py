"""Case state machine. `transition` is the only code path that changes `cases.state`."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from harness.audit import write_event

# CLAUDE.md "Case states". Terminal states map to an empty set.
TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"AWAITING_CONFIRMATION", "CANCELLED"}),
    "AWAITING_CONFIRMATION": frozenset({"SUBMITTED", "CANCELLED"}),
    "SUBMITTED": frozenset({"AWAITING_APPROVAL", "CANCELLED"}),  # CANCELLED: no longer eligible at submit
    "AWAITING_APPROVAL": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"EXECUTING", "FAILED"}),  # FAILED: approval token refused at execution (flagged)
    "EXECUTING": frozenset({"COMPLETED", "FAILED"}),
    "REJECTED": frozenset(),
    "COMPLETED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}


class UnknownCase(Exception):
    pass


class InvalidTransition(Exception):
    pass


def get_case(conn: sqlite3.Connection, case_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if row is None:
        raise UnknownCase(f"No case {case_id!r}.")
    return dict(row)


def create_case(conn: sqlite3.Connection, case_id: str, student_id: str, offering_id: str, actor: str) -> None:
    """Insert a case in DRAFT and write its audit row. Never commits (caller's transaction)."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)
           VALUES (?, ?, ?, 'FORCE_ENROLLMENT', 'DRAFT', ?, ?)""",
        (case_id, student_id, offering_id, now, now),
    )
    write_event(conn, case_id, actor, "CREATE", None, "DRAFT", {"offering_id": offering_id})


def transition(
    conn: sqlite3.Connection,
    case_id: str,
    to_state: str,
    actor: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Move a case to `to_state` and write its audit row. Never commits (caller's transaction).

    The UPDATE is conditional on the state just read, so a concurrent change makes this
    raise instead of silently overwriting it.
    """
    from_state = get_case(conn, case_id)["state"]
    if to_state not in TRANSITIONS[from_state]:
        raise InvalidTransition(f"Case {case_id}: {from_state} -> {to_state} is not allowed.")
    cur = conn.execute(
        "UPDATE cases SET state = ?, updated_at = ? WHERE case_id = ? AND state = ?",
        (to_state, datetime.now(UTC).isoformat(timespec="seconds"), case_id, from_state),
    )
    if cur.rowcount != 1:
        raise InvalidTransition(f"Case {case_id} changed state concurrently; expected {from_state}.")
    write_event(conn, case_id, actor, action, from_state, to_state, detail)

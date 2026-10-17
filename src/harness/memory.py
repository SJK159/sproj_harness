"""Per-student long-term memory: case notes in the LangGraph store.

The agent sees them as the file /memories/notes.md (CompositeBackend route -> StoreBackend). Each student
has their own namespace, built from the runtime context the caller sets, never from a path the model
writes. File tools cannot write /memories/** (persistence.READ_ONLY); notes are added only by
save_case_note, from the case record, so nothing said in a conversation can reach a later system prompt.
"""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from langgraph.store.base import BaseStore

NOTES_PATH = "/memories/notes.md"
NOTES_KEY = "/notes.md"  # key inside the namespace: CompositeBackend strips the "/memories" prefix
FINAL_STATES = ("COMPLETED", "FAILED", "REJECTED", "CANCELLED")
_HEADER = "# Past force-enrollment requests (written by the system from case records)\n"


def namespace_for(student_id: str) -> tuple[str, ...]:
    return ("students", student_id, "memories")


def memory_namespace(runtime: Any) -> tuple[str, ...]:
    """StoreBackend namespace factory: the student comes from the runtime context, or nothing is read."""
    student_id = getattr(getattr(runtime, "context", None), "student_id", None)
    if not student_id:
        raise RuntimeError("No signed-in student in the runtime context; memory is unavailable.")
    return namespace_for(student_id)


def read_notes(store: BaseStore, student_id: str) -> str:
    item = store.get(namespace_for(student_id), NOTES_KEY)
    return item.value["content"] if item else ""


def append_note(store: BaseStore, student_id: str, case_id: str, line: str) -> bool:
    """Append one line for a case; False if that case already has a note (idempotent)."""
    content = read_notes(store, student_id)
    if f" {case_id}:" in content:
        return False
    now = datetime.now(UTC).isoformat(timespec="seconds")
    item = store.get(namespace_for(student_id), NOTES_KEY)
    created = item.value.get("created_at", now) if item else now
    store.put(namespace_for(student_id), NOTES_KEY, {
        "content": (content or _HEADER) + line + "\n",
        "encoding": "utf-8",
        "created_at": created,
        "modified_at": now,
    })
    return True


def case_note(conn: sqlite3.Connection, case: dict[str, Any]) -> str:
    """One line of facts about a finished case, built only from database rows."""
    date = case["updated_at"][:10]
    head = f"- {date} {case['case_id']}: force enrollment in {case['offering_id']} {case['state']}"
    approval = conn.execute(
        "SELECT instructor_id, decision, reason FROM approvals WHERE case_id = ? ORDER BY approval_id DESC LIMIT 1",
        (case["case_id"],),
    ).fetchone()
    if case["state"] == "COMPLETED":
        kind = conn.execute("SELECT kind FROM enrollments WHERE idempotency_key = ?", (case["case_id"],)).fetchone()
        detail = f"approved by {approval['instructor_id']}; {kind['kind'].lower()} enrollment" if approval and kind else "enrolled"
    elif case["state"] == "REJECTED":
        detail = f"rejected by {approval['instructor_id']}; reason: {approval['reason'] or 'none given'}" if approval else "rejected"
    elif case["state"] == "FAILED":
        last = conn.execute(
            "SELECT detail FROM audit_events WHERE case_id = ? AND to_state = 'FAILED' ORDER BY event_id DESC LIMIT 1",
            (case["case_id"],),
        ).fetchone()
        detail = f"not enrolled; {last['detail']}" if last and last["detail"] else "not enrolled"
        if case["flag"]:
            detail += "; flagged for review"
    else:  # CANCELLED
        detail = "cancelled before reaching the instructor"
    return f"{head} ({detail})."

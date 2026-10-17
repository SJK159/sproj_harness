"""Read-only queries used by the case-flow tests."""


def audit_path(db, case_id):
    """State transitions only (refusal rows record from == to and are skipped)."""
    return [(r["from_state"], r["to_state"]) for r in db.execute(
        "SELECT from_state, to_state FROM audit_events WHERE case_id = ? AND to_state IS NOT NULL"
        " AND (from_state IS NULL OR from_state <> to_state) ORDER BY event_id", (case_id,))]


def audit_actions(db, case_id):
    return [r["action"] for r in db.execute(
        "SELECT action FROM audit_events WHERE case_id = ? ORDER BY event_id", (case_id,))]


def notices(db, recipient_id):
    return [dict(r) for r in db.execute(
        "SELECT kind, message, case_id FROM notifications WHERE recipient_id = ? ORDER BY notification_id",
        (recipient_id,))]


def enrollment_count(db, case_id):
    return db.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key = ?", (case_id,)).fetchone()[0]


def thread(case_id):
    return {"configurable": {"thread_id": case_id}}

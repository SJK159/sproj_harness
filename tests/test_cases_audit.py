import sqlite3

import pytest

from harness.audit import write_event
from harness.cases import InvalidTransition, get_case, transition


def test_write_event_appends_a_full_row(awaiting):
    with awaiting:
        event_id = write_event(awaiting, "C-A1", "I1", "NOTE", "AWAITING_APPROVAL", "AWAITING_APPROVAL", {"k": "v"})
    row = awaiting.execute("SELECT * FROM audit_events WHERE event_id = ?", (event_id,)).fetchone()
    assert (row["case_id"], row["actor"], row["action"], row["detail"]) == ("C-A1", "I1", "NOTE", '{"k": "v"}')
    assert row["timestamp"]

@pytest.mark.parametrize("sql", ["UPDATE audit_events SET actor = 'x'", "DELETE FROM audit_events"])
def test_audit_log_is_append_only(awaiting, sql):
    with awaiting:
        write_event(awaiting, "C-A1", "I1", "NOTE")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        awaiting.execute(sql)

def test_every_transition_writes_one_audit_row(awaiting):
    with awaiting:
        transition(awaiting, "C-A1", "APPROVED", "I1", "APPROVE")
        transition(awaiting, "C-A1", "EXECUTING", "system", "EXECUTE")
        transition(awaiting, "C-A1", "COMPLETED", "system", "ENROLLED")
    rows = awaiting.execute(
        "SELECT from_state, to_state FROM audit_events WHERE case_id = 'C-A1' ORDER BY event_id").fetchall()
    assert [tuple(r) for r in rows] == [
        ("AWAITING_APPROVAL", "APPROVED"), ("APPROVED", "EXECUTING"), ("EXECUTING", "COMPLETED")]
    assert get_case(awaiting, "C-A1")["state"] == "COMPLETED"

def test_rejected_case_can_never_execute(awaiting):
    with awaiting:
        transition(awaiting, "C-A1", "REJECTED", "I1", "REJECT")
    with pytest.raises(InvalidTransition):
        with awaiting:
            transition(awaiting, "C-A1", "EXECUTING", "system", "EXECUTE")
    assert get_case(awaiting, "C-A1")["state"] == "REJECTED"
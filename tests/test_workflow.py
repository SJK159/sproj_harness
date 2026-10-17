"""Deterministic case workflow (no agent): A1/A2/A4/A5/A6/A7 cores and crash recovery."""

from datetime import UTC, datetime

import pytest
from case_helpers import audit_actions, audit_path, enrollment_count, notices

from harness import workflow as wf
from harness.approvals import decide, verify_and_consume
from harness.cases import get_case, transition
from harness.mock_zambeel import get_section

pytestmark = pytest.mark.usefixtures("secret")


def awaiting_case(db, case_id="FE-1", student="S1", course="CS412", section="S1"):
    wf.open_case(db, case_id, student, course, section)
    wf.record_confirmation(db, case_id, student, True)
    wf.submit(db, case_id, student)
    return case_id


def approval_token(db, case_id):
    return db.execute("SELECT token FROM approvals WHERE case_id = ? AND decision = 'APPROVE'", (case_id,)).fetchone()[0]


def test_open_case_waits_for_confirmation_and_is_idempotent(db):
    wf.open_case(db, "FE-1", "S1", "CS412", "S1")
    wf.open_case(db, "FE-1", "S1", "CS412", "S1")  # client retry: same case back, nothing new
    assert get_case(db, "FE-1")["state"] == "AWAITING_CONFIRMATION"
    assert audit_path(db, "FE-1") == [(None, "DRAFT"), ("DRAFT", "AWAITING_CONFIRMATION")]


def test_ineligible_request_creates_no_case(db):
    with pytest.raises(wf.NotEligible) as refused:
        wf.open_case(db, "FE-1", "S2", "CS412", "S1")
    assert "PREREQ_MISSING" in refused.value.eligibility.blocking
    assert db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0


def test_a7_duplicate_request_returns_the_open_case(db):
    wf.open_case(db, "FE-1", "S1", "CS412", "S1")
    with pytest.raises(wf.DuplicateCase) as dup:
        wf.open_case(db, "FE-2", "S1", "CS412", "S1")
    assert dup.value.existing_case_id == "FE-1"
    assert db.execute("SELECT COUNT(*) FROM cases WHERE case_id = 'FE-2'").fetchone()[0] == 0


def test_a6_declining_cancels_and_notifies_nobody(db):
    wf.open_case(db, "FE-1", "S1", "CS412", "S1")
    wf.record_confirmation(db, "FE-1", "S1", False)
    assert get_case(db, "FE-1")["state"] == "CANCELLED"
    assert audit_path(db, "FE-1")[-1] == ("AWAITING_CONFIRMATION", "CANCELLED")
    assert notices(db, "I1") == []


def test_submit_needs_confirmation_and_notifies_the_instructor_once(db):
    wf.open_case(db, "FE-1", "S1", "CS412", "S1")
    with pytest.raises(wf.WrongState):
        wf.submit(db, "FE-1", "S1")
    wf.record_confirmation(db, "FE-1", "S1", True)
    wf.submit(db, "FE-1", "S1")
    wf.submit(db, "FE-1", "S1")  # tool retried after resume: no second notice
    assert get_case(db, "FE-1")["state"] == "AWAITING_APPROVAL"
    assert [n["kind"] for n in notices(db, "I1")] == ["APPROVAL_REQUESTED"]


def test_execute_before_approval_is_refused_and_changes_nothing(db):
    awaiting_case(db)
    with pytest.raises(wf.WrongState):
        wf.execute(db, "FE-1", "S1")
    assert get_case(db, "FE-1")["state"] == "AWAITING_APPROVAL"
    assert enrollment_count(db, "FE-1") == 0
    assert "EXECUTE_REFUSED" in audit_actions(db, "FE-1")


def test_a1_approved_case_completes_once(db):
    awaiting_case(db)
    decide(db, "FE-1", "I1", "APPROVE")
    first = wf.execute(db, "FE-1", "S1")
    again = wf.execute(db, "FE-1", "S1")
    assert first["state"] == again["state"] == "COMPLETED"
    assert first["enrollment_id"] == again["enrollment_id"] and first["kind"] == "FORCE"
    assert enrollment_count(db, "FE-1") == 1
    assert get_section(db, "CS412-S1")["fe_used"] == 1
    assert [n["kind"] for n in notices(db, "S1")] == ["COMPLETED"]


def _expired(db):
    decide(db, "FE-1", "I1", "APPROVE", now=datetime(2026, 1, 1, tzinfo=UTC))


def _tampered(db):
    decide(db, "FE-1", "I1", "APPROVE")
    token = approval_token(db, "FE-1")
    head, payload, sig = token.split(".")
    db.execute("UPDATE approvals SET token = ? WHERE case_id = 'FE-1'",
               (f"{head}.{payload}.{'B' if sig[0] != 'B' else 'C'}{sig[1:]}",))
    db.commit()


def _other_case(db):
    awaiting_case(db, "FE-2", "S2", "CS360", "S1")
    decide(db, "FE-2", "I1", "APPROVE")
    decide(db, "FE-1", "I1", "APPROVE")
    db.execute("UPDATE approvals SET token = ? WHERE case_id = 'FE-1'", (approval_token(db, "FE-2"),))
    db.commit()


def _reused(db):
    decide(db, "FE-1", "I1", "APPROVE")
    verify_and_consume(db, approval_token(db, "FE-1"), "FE-1")  # used outside execute_enrollment


@pytest.mark.parametrize("break_token", [_expired, _tampered, _other_case, _reused],
                         ids=["expired", "tampered", "other-case", "reused"])
def test_a4_bad_token_fails_and_flags_the_case(db, break_token):
    awaiting_case(db)
    break_token(db)
    out = wf.execute(db, "FE-1", "S1")
    case = get_case(db, "FE-1")
    assert out["state"] == case["state"] == "FAILED"
    assert case["flag"]
    assert enrollment_count(db, "FE-1") == 0
    assert "TOKEN_REFUSED" in audit_actions(db, "FE-1")
    assert [n["kind"] for n in notices(db, "S1")] == ["FAILED"]


def test_a5_fe_cap_race_second_execution_fails(db):
    awaiting_case(db, "FE-A", "S1", "CS360", "S1")
    awaiting_case(db, "FE-B", "S2", "CS360", "S1")
    decide(db, "FE-A", "I1", "APPROVE")
    decide(db, "FE-B", "I1", "APPROVE")
    assert wf.execute(db, "FE-A", "S1")["state"] == "COMPLETED"
    second = wf.execute(db, "FE-B", "S2")
    assert second["state"] == "FAILED" and "force-enrollment slots" in second["reason"]
    assert get_section(db, "CS360-S1")["fe_used"] == 1
    assert [n["kind"] for n in notices(db, "S2")] == ["FAILED"]


def test_crash_after_consuming_the_token_still_completes_once(db):
    awaiting_case(db)
    decide(db, "FE-1", "I1", "APPROVE")
    verify_and_consume(db, approval_token(db, "FE-1"), "FE-1", actor="execute_enrollment",
                       on_consumed=lambda c: transition(c, "FE-1", "EXECUTING", "execute_enrollment", "EXECUTE"))
    assert get_case(db, "FE-1")["state"] == "EXECUTING"  # ...process dies here, before enroll()
    assert wf.execute(db, "FE-1", "S1")["state"] == "COMPLETED"
    assert enrollment_count(db, "FE-1") == 1


def test_a2_rejection_tells_the_student_who_and_why(db):
    awaiting_case(db, "FE-2", "S2", "CS360", "S1")
    decide(db, "FE-2", "I1", "REJECT", reason="Room at capacity")
    assert get_case(db, "FE-2")["state"] == "REJECTED"
    [notice] = notices(db, "S2")
    assert notice["kind"] == "REJECTED" and "I1" in notice["message"] and "Room at capacity" in notice["message"]
    with pytest.raises(wf.WrongState):
        wf.execute(db, "FE-2", "S2")

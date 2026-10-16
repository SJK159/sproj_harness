import pytest

from harness.mock_zambeel import (
    FeCapReached,
    IdempotencyConflict,
    enroll,
    get_section,
    get_student_profile,
)


def count(db, student_id, offering_id):
    return db.execute(
        "SELECT COUNT(*) FROM enrollments WHERE student_id = ? AND offering_id = ?",
        (student_id, offering_id),
    ).fetchone()[0]

def test_force_enroll_uses_an_fe_slot(db):
    r = enroll(db, "S1", "CS412-S1", idempotency_key="case-1")
    assert r.created and r.kind == "FORCE"
    assert get_section(db, "CS412-S1")["fe_used"] == 1

def test_same_key_twice_creates_one_enrollment(db):
    first = enroll(db, "S1", "CS412-S1", idempotency_key="case-1")
    second = enroll(db, "S1", "CS412-S1", idempotency_key="case-1")
    assert not second.created and second.enrollment_id == first.enrollment_id
    assert count(db, "S1", "CS412-S1") == 1
    assert get_section(db, "CS412-S1")["fe_used"] == 1

def test_same_key_for_a_different_request_is_rejected(db):
    enroll(db, "S1", "CS412-S1", idempotency_key="case-1")
    with pytest.raises(IdempotencyConflict):
        enroll(db, "S3", "CS412-S1", idempotency_key="case-1")
    assert count(db, "S3", "CS412-S1") == 0

def test_cap_is_rechecked_at_execution(db):  # deterministic core of scenario A5
    enroll(db, "S1", "CS360-S1", idempotency_key="case-a")
    with pytest.raises(FeCapReached):
        enroll(db, "S2", "CS360-S1", idempotency_key="case-b")
    assert count(db, "S2", "CS360-S1") == 0

def test_retry_after_cap_filled_returns_existing(db):
    first = enroll(db, "S1", "CS360-S1", idempotency_key="case-a")
    again = enroll(db, "S1", "CS360-S1", idempotency_key="case-a")
    assert again.enrollment_id == first.enrollment_id and not again.created

def test_open_seat_at_execution_enrolls_regular(db):
    r = enroll(db, "S1", "CS412-S2", idempotency_key="case-1")
    assert r.kind == "REGULAR"
    assert get_section(db, "CS412-S2")["fe_used"] == 0

def test_profile_reports_credits_and_standing(db):
    p = get_student_profile(db, "S1")
    assert (p["year"], p["cgpa"], p["credits"], p["on_probation"]) == (4, 3.4, 15, False)
    assert set(p["completed"]) == {"CS200", "CS310"}
    assert get_student_profile(db, "S6")["on_probation"] is True
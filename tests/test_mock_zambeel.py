import pytest
from harness.mock_zambeel import (
    IdempotencyConflict, UnknownStudent, check_clashes, check_prerequisites,
    check_seats, enroll, find_offering, get_student_profile,
)

def enrollment_count(db, student_id, offering_id):
    return db.execute(
        "SELECT COUNT(*) FROM enrollments WHERE student_id = ? AND offering_id = ?",
        (student_id, offering_id),
    ).fetchone()[0]

# --- done-when checks ---

def test_s1_passes_all_checks_for_cs412(db):
    off = find_offering(db, "CS412")
    results = [check_prerequisites(db, "S1", "CS412"), check_seats(db, off), check_clashes(db, "S1", off)]
    assert [r.check for r in results] == ["prerequisites", "seats", "clashes"]
    assert all(r.passed for r in results), [r.reason for r in results]

def test_s2_fails_prerequisites_for_cs412(db):
    r = check_prerequisites(db, "S2", "CS412")
    assert not r.passed
    assert r.details["missing"] == ["CS310"]

def test_cs360_has_no_seats(db):
    r = check_seats(db, find_offering(db, "CS360"))
    assert not r.passed
    assert r.details["available"] == 0
    assert r.details["capacity"] == r.details["enrolled"]

def test_s3_has_clash_with_cs412(db):
    r = check_clashes(db, "S3", find_offering(db, "CS412"))
    assert not r.passed
    assert {c["course_id"] for c in r.details["clashes"]} == {"CS370"}
    assert {c["day"] for c in r.details["clashes"]} == {"M", "W"}

def test_enroll_twice_with_same_key_creates_one_enrollment(db):
    off = find_offering(db, "CS412")
    first = enroll(db, "S1", off, idempotency_key="case-123")
    second = enroll(db, "S1", off, idempotency_key="case-123")
    assert first.created and not second.created
    assert first.enrollment_id == second.enrollment_id
    assert enrollment_count(db, "S1", off) == 1

# --- edges the later milestones rely on ---

def test_same_key_for_a_different_request_is_rejected(db):
    off = find_offering(db, "CS412")
    enroll(db, "S1", off, idempotency_key="case-123")
    with pytest.raises(IdempotencyConflict):
        enroll(db, "S3", off, idempotency_key="case-123")
    assert enrollment_count(db, "S3", off) == 0

def test_unknown_student_is_not_a_pass(db):
    with pytest.raises(UnknownStudent):
        check_prerequisites(db, "S999", "CS412")

def test_enrolling_takes_a_seat(db):
    off = find_offering(db, "CS412")
    before = check_seats(db, off).details["available"]
    enroll(db, "S1", off, idempotency_key="case-1")
    assert check_seats(db, off).details["available"] == before - 1

def test_profile_shows_only_that_student(db):
    p = get_student_profile(db, "S1")
    assert p["student_id"] == "S1"
    assert set(p["completed"]) == {"CS200", "CS310"}
    assert [e["course_id"] for e in p["enrollments"]] == ["MATH120"]
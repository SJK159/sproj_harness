"""The O-02 / O-03 checks themselves must catch what they claim to catch."""

from harness.integrity import audit_gaps, unauthorized_writes


def test_seeded_database_is_clean(db):
    assert audit_gaps(db) == [] and unauthorized_writes(db) == []


def test_case_without_audit_rows_is_reported(db):
    db.execute("INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)"
               " VALUES ('FE-x', 'S1', 'CS412-S1', 'FORCE_ENROLLMENT', 'APPROVED', 'now', 'now')")
    db.commit()
    assert any("FE-x" in gap for gap in audit_gaps(db))


def test_enrollment_without_a_verified_approval_is_reported(db):
    db.execute("INSERT INTO enrollments (student_id, offering_id, status, kind, idempotency_key, created_at)"
               " VALUES ('S2', 'CS412-S1', 'ENROLLED', 'FORCE', 'FE-sneaky', 'now')")
    db.execute("INSERT INTO enrollments (student_id, offering_id, status, kind, created_at)"
               " VALUES ('S3', 'CS360-S1', 'ENROLLED', 'REGULAR', 'now')")
    db.commit()
    problems = unauthorized_writes(db)
    assert any("FE-sneaky" in p for p in problems) and any("S3" in p and "CS360-S1" in p for p in problems)

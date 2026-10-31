"""Academic operations used by the workflow: local by default, MCP inside the FE service.

The override is scoped to a call, never a process-wide monkeypatch. Both paths use
the same deterministic mock rules. SQLite remains shared for this local prototype.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from harness import mock_zambeel as local

_gateway = ContextVar("academic_gateway", default=None)


@contextmanager
def using_academic(gateway):
    token = _gateway.set(gateway)
    try:
        yield
    finally:
        _gateway.reset(token)


def get_section(conn, offering_id):
    gateway = _gateway.get()
    return gateway.get_section(offering_id) if gateway else local.get_section(conn, offering_id)


def get_student_profile(conn, student_id):
    gateway = _gateway.get()
    return gateway.get_student_profile(student_id) if gateway else local.get_student_profile(conn, student_id)


def check_fe_eligibility(conn, student_id, course_id, section):
    gateway = _gateway.get()
    return gateway.check_fe_eligibility(student_id, course_id, section) if gateway else local.check_fe_eligibility(conn, student_id, course_id, section)


def enroll(conn, student_id, offering_id, idempotency_key):
    gateway = _gateway.get()
    return gateway.enroll(student_id, offering_id, idempotency_key) if gateway else local.enroll(conn, student_id, offering_id, idempotency_key)


def enrollment_result(conn, case_id):
    gateway = _gateway.get()
    if gateway:
        return gateway.enrollment_result(case_id)
    row = conn.execute("SELECT enrollment_id, kind FROM enrollments WHERE idempotency_key = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def course_details(conn, course_id):
    gateway = _gateway.get()
    if gateway:
        return gateway.course_details(course_id)
    row = conn.execute("SELECT credits FROM courses WHERE course_id = ?", (course_id,)).fetchone()
    return {"credits": row[0], "prerequisites": [r[0] for r in conn.execute(
        "SELECT prereq_course_id FROM prerequisites WHERE course_id = ? ORDER BY prereq_course_id", (course_id,))]}

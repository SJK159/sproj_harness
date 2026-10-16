"""Mock Zambeel read checks and the one write, `enroll`.

Plain functions over a sqlite3 connection; no LLM, no access control. Callers
(agent tools from M3 on) decide whose data may be read.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from harness.mock_zambeel.seed_data import CURRENT_TERM


class ZambeelError(Exception):
    pass


class UnknownStudent(ZambeelError):
    pass


class UnknownCourse(ZambeelError):
    pass


class UnknownOffering(ZambeelError):
    pass


class IdempotencyConflict(ZambeelError):
    """The idempotency key was already used for a different enrollment request."""


class AlreadyEnrolled(ZambeelError):
    """The student is already enrolled in this offering under another key."""


@dataclass(frozen=True)
class CheckResult:
    check: str  # "prerequisites" | "seats" | "clashes"
    passed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnrollResult:
    enrollment_id: int
    created: bool  # False when an earlier call with the same key already enrolled


def _require_student(conn: sqlite3.Connection, student_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
    if row is None:
        raise UnknownStudent(f"No student record for {student_id!r}; eligibility cannot be determined.")
    return row


def _require_course(conn: sqlite3.Connection, course_id: str) -> None:
    if conn.execute("SELECT 1 FROM courses WHERE course_id = ?", (course_id,)).fetchone() is None:
        raise UnknownCourse(f"No course {course_id!r} in the catalogue.")


def _require_offering(conn: sqlite3.Connection, offering_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM offerings WHERE offering_id = ?", (offering_id,)).fetchone()
    if row is None:
        raise UnknownOffering(f"No offering {offering_id!r}.")
    return row


def get_student_profile(conn: sqlite3.Connection, student_id: str) -> dict[str, Any]:
    student = _require_student(conn, student_id)
    completed = [
        r["course_id"]
        for r in conn.execute(
            "SELECT course_id FROM transcript WHERE student_id = ? ORDER BY course_id", (student_id,)
        )
    ]
    enrollments = [
        {"offering_id": r["offering_id"], "course_id": r["course_id"]}
        for r in conn.execute(
            """SELECT e.offering_id, o.course_id FROM enrollments e
               JOIN offerings o ON o.offering_id = e.offering_id
               WHERE e.student_id = ? AND e.status = 'ENROLLED' AND o.term = ?
               ORDER BY o.course_id""",
            (student_id, CURRENT_TERM),
        )
    ]
    return {
        "student_id": student["student_id"],
        "name": student["name"],
        "program": student["program"],
        "standing": student["standing"],
        "completed": completed,
        "enrollments": enrollments,
    }


def find_offering(conn: sqlite3.Connection, course_id: str, term: str = CURRENT_TERM) -> str:
    _require_course(conn, course_id)
    row = conn.execute(
        "SELECT offering_id FROM offerings WHERE course_id = ? AND term = ? ORDER BY section LIMIT 1",
        (course_id, term),
    ).fetchone()
    if row is None:
        raise UnknownOffering(f"{course_id} is not offered in {term}.")
    return row["offering_id"]


def check_prerequisites(conn: sqlite3.Connection, student_id: str, course_id: str) -> CheckResult:
    _require_student(conn, student_id)
    _require_course(conn, course_id)
    missing = [
        r["prereq_course_id"]
        for r in conn.execute(
            """SELECT p.prereq_course_id FROM prerequisites p
               WHERE p.course_id = ? AND p.prereq_course_id NOT IN
                   (SELECT course_id FROM transcript WHERE student_id = ?)
               ORDER BY p.prereq_course_id""",
            (course_id, student_id),
        )
    ]
    if missing:
        reason = f"{student_id} has not completed {', '.join(missing)}, required for {course_id}."
    else:
        reason = f"{student_id} has completed all prerequisites for {course_id}."
    return CheckResult("prerequisites", not missing, reason, {"course_id": course_id, "missing": missing})


def check_seats(conn: sqlite3.Connection, offering_id: str) -> CheckResult:
    offering = _require_offering(conn, offering_id)
    enrolled = conn.execute(
        "SELECT COUNT(*) FROM enrollments WHERE offering_id = ? AND status = 'ENROLLED'", (offering_id,)
    ).fetchone()[0]
    capacity = offering["capacity"]
    available = max(capacity - enrolled, 0)
    reason = f"{offering_id}: {available} of {capacity} seats available."
    return CheckResult(
        "seats",
        available > 0,
        reason,
        {"offering_id": offering_id, "capacity": capacity, "enrolled": enrolled, "available": available},
    )


def check_clashes(conn: sqlite3.Connection, student_id: str, offering_id: str) -> CheckResult:
    _require_student(conn, student_id)
    offering = _require_offering(conn, offering_id)
    clashes = [
        {"course_id": r["course_id"], "offering_id": r["offering_id"], "day": r["day"], "start": r["start"], "end": r["end"]}
        for r in conn.execute(
            """SELECT o.course_id, o.offering_id, theirs.day, theirs.start, theirs."end"
               FROM offering_slots mine
               JOIN offering_slots theirs
                 ON theirs.day = mine.day AND theirs.start < mine."end" AND mine.start < theirs."end"
               JOIN enrollments e ON e.offering_id = theirs.offering_id
               JOIN offerings o ON o.offering_id = theirs.offering_id
               WHERE mine.offering_id = ? AND e.student_id = ? AND e.status = 'ENROLLED'
                 AND o.term = ? AND theirs.offering_id != mine.offering_id
               ORDER BY o.course_id, theirs.day""",
            (offering_id, student_id, offering["term"]),
        )
    ]
    if clashes:
        slots = "; ".join(f"{c['course_id']} {c['day']} {c['start']}-{c['end']}" for c in clashes)
        reason = f"{offering_id} clashes with {student_id}'s timetable: {slots}."
    else:
        reason = f"{offering_id} does not clash with {student_id}'s timetable."
    return CheckResult("clashes", not clashes, reason, {"offering_id": offering_id, "clashes": clashes})


def enroll(conn: sqlite3.Connection, student_id: str, offering_id: str, idempotency_key: str) -> EnrollResult:
    """Enroll a student. Idempotent on `idempotency_key` (the case_id from M5 on).

    Does not re-check eligibility or seats: those run before approval, and the
    write is gated by the approval token in `execute_enrollment` (M5).
    The UNIQUE constraint on the key, not a read-then-insert, decides the outcome,
    so two concurrent retries cannot both insert.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key is required")
    _require_student(conn, student_id)
    _require_offering(conn, offering_id)
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO enrollments (student_id, offering_id, status, idempotency_key, created_at)
                   VALUES (?, ?, 'ENROLLED', ?, ?)""",
                (student_id, offering_id, idempotency_key, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            return EnrollResult(cur.lastrowid, created=True)
    except sqlite3.IntegrityError:
        existing = conn.execute(
            "SELECT enrollment_id, student_id, offering_id FROM enrollments WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is None:
            raise AlreadyEnrolled(f"{student_id} is already enrolled in {offering_id}.") from None
        if (existing["student_id"], existing["offering_id"]) != (student_id, offering_id):
            raise IdempotencyConflict(
                f"Key {idempotency_key!r} was already used for {existing['student_id']} in {existing['offering_id']}."
            ) from None
        return EnrollResult(existing["enrollment_id"], created=False)

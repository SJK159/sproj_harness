"""Mock Zambeel reads, force-enrollment eligibility, and the one write, `enroll`.

Plain functions over a sqlite3 connection; no LLM, no access control. Callers
(agent tools from M3 on) decide whose data may be read.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from harness.mock_zambeel.policy import (
    ADVISORY_CODES,
    BLOCKING_CODES,
    CREDIT_CAP,
    PROBATION_CGPA,
)
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


class FeCapReached(ZambeelError):
    """The section is full and all its force-enrollment slots are used."""


@dataclass(frozen=True)
class CheckResult:
    check: str  # "prerequisites" | "seats" | "clashes"
    passed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Eligibility:
    student_id: str
    course_id: str
    section: str
    offering_id: str | None  # None when the section is not offered this term
    blocking: tuple[str, ...]  # failures, in policy.BLOCKING_CODES order
    advisory: tuple[str, ...]  # SEATS_AVAILABLE / OTHER_SECTION_OPEN; not failures
    reasons: dict[str, str]  # code -> human-readable reason, for every code above
    suggestions: tuple[dict[str, Any], ...] = ()  # open, non-clashing sections of the same course

    @property
    def eligible(self) -> bool:
        return not self.blocking

    @property
    def fe_needed(self) -> bool:
        """False when the requested section has seats: register normally instead."""
        return "SEATS_AVAILABLE" not in self.advisory

    @property
    def can_submit(self) -> bool:
        """The only condition under which a force-enrollment case may be created."""
        return self.eligible and self.fe_needed


@dataclass(frozen=True)
class EnrollResult:
    enrollment_id: int
    created: bool  # False when an earlier call with the same key already enrolled
    kind: str  # "FORCE" (over capacity) or "REGULAR" (a seat had opened by execution time)


# --- lookups -------------------------------------------------------------------


def _require_student(conn: sqlite3.Connection, student_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
    if row is None:
        raise UnknownStudent(f"No student record for {student_id!r}; eligibility cannot be determined.")
    return row


def _require_course(conn: sqlite3.Connection, course_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM courses WHERE course_id = ?", (course_id,)).fetchone()
    if row is None:
        raise UnknownCourse(f"No course {course_id!r} in the catalogue.")
    return row


def _find_offering(conn: sqlite3.Connection, course_id: str, section: str, term: str) -> str | None:
    row = conn.execute(
        "SELECT offering_id FROM offerings WHERE course_id = ? AND section = ? AND term = ?",
        (course_id, section, term),
    ).fetchone()
    return row["offering_id"] if row else None


def get_section(conn: sqlite3.Connection, offering_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM offerings WHERE offering_id = ?", (offering_id,)).fetchone()
    if row is None:
        raise UnknownOffering(f"No offering {offering_id!r}.")
    enrolled, fe_used = conn.execute(
        """SELECT COUNT(*), COALESCE(SUM(kind = 'FORCE'), 0) FROM enrollments
           WHERE offering_id = ? AND status = 'ENROLLED'""",
        (offering_id,),
    ).fetchone()
    return {
        "offering_id": offering_id,
        "course_id": row["course_id"],
        "section": row["section"],
        "term": row["term"],
        "instructor_id": row["instructor_id"],
        "capacity": row["capacity"],
        "enrolled": enrolled,
        "available": max(row["capacity"] - enrolled, 0),
        "fe_allowed": bool(row["fe_allowed"]),
        "fe_cap": row["fe_cap"],
        "fe_used": fe_used,
        "min_year": row["min_year"],
        "min_cgpa": row["min_cgpa"],
    }


def _current_enrollments(conn: sqlite3.Connection, student_id: str, term: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT e.offering_id, o.course_id, c.credits FROM enrollments e
           JOIN offerings o ON o.offering_id = e.offering_id
           JOIN courses c ON c.course_id = o.course_id
           WHERE e.student_id = ? AND e.status = 'ENROLLED' AND o.term = ?
           ORDER BY o.course_id""",
        (student_id, term),
    ).fetchall()


def _clashes(conn: sqlite3.Connection, student_id: str, offering_id: str) -> list[dict[str, str]]:
    """Slots of the student's current enrollments that overlap the offering.

    Enrollments in the same course are ignored (that case is ALREADY_ENROLLED, not CLASH).
    """
    return [
        dict(r)
        for r in conn.execute(
            """SELECT o.course_id, o.offering_id, theirs.day, theirs.start, theirs."end" AS "end"
               FROM offerings target
               JOIN offering_slots mine ON mine.offering_id = target.offering_id
               JOIN offering_slots theirs
                 ON theirs.day = mine.day AND theirs.start < mine."end" AND mine.start < theirs."end"
               JOIN enrollments e ON e.offering_id = theirs.offering_id
               JOIN offerings o ON o.offering_id = theirs.offering_id
               WHERE target.offering_id = ? AND e.student_id = ? AND e.status = 'ENROLLED'
                 AND o.term = target.term AND o.course_id != target.course_id
               ORDER BY o.course_id, theirs.day""",
            (offering_id, student_id),
        )
    ]


def _slot_text(conn: sqlite3.Connection, offering_id: str) -> str:
    rows = conn.execute(
        'SELECT day, start, "end" FROM offering_slots WHERE offering_id = ? ORDER BY start, day', (offering_id,)
    ).fetchall()
    days = "".join(sorted({r["day"] for r in rows}, key="MTWRF".index))  # weekday order: "TR", not "RT"
    return f"{days} {rows[0]['start']}-{rows[0]['end']}" if rows else "TBA"


# --- reads ---------------------------------------------------------------------


def get_student_profile(conn: sqlite3.Connection, student_id: str) -> dict[str, Any]:
    student = _require_student(conn, student_id)
    completed = [
        r["course_id"]
        for r in conn.execute("SELECT course_id FROM transcript WHERE student_id = ? ORDER BY course_id", (student_id,))
    ]
    enrollments = _current_enrollments(conn, student_id, CURRENT_TERM)
    return {
        "student_id": student["student_id"],
        "name": student["name"],
        "program": student["program"],
        "year": student["year"],
        "cgpa": student["cgpa"],
        "on_probation": student["cgpa"] < PROBATION_CGPA,
        "completed": completed,
        "enrollments": [{"offering_id": r["offering_id"], "course_id": r["course_id"]} for r in enrollments],
        "credits": sum(r["credits"] for r in enrollments),
    }


def check_prerequisites(conn: sqlite3.Connection, student_id: str, course_id: str) -> CheckResult:
    """Completed prerequisites only; one being taken this term is reported as in progress."""
    _require_student(conn, student_id)
    _require_course(conn, course_id)
    required = [r[0] for r in conn.execute(
        "SELECT prereq_course_id FROM prerequisites WHERE course_id = ? ORDER BY prereq_course_id", (course_id,)
    )]
    completed = {r[0] for r in conn.execute("SELECT course_id FROM transcript WHERE student_id = ?", (student_id,))}
    current = {r["course_id"] for r in _current_enrollments(conn, student_id, CURRENT_TERM)}
    in_progress = [c for c in required if c not in completed and c in current]
    missing = [c for c in required if c not in completed and c not in current]
    if missing or in_progress:
        parts = []
        if missing:
            parts.append(f"has not taken {', '.join(missing)}")
        if in_progress:
            parts.append(f"is still taking {', '.join(in_progress)} (in progress does not count)")
        reason = f"{student_id} {' and '.join(parts)}, required for {course_id}."
    else:
        reason = f"{student_id} has completed all prerequisites for {course_id}."
    return CheckResult(
        "prerequisites", not (missing or in_progress), reason,
        {"course_id": course_id, "missing": missing, "in_progress": in_progress},
    )


def check_seats(conn: sqlite3.Connection, offering_id: str) -> CheckResult:
    s = get_section(conn, offering_id)
    reason = (
        f"{offering_id}: {s['available']} of {s['capacity']} seats available; "
        f"force enrollment {'accepted' if s['fe_allowed'] else 'not accepted'}, "
        f"{s['fe_used']} of {s['fe_cap']} FE slots used."
    )
    return CheckResult("seats", s["available"] > 0, reason, s)


def check_clashes(conn: sqlite3.Connection, student_id: str, offering_id: str) -> CheckResult:
    _require_student(conn, student_id)
    get_section(conn, offering_id)
    clashes = _clashes(conn, student_id, offering_id)
    if clashes:
        slots = "; ".join(f"{c['course_id']} {c['day']} {c['start']}-{c['end']}" for c in clashes)
        reason = f"{offering_id} clashes with {student_id}'s timetable: {slots}."
    else:
        reason = f"{offering_id} does not clash with {student_id}'s timetable."
    return CheckResult("clashes", not clashes, reason, {"offering_id": offering_id, "clashes": clashes})


def check_fe_eligibility(
    conn: sqlite3.Connection, student_id: str, course_id: str, section: str, term: str = CURRENT_TERM
) -> Eligibility:
    """Every force-enrollment rule at once; reports all failing codes, not just the first."""
    student = _require_student(conn, student_id)
    course = _require_course(conn, course_id)
    offering_id = _find_offering(conn, course_id, section, term)
    found: dict[str, str] = {}

    prereqs = check_prerequisites(conn, student_id, course_id)
    if prereqs.details["missing"]:
        found["PREREQ_MISSING"] = f"Missing prerequisite(s) {', '.join(prereqs.details['missing'])} for {course_id}."
    if prereqs.details["in_progress"]:
        found["PREREQ_IN_PROGRESS"] = (
            f"Prerequisite(s) {', '.join(prereqs.details['in_progress'])} still in progress; "
            f"prerequisites must be completed."
        )
    if student["cgpa"] < PROBATION_CGPA:
        found["PROBATION"] = (
            f"CGPA {student['cgpa']:.2f} is below {PROBATION_CGPA:.1f}: students on probation cannot request FE."
        )
    current = _current_enrollments(conn, student_id, term)
    if any(r["course_id"] == course_id for r in current):
        found["ALREADY_ENROLLED"] = f"{student_id} is already enrolled in a section of {course_id} this term."

    sec = None
    if offering_id is None:
        found["NOT_OFFERED"] = f"{course_id} section {section} is not offered in {term}."
    else:
        sec = get_section(conn, offering_id)
        clashes = _clashes(conn, student_id, offering_id)
        if clashes:
            slots = "; ".join(f"{c['course_id']} {c['day']} {c['start']}-{c['end']}" for c in clashes)
            found["CLASH"] = f"{offering_id} clashes with: {slots}."
        credits = sum(r["credits"] for r in current if r["course_id"] != course_id) + course["credits"]
        if credits > CREDIT_CAP:
            found["CREDIT_LIMIT"] = f"Would take {credits} credits; the cap is {CREDIT_CAP}."
        if sec["min_year"] is not None and student["year"] < sec["min_year"]:
            found["YEAR_RESTRICTION"] = f"{offering_id} is restricted to year {sec['min_year']}+; student is year {student['year']}."
        if sec["min_cgpa"] is not None and student["cgpa"] < sec["min_cgpa"]:
            found["CGPA_BELOW_MIN"] = f"{offering_id} requires CGPA {sec['min_cgpa']:.1f}; student has {student['cgpa']:.2f}."
        if sec["available"] > 0:
            found["SEATS_AVAILABLE"] = f"{offering_id} has {sec['available']} open seat(s): register normally, no FE needed."
        elif not sec["fe_allowed"]:
            found["FE_NOT_ACCEPTED"] = f"The instructor of {offering_id} does not accept force enrollment."
        elif sec["fe_used"] >= sec["fe_cap"]:
            found["FE_CAP_REACHED"] = f"All {sec['fe_cap']} force-enrollment slots of {offering_id} are used."

    suggestions: list[dict[str, Any]] = []
    if (sec is None or sec["available"] == 0) and "ALREADY_ENROLLED" not in found:
        for (other_id,) in conn.execute(
            "SELECT offering_id FROM offerings WHERE course_id = ? AND term = ? AND offering_id IS NOT ? ORDER BY section",
            (course_id, term, offering_id),
        ).fetchall():
            other = get_section(conn, other_id)
            if other["available"] > 0 and not _clashes(conn, student_id, other_id):
                suggestions.append({
                    "offering_id": other_id, "section": other["section"],
                    "available": other["available"], "time": _slot_text(conn, other_id),
                })
        if suggestions:
            found["OTHER_SECTION_OPEN"] = "Open section(s) that fit the timetable: " + ", ".join(
                f"{s['offering_id']} ({s['time']}, {s['available']} seats)" for s in suggestions
            )

    return Eligibility(
        student_id=student_id,
        course_id=course_id,
        section=section,
        offering_id=offering_id,
        blocking=tuple(c for c in BLOCKING_CODES if c in found),
        advisory=tuple(c for c in ADVISORY_CODES if c in found),
        reasons=found,
        suggestions=tuple(suggestions),
    )


# --- the one write -------------------------------------------------------------


def enroll(conn: sqlite3.Connection, student_id: str, offering_id: str, idempotency_key: str) -> EnrollResult:
    """Execute an approved force enrollment. Idempotent on `idempotency_key` (the case_id from M5 on).

    Order matters:
    1. An existing row for the key is returned as is, even if the cap has filled since.
    2. The FE cap is re-checked now, not at approval: an approved case can still fail (FeCapReached).
       If a seat opened after approval, the student is enrolled REGULAR and no FE slot is used.
    `BEGIN IMMEDIATE` takes the write lock before reading counts, so two executions cannot
    both take the last FE slot. Eligibility is not re-checked here; the approval token (M5) gates the call.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key is required")
    _require_student(conn, student_id)
    get_section(conn, offering_id)
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT enrollment_id, student_id, offering_id, kind FROM enrollments WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            if (existing["student_id"], existing["offering_id"]) != (student_id, offering_id):
                raise IdempotencyConflict(
                    f"Key {idempotency_key!r} was already used for {existing['student_id']} in {existing['offering_id']}."
                )
            conn.commit()
            return EnrollResult(existing["enrollment_id"], created=False, kind=existing["kind"])

        sec = get_section(conn, offering_id)
        if sec["available"] > 0:
            kind = "REGULAR"
        elif sec["fe_used"] < sec["fe_cap"]:
            kind = "FORCE"
        else:
            raise FeCapReached(
                f"{offering_id} is full and all {sec['fe_cap']} force-enrollment slots are used."
            )
        try:
            cur = conn.execute(
                """INSERT INTO enrollments (student_id, offering_id, status, kind, idempotency_key, created_at)
                   VALUES (?, ?, 'ENROLLED', ?, ?, ?)""",
                (student_id, offering_id, kind, idempotency_key, datetime.now(UTC).isoformat(timespec="seconds")),
            )
        except sqlite3.IntegrityError:
            raise AlreadyEnrolled(f"{student_id} is already enrolled in {offering_id}.") from None
        conn.commit()
        return EnrollResult(cur.lastrowid, created=True, kind=kind)
    except BaseException:
        conn.rollback()
        raise

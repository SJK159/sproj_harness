"""Fixed synthetic dataset. IDs are stable; tests and CLAUDE.md rely on them.

- S1 eligible for CS412 (prereqs met, seats free, no clash).
- S2 missing the prerequisite CS310 for CS412.
- CS360 is full (capacity 2, filler students S90 and S91 enrolled).
- S3 enrolled in CS370, which clashes with CS412 on M/W.
- Instructor I1 owns CS412 and CS360.
"""

import sqlite3

CURRENT_TERM = "2027SP"
_SEED_TIME = "2026-10-01T00:00:00+00:00"

STUDENTS = [
    ("S1", "Student One", "BS Computer Science", "GOOD"),
    ("S2", "Student Two", "BS Computer Science", "GOOD"),
    ("S3", "Student Three", "BS Computer Science", "GOOD"),
    ("S90", "Filler Ninety", "BS Computer Science", "GOOD"),
    ("S91", "Filler Ninety-One", "BS Computer Science", "GOOD"),
]

INSTRUCTORS = [
    ("I1", "Instructor One"),
    ("I2", "Instructor Two"),
]

COURSES = [
    ("CS200", "Data Structures", 4, "CS"),
    ("CS310", "Algorithms", 3, "CS"),
    ("CS360", "Software Engineering", 3, "CS"),
    ("CS370", "Operating Systems", 3, "CS"),
    ("CS412", "Machine Learning", 3, "CS"),
    ("MATH120", "Linear Algebra", 3, "MATH"),
]

PREREQUISITES = [
    ("CS412", "CS200"),
    ("CS412", "CS310"),
    ("CS360", "CS200"),
    ("CS370", "CS200"),
]

TRANSCRIPT = [
    ("S1", "CS200", "2026FA", "A-"),
    ("S1", "CS310", "2026FA", "B+"),
    ("S2", "CS200", "2026FA", "B"),
    ("S3", "CS200", "2026FA", "A"),
    ("S3", "CS310", "2026FA", "B"),
    ("S90", "CS200", "2026FA", "B"),
    ("S91", "CS200", "2026FA", "B"),
]

# (offering_id, course_id, section, capacity, instructor_id, [(day, start, end), ...])
OFFERINGS = [
    ("CS412-S1", "CS412", "S1", 30, "I1", [("M", "10:30", "11:45"), ("W", "10:30", "11:45")]),
    ("CS360-S1", "CS360", "S1", 2, "I1", [("T", "14:00", "15:15"), ("R", "14:00", "15:15")]),
    ("CS370-S1", "CS370", "S1", 40, "I2", [("M", "10:00", "11:15"), ("W", "10:00", "11:15")]),
    ("MATH120-S1", "MATH120", "S1", 40, "I2", [("T", "11:00", "12:15"), ("R", "11:00", "12:15")]),
]

# Current-term enrollments made outside the harness (no idempotency key).
ENROLLMENTS = [
    ("S1", "MATH120-S1"),
    ("S3", "CS370-S1"),
    ("S90", "CS360-S1"),
    ("S91", "CS360-S1"),
]


def seed(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executemany("INSERT INTO students VALUES (?, ?, ?, ?)", STUDENTS)
        conn.executemany("INSERT INTO instructors VALUES (?, ?)", INSTRUCTORS)
        conn.executemany("INSERT INTO courses VALUES (?, ?, ?, ?)", COURSES)
        conn.executemany("INSERT INTO prerequisites VALUES (?, ?)", PREREQUISITES)
        conn.executemany("INSERT INTO transcript VALUES (?, ?, ?, ?)", TRANSCRIPT)
        for offering_id, course_id, section, capacity, instructor_id, slots in OFFERINGS:
            conn.execute(
                "INSERT INTO offerings VALUES (?, ?, ?, ?, ?, ?)",
                (offering_id, course_id, CURRENT_TERM, section, capacity, instructor_id),
            )
            conn.executemany(
                'INSERT INTO offering_slots (offering_id, day, start, "end") VALUES (?, ?, ?, ?)',
                [(offering_id, *slot) for slot in slots],
            )
        conn.executemany(
            "INSERT INTO enrollments (student_id, offering_id, status, created_at) VALUES (?, ?, 'ENROLLED', ?)",
            [(s, o, _SEED_TIME) for s, o in ENROLLMENTS],
        )

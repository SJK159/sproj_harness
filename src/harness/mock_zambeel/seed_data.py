"""Fixed synthetic dataset for force-enrollment testing. IDs are stable; tests and
docs/test-scenarios.md rely on them.

Students S1-S9 each exercise one eligibility rule (see docs/test-scenarios.md, E01-E14).
S90-S93 are filler students that make sections full and hold CS471's used FE slots.
Seeded enrollments bypass the eligibility checks on purpose.
"""

import sqlite3

CURRENT_TERM = "2026FA"
PREVIOUS_TERM = "2026SP"
_SEED_TIME = "2026-08-15T00:00:00+00:00"

# (student_id, name, program, year, cgpa)
STUDENTS = [
    ("S1", "Student One", "BS Computer Science", 4, 3.4),
    ("S2", "Student Two", "BS Computer Science", 3, 3.0),
    ("S3", "Student Three", "BS Computer Science", 3, 3.1),
    ("S4", "Student Four", "BS Computer Science", 3, 3.2),
    ("S5", "Student Five", "BS Computer Science", 4, 3.3),
    ("S6", "Student Six", "BS Computer Science", 3, 1.9),
    ("S7", "Student Seven", "BS Computer Science", 2, 3.2),
    ("S8", "Student Eight", "BS Computer Science", 4, 3.0),
    ("S9", "Student Nine", "BS Computer Science", 4, 2.8),
    ("S90", "Filler Ninety", "BS Computer Science", 3, 3.0),
    ("S91", "Filler Ninety-One", "BS Computer Science", 3, 3.0),
    ("S92", "Filler Ninety-Two", "BS Computer Science", 4, 3.0),
    ("S93", "Filler Ninety-Three", "BS Computer Science", 4, 3.5),
]

# One line per demo student for the frontend's switcher (the scenario each one exercises; docs/test-scenarios.md).
# The fillers S90-S93 only fill sections and are not listed.
SCENARIO_HINTS = {
    "S1": "Happy path: CS412-S1 is full and open to force enrollment",
    "S2": "Missing the CS310 prerequisite",
    "S3": "Timetable clash",
    "S4": "Prerequisite still in progress",
    "S5": "Already at the 20-credit cap",
    "S6": "On probation (CGPA below 2.0)",
    "S7": "Year restriction (CS381)",
    "S8": "Already enrolled",
    "S9": "CGPA below CS582's minimum",
}

INSTRUCTORS = [
    ("I1", "Instructor One"),
    ("I2", "Instructor Two"),
    ("I3", "Instructor Three"),
    ("I4", "Instructor Four"),
]

# (course_id, title, credits, department)
COURSES = [
    ("CS200", "Data Structures", 3, "CS"),
    ("CS300", "Advanced Programming", 3, "CS"),
    ("CS310", "Algorithms", 3, "CS"),
    ("CS360", "Software Engineering", 3, "CS"),
    ("CS370", "Operating Systems", 3, "CS"),
    ("CS381", "Senior Design Studio", 3, "CS"),
    ("CS412", "Machine Learning", 3, "CS"),
    ("CS471", "Computer Networks", 3, "CS"),
    ("CS582", "Advanced Machine Learning", 3, "CS"),
    ("CS999", "Special Topics (not offered)", 3, "CS"),
    ("MATH120", "Linear Algebra", 3, "MATH"),
    ("HUM101", "Writing and Communication", 3, "HUM"),
    ("SS101", "Introduction to Sociology", 3, "SS"),
    ("ECON100", "Principles of Economics", 3, "ECON"),
    ("PHIL101", "Introduction to Philosophy", 3, "PHIL"),
    ("BIO100", "Biology for Engineers", 3, "BIO"),
    ("LIT200", "Short Fiction Seminar", 2, "HUM"),
]

PREREQUISITES = [
    ("CS300", "CS200"),
    ("CS310", "CS200"),
    ("CS360", "CS200"),
    ("CS370", "CS200"),
    ("CS381", "CS200"),
    ("CS412", "CS310"),
    ("CS471", "CS310"),
    ("CS582", "CS310"),
]

TRANSCRIPT = (
    [(s, "CS200", PREVIOUS_TERM, "B+") for s in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9")]
    + [(s, "CS310", PREVIOUS_TERM, "B") for s in ("S1", "S3", "S5", "S6", "S8", "S9")]
)

MW, TR, F = ("M", "W"), ("T", "R"), ("F",)

# (offering_id, course_id, section, capacity, instructor_id, fe_allowed, fe_cap, min_year, min_cgpa, days, start, end)
OFFERINGS = [
    ("CS412-S1", "CS412", "S1", 2, "I1", 1, 3, None, None, MW, "11:00", "12:15"),
    ("CS412-S2", "CS412", "S2", 5, "I1", 0, 0, None, None, TR, "14:00", "15:15"),
    ("CS360-S1", "CS360", "S1", 1, "I1", 1, 1, None, None, TR, "09:30", "10:45"),
    ("CS300-S1", "CS300", "S1", 30, "I2", 0, 0, None, None, MW, "08:00", "09:15"),
    ("CS370-S1", "CS370", "S1", 1, "I2", 0, 0, None, None, MW, "14:00", "15:15"),
    ("CS471-S1", "CS471", "S1", 1, "I2", 1, 2, None, None, MW, "15:30", "16:45"),
    ("CS381-S1", "CS381", "S1", 1, "I3", 1, 2, 4, None, TR, "11:00", "12:15"),
    ("MATH120-S1", "MATH120", "S1", 2, "I3", 1, 2, None, None, MW, "11:00", "12:15"),
    ("CS582-S1", "CS582", "S1", 1, "I3", 1, 2, None, 3.0, TR, "15:30", "16:45"),
    ("CS310-S1", "CS310", "S1", 40, "I4", 0, 0, None, None, F, "09:00", "11:30"),
    ("HUM101-S1", "HUM101", "S1", 50, "I4", 0, 0, None, None, MW, "09:30", "10:45"),
    ("SS101-S1", "SS101", "S1", 50, "I4", 0, 0, None, None, TR, "08:00", "09:15"),
    ("ECON100-S1", "ECON100", "S1", 50, "I4", 0, 0, None, None, TR, "12:30", "13:45"),
    ("PHIL101-S1", "PHIL101", "S1", 50, "I4", 0, 0, None, None, MW, "17:00", "18:15"),
    ("BIO100-S1", "BIO100", "S1", 50, "I4", 0, 0, None, None, F, "14:00", "16:45"),
    ("LIT200-S1", "LIT200", "S1", 50, "I4", 0, 0, None, None, TR, "17:00", "18:15"),
]

_S1_LOAD = ["HUM101-S1", "SS101-S1", "ECON100-S1", "PHIL101-S1", "BIO100-S1"]  # 15 credits

# (student_id, offering_id, kind); made outside the harness, so no idempotency key.
ENROLLMENTS = (
    [("S1", o, "REGULAR") for o in _S1_LOAD]
    + [("S2", "HUM101-S1", "REGULAR")]
    + [("S3", "MATH120-S1", "REGULAR")]  # MW 11:00, clashes with CS412-S1
    + [("S4", "CS310-S1", "REGULAR")]  # CS310 in progress
    + [("S5", o, "REGULAR") for o in [*_S1_LOAD, "LIT200-S1", "CS300-S1"]]  # 20 credits
    + [("S6", "HUM101-S1", "REGULAR"), ("S7", "HUM101-S1", "REGULAR"), ("S9", "HUM101-S1", "REGULAR")]
    + [("S8", "CS412-S1", "REGULAR")]
    # fillers: make sections full; S91 and S92 hold CS471's two used FE slots
    + [("S90", "CS412-S1", "REGULAR"), ("S90", "CS370-S1", "REGULAR"), ("S90", "CS471-S1", "REGULAR")]
    + [("S91", "CS360-S1", "REGULAR"), ("S91", "CS471-S1", "FORCE")]
    + [("S92", "CS381-S1", "REGULAR"), ("S92", "CS471-S1", "FORCE")]
    + [("S93", "MATH120-S1", "REGULAR"), ("S93", "CS582-S1", "REGULAR")]
)


def seed(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executemany("INSERT INTO students VALUES (?, ?, ?, ?, ?)", STUDENTS)
        conn.executemany("INSERT INTO instructors VALUES (?, ?)", INSTRUCTORS)
        conn.executemany("INSERT INTO courses VALUES (?, ?, ?, ?)", COURSES)
        conn.executemany("INSERT INTO prerequisites VALUES (?, ?)", PREREQUISITES)
        conn.executemany("INSERT INTO transcript VALUES (?, ?, ?, ?)", TRANSCRIPT)
        for (offering_id, course_id, section, capacity, instructor_id,
             fe_allowed, fe_cap, min_year, min_cgpa, days, start, end) in OFFERINGS:
            conn.execute(
                """INSERT INTO offerings (offering_id, course_id, term, section, capacity, instructor_id,
                                          fe_allowed, fe_cap, min_year, min_cgpa)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (offering_id, course_id, CURRENT_TERM, section, capacity, instructor_id,
                 fe_allowed, fe_cap, min_year, min_cgpa),
            )
            conn.executemany(
                'INSERT INTO offering_slots (offering_id, day, start, "end") VALUES (?, ?, ?, ?)',
                [(offering_id, day, start, end) for day in days],
            )
        conn.executemany(
            """INSERT INTO enrollments (student_id, offering_id, status, kind, created_at)
               VALUES (?, ?, 'ENROLLED', ?, ?)""",
            [(s, o, kind, _SEED_TIME) for s, o, kind in ENROLLMENTS],
        )

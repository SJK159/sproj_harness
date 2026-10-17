"""Fixed synthetic dataset for force-enrollment testing. IDs are stable; tests and
docs/test-scenarios.md rely on them.

Students S1-S9 each exercise one eligibility rule (see docs/test-scenarios.md, E01-E14).
S90-S93 are filler students that make sections full and hold CS471's used FE slots.
The extended catalogue at the end (I5-I8, S94-S99, 29 more courses) only adds data for manual testing.
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


# ---------------------------------------------------------------------------------------------------------------------
# Extended catalogue (added 2026-10-18) for manual testing in the web UI and CLI: more courses, departments and rule
# combinations. It only adds: S1-S9, I1-I4 and the sections above are unchanged, and no S1-S9 student is enrolled in
# a new section, so every scenario in docs/test-scenarios.md gives the same result. New sections belong to I5-I8.
# Fillers S94-S99 fill the "full" sections and hold their used FE slots.

EXTRA_INSTRUCTORS = [
    ("I5", "Instructor Five"),   # CS electives
    ("I6", "Instructor Six"),    # EE, MATH, PHY, CHEM
    ("I7", "Instructor Seven"),  # ECON, MGMT, FIN
    ("I8", "Instructor Eight"),  # LAW, PSY, HIST, ART, URDU
]

EXTRA_FILLERS = [(f"S{n}", f"Filler {n}", "BS Computer Science", 3, 3.0) for n in range(94, 100)]

EXTRA_COURSES = [
    ("CS295", "Programming Lab", 1, "CS"),
    ("CS330", "Database Systems", 3, "CS"),
    ("CS340", "Computer Architecture", 3, "CS"),
    ("CS350", "Theory of Computation", 3, "CS"),
    ("CS391", "Human-Computer Interaction", 3, "CS"),
    ("CS432", "Computer Vision", 4, "CS"),
    ("CS435", "Natural Language Processing", 3, "CS"),
    ("CS450", "Distributed Systems", 3, "CS"),
    ("CS473", "Network Security", 3, "CS"),
    ("CS491", "Senior Project", 4, "CS"),
    ("EE210", "Circuits", 4, "EE"),
    ("EE240", "Digital Logic", 3, "EE"),
    ("EE320", "Signals and Systems", 3, "EE"),
    ("MATH101", "Calculus I", 3, "MATH"),
    ("MATH230", "Probability and Statistics", 3, "MATH"),
    ("MATH310", "Real Analysis", 3, "MATH"),
    ("PHY101", "Mechanics", 4, "PHY"),
    ("PHY201", "Electromagnetism", 4, "PHY"),
    ("CHEM101", "General Chemistry", 3, "CHEM"),
    ("ECON200", "Intermediate Microeconomics", 3, "ECON"),
    ("ECON310", "Econometrics", 3, "ECON"),
    ("MGMT101", "Introduction to Management", 3, "MGMT"),
    ("MGMT250", "Marketing", 3, "MGMT"),
    ("FIN201", "Corporate Finance", 3, "FIN"),
    ("LAW101", "Introduction to Law", 2, "LAW"),
    ("PSY101", "Introduction to Psychology", 3, "PSY"),
    ("HIST110", "World History", 3, "HIST"),
    ("ART150", "Studio Art", 1, "ART"),
    ("URDU100", "Urdu Literature", 3, "URDU"),
]

EXTRA_PREREQUISITES = [
    ("CS330", "CS200"), ("CS340", "CS200"), ("CS391", "CS200"), ("CS491", "CS200"),
    ("CS350", "CS310"), ("CS450", "CS310"), ("CS473", "CS310"),
    ("CS432", "CS412"),                         # chain: nobody has completed CS412 (S8 is taking it)
    ("CS435", "CS310"), ("CS435", "MATH120"),   # two prerequisites (S3 is taking MATH120)
    ("EE320", "EE210"), ("MATH310", "MATH120"), ("PHY201", "PHY101"),
    ("ECON200", "ECON100"),                     # S1 and S5 are taking ECON100: in progress
]

# Same columns as OFFERINGS, plus: full (fillers take every seat) and fe_used (fillers holding FE slots).
# What each row exercises is noted at the end; "S1 clash" means it overlaps a section S1 is enrolled in.
EXTRA_OFFERINGS = [
    ("CS295-S1", "CS295", "S1", 2, "I5", 1, 5, None, None, F, "14:00", "16:45", True, 0),   # 1 credit; S1/S5 clash
    ("CS330-S1", "CS330", "S1", 3, "I5", 1, 2, None, None, MW, "12:30", "13:45", True, 0),  # FE ok; S2 open
    ("CS330-S2", "CS330", "S2", 35, "I5", 0, 0, None, None, TR, "14:00", "15:15", False, 0),
    ("CS340-S1", "CS340", "S1", 2, "I5", 1, 1, None, None, MW, "14:00", "15:15", True, 1),  # FE cap reached
    ("CS340-S2", "CS340", "S2", 2, "I5", 1, 2, None, None, TR, "09:30", "10:45", True, 0),  # FE ok
    ("CS350-S1", "CS350", "S1", 2, "I5", 1, 2, None, None, TR, "11:00", "12:15", True, 0),  # needs CS310
    ("CS391-S1", "CS391", "S1", 3, "I5", 1, 3, None, None, MW, "09:30", "10:45", True, 0),  # clashes HUM101
    ("CS432-S1", "CS432", "S1", 1, "I5", 1, 2, None, None, MW, "15:30", "16:45", True, 0),  # 4 cr; needs CS412
    ("CS435-S1", "CS435", "S1", 2, "I5", 1, 2, None, 3.0, TR, "09:30", "10:45", True, 0),   # two prereqs; CGPA 3.0
    ("CS450-S1", "CS450", "S1", 2, "I5", 1, 2, 4, None, MW, "08:00", "09:15", True, 0),     # year 4+
    ("CS473-S1", "CS473", "S1", 2, "I5", 0, 0, None, None, TR, "17:00", "18:15", True, 0),  # full, no FE
    ("CS491-S1", "CS491", "S1", 1, "I5", 1, 1, 4, 3.3, F, "09:00", "11:30", True, 0),       # year 4 + CGPA 3.3
    ("EE210-S1", "EE210", "S1", 2, "I6", 1, 2, None, None, MW, "08:00", "09:15", True, 0),  # 3 sections
    ("EE210-S2", "EE210", "S2", 2, "I6", 1, 2, None, None, TR, "14:00", "15:15", True, 0),
    ("EE210-S3", "EE210", "S3", 30, "I6", 0, 0, None, None, MW, "15:30", "16:45", False, 0),
    ("EE240-S1", "EE240", "S1", 40, "I6", 0, 0, None, None, TR, "09:30", "10:45", False, 0),  # open
    ("EE320-S1", "EE320", "S1", 2, "I6", 1, 2, None, None, TR, "11:00", "12:15", True, 0),  # needs EE210
    ("MATH101-S1", "MATH101", "S1", 60, "I6", 0, 0, None, None, MW, "08:00", "09:15", False, 0),
    ("MATH101-S2", "MATH101", "S2", 60, "I6", 0, 0, None, None, TR, "11:00", "12:15", False, 0),
    ("MATH230-S1", "MATH230", "S1", 3, "I6", 1, 3, None, None, MW, "14:00", "15:15", True, 0),  # FE ok, no prereq
    ("MATH310-S1", "MATH310", "S1", 1, "I6", 1, 1, 3, None, TR, "08:00", "09:15", True, 0),   # S1 clash; MATH120
    ("PHY101-S1", "PHY101", "S1", 3, "I6", 0, 0, None, None, MW, "11:00", "12:15", True, 0),  # full, no FE
    ("PHY201-S1", "PHY201", "S1", 30, "I6", 0, 0, None, None, TR, "12:30", "13:45", False, 0),  # open; S1 clash
    ("CHEM101-S1", "CHEM101", "S1", 2, "I6", 1, 2, None, None, F, "09:00", "11:30", True, 0),  # S4 clash
    ("ECON200-S1", "ECON200", "S1", 2, "I7", 1, 2, None, None, MW, "12:30", "13:45", True, 0),  # ECON100 in prog.
    ("ECON310-S1", "ECON310", "S1", 2, "I7", 1, 2, None, 2.5, TR, "15:30", "16:45", True, 0),  # CGPA 2.5
    ("MGMT101-S1", "MGMT101", "S1", 80, "I7", 0, 0, None, None, MW, "15:30", "16:45", False, 0),  # open
    ("MGMT250-S1", "MGMT250", "S1", 3, "I7", 1, 3, None, None, TR, "11:00", "12:15", True, 3),  # FE cap reached
    ("FIN201-S1", "FIN201", "S1", 2, "I7", 1, 2, 3, None, MW, "11:00", "12:15", True, 0),   # year 3+; S3 clash
    ("LAW101-S1", "LAW101", "S1", 2, "I8", 1, 2, None, None, TR, "17:00", "18:15", True, 0),  # 2 cr; S5 clash
    ("PSY101-S1", "PSY101", "S1", 100, "I8", 0, 0, None, None, F, "09:00", "11:30", False, 0),  # open
    ("HIST110-S1", "HIST110", "S1", 3, "I8", 1, 4, None, None, MW, "17:00", "18:15", True, 0),  # S1 clash
    ("ART150-S1", "ART150", "S1", 2, "I8", 1, 2, 2, None, TR, "17:00", "18:15", True, 0),    # 1 cr; year 2+
    ("URDU100-S1", "URDU100", "S1", 40, "I8", 0, 0, None, None, TR, "15:30", "16:45", False, 0),  # open
]

_FILLER_IDS = [f[0] for f in EXTRA_FILLERS]
INSTRUCTORS += EXTRA_INSTRUCTORS
STUDENTS += EXTRA_FILLERS
COURSES += EXTRA_COURSES
PREREQUISITES += EXTRA_PREREQUISITES
OFFERINGS += [row[:12] for row in EXTRA_OFFERINGS]
ENROLLMENTS += [  # a full section: fillers take every seat; fe_used more fillers hold force enrollments
    (_FILLER_IDS[i], row[0], "REGULAR") for row in EXTRA_OFFERINGS if row[12] for i in range(row[3])
] + [
    (_FILLER_IDS[row[3] + i], row[0], "FORCE") for row in EXTRA_OFFERINGS for i in range(row[13])
]

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

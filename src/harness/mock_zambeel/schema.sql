-- Mock Zambeel + workflow tables. Synthetic data only.

-- Academic records ---------------------------------------------------------

CREATE TABLE students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    program    TEXT NOT NULL,
    year       INTEGER NOT NULL CHECK (year BETWEEN 1 AND 5),
    cgpa       REAL NOT NULL CHECK (cgpa BETWEEN 0 AND 4)
);

CREATE TABLE instructors (
    instructor_id TEXT PRIMARY KEY,
    name          TEXT NOT NULL
);

CREATE TABLE courses (
    course_id  TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    credits    INTEGER NOT NULL,
    department TEXT NOT NULL
);

CREATE TABLE prerequisites (
    course_id        TEXT NOT NULL REFERENCES courses(course_id),
    prereq_course_id TEXT NOT NULL REFERENCES courses(course_id),
    PRIMARY KEY (course_id, prereq_course_id)
);

-- Completed courses; the source for prerequisite checks.
CREATE TABLE transcript (
    student_id TEXT NOT NULL REFERENCES students(student_id),
    course_id  TEXT NOT NULL REFERENCES courses(course_id),
    term       TEXT NOT NULL,
    grade      TEXT NOT NULL,
    PRIMARY KEY (student_id, course_id)
);

CREATE TABLE offerings (
    offering_id   TEXT PRIMARY KEY,
    course_id     TEXT NOT NULL REFERENCES courses(course_id),
    term          TEXT NOT NULL,
    section       TEXT NOT NULL,
    capacity      INTEGER NOT NULL CHECK (capacity >= 0),
    instructor_id TEXT NOT NULL REFERENCES instructors(instructor_id),
    fe_allowed    INTEGER NOT NULL DEFAULT 0 CHECK (fe_allowed IN (0, 1)),  -- instructor accepts force enrollment
    fe_cap        INTEGER NOT NULL DEFAULT 0 CHECK (fe_cap >= 0),           -- max force enrollments over capacity
    min_year      INTEGER,                                                  -- NULL = no year restriction
    min_cgpa      REAL,                                                     -- NULL = no CGPA minimum
    UNIQUE (course_id, term, section)
);

-- Times are zero-padded 'HH:MM', so string comparison orders them correctly.
CREATE TABLE offering_slots (
    offering_id TEXT NOT NULL REFERENCES offerings(offering_id),
    day         TEXT NOT NULL CHECK (day IN ('M', 'T', 'W', 'R', 'F')),
    start       TEXT NOT NULL,
    "end"       TEXT NOT NULL,
    CHECK (start < "end")
);

-- Seats available = capacity - count(ENROLLED); fe_used = count(ENROLLED AND kind = 'FORCE').
-- Neither is stored.
CREATE TABLE enrollments (
    enrollment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT NOT NULL REFERENCES students(student_id),
    offering_id     TEXT NOT NULL REFERENCES offerings(offering_id),
    status          TEXT NOT NULL CHECK (status IN ('ENROLLED', 'DROPPED')),
    kind            TEXT NOT NULL CHECK (kind IN ('REGULAR', 'FORCE')),
    idempotency_key TEXT UNIQUE,
    created_at      TEXT NOT NULL,
    UNIQUE (student_id, offering_id)
);

-- Workflow and audit (used from M2 / M5) -------------------------------------

CREATE TABLE cases (
    case_id     TEXT PRIMARY KEY,
    student_id  TEXT NOT NULL REFERENCES students(student_id),
    offering_id TEXT REFERENCES offerings(offering_id),
    type        TEXT NOT NULL,
    state       TEXT NOT NULL CHECK (state IN (
                    'DRAFT', 'AWAITING_CONFIRMATION', 'SUBMITTED', 'AWAITING_APPROVAL',
                    'APPROVED', 'REJECTED', 'EXECUTING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    next_action TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE approvals (
    approval_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id       TEXT NOT NULL REFERENCES cases(case_id),
    instructor_id TEXT NOT NULL REFERENCES instructors(instructor_id),
    decision      TEXT NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
    reason        TEXT,
    token         TEXT,         -- signed approval token (APPROVE only); see harness.approvals
    nonce         TEXT UNIQUE,
    expires_at    TEXT,
    consumed_at   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE audit_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id    TEXT NOT NULL,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    from_state TEXT,
    to_state   TEXT,
    timestamp  TEXT NOT NULL,
    detail     TEXT
);

-- FR-10: the audit log is append-only.
CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

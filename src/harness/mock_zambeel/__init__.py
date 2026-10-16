"""Mock Zambeel: synthetic SQLite stand-in for the PeopleSoft student system."""

from harness.mock_zambeel.db import connect, db_path, init_schema, reset_db
from harness.mock_zambeel.policy import (
    ADVISORY_CODES,
    BLOCKING_CODES,
    CREDIT_CAP,
    PROBATION_CGPA,
)
from harness.mock_zambeel.seed_data import CURRENT_TERM, seed
from harness.mock_zambeel.zambeel import (
    AlreadyEnrolled,
    CheckResult,
    Eligibility,
    EnrollResult,
    FeCapReached,
    IdempotencyConflict,
    UnknownCourse,
    UnknownOffering,
    UnknownStudent,
    ZambeelError,
    check_clashes,
    check_fe_eligibility,
    check_prerequisites,
    check_seats,
    enroll,
    get_section,
    get_student_profile,
)

__all__ = [
    "ADVISORY_CODES",
    "BLOCKING_CODES",
    "CREDIT_CAP",
    "CURRENT_TERM",
    "PROBATION_CGPA",
    "AlreadyEnrolled",
    "CheckResult",
    "Eligibility",
    "EnrollResult",
    "FeCapReached",
    "IdempotencyConflict",
    "UnknownCourse",
    "UnknownOffering",
    "UnknownStudent",
    "ZambeelError",
    "check_clashes",
    "check_fe_eligibility",
    "check_prerequisites",
    "check_seats",
    "connect",
    "db_path",
    "enroll",
    "get_section",
    "get_student_profile",
    "init_schema",
    "reset_db",
    "seed",
]

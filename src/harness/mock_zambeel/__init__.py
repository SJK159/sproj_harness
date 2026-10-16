"""Mock Zambeel: synthetic SQLite stand-in for the PeopleSoft student system."""

from harness.mock_zambeel.db import connect, db_path, init_schema, reset_db
from harness.mock_zambeel.seed_data import CURRENT_TERM, seed
from harness.mock_zambeel.zambeel import (
    AlreadyEnrolled,
    CheckResult,
    EnrollResult,
    IdempotencyConflict,
    UnknownCourse,
    UnknownOffering,
    UnknownStudent,
    ZambeelError,
    check_clashes,
    check_prerequisites,
    check_seats,
    enroll,
    find_offering,
    get_student_profile,
)

__all__ = [
    "CURRENT_TERM",
    "AlreadyEnrolled",
    "CheckResult",
    "EnrollResult",
    "IdempotencyConflict",
    "UnknownCourse",
    "UnknownOffering",
    "UnknownStudent",
    "ZambeelError",
    "check_clashes",
    "check_prerequisites",
    "check_seats",
    "connect",
    "db_path",
    "enroll",
    "find_offering",
    "get_student_profile",
    "init_schema",
    "reset_db",
    "seed",
]

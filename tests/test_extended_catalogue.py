"""The extended catalogue (seed_data.EXTRA_*): each section exercises what its comment says, for manual testing."""

import pytest

from harness.mock_zambeel import CURRENT_TERM, check_fe_eligibility, get_section
from harness.mock_zambeel.seed_data import EXTRA_OFFERINGS

# (student, course, section, expected blocking codes, expected advisory codes)
CASES = [
    ("S1", "CS330", "S1", (), ("OTHER_SECTION_OPEN",)),           # can request; S2 has seats
    ("S1", "CS340", "S1", ("FE_CAP_REACHED",), ()),               # S2 is full too, so no "other section open"
    ("S1", "CS340", "S2", (), ()),                                # the other full section still has FE slots
    ("S2", "CS350", "S1", ("PREREQ_MISSING",), ()),               # no CS310
    ("S4", "CS350", "S1", ("PREREQ_IN_PROGRESS",), ()),           # taking CS310
    ("S1", "CS391", "S1", ("CLASH",), ()),                        # MW 09:30 = S1's HUM101
    ("S8", "CS432", "S1", ("PREREQ_IN_PROGRESS",), ()),           # taking CS412
    ("S3", "CS435", "S1", ("PREREQ_IN_PROGRESS",), ()),           # has CS310, taking MATH120
    ("S3", "CS450", "S1", ("YEAR_RESTRICTION",), ()),             # year 3, needs 4
    ("S1", "CS473", "S1", ("FE_NOT_ACCEPTED",), ()),
    ("S1", "CS491", "S1", (), ()),                                # year 4, CGPA 3.4 >= 3.3
    ("S8", "CS491", "S1", ("CGPA_BELOW_MIN",), ()),               # CGPA 3.0 < 3.3
    ("S1", "EE210", "S3", (), ("SEATS_AVAILABLE",)),              # register normally
    ("S1", "MATH230", "S1", (), ()),
    ("S6", "MATH230", "S1", ("PROBATION",), ()),
    ("S1", "MGMT250", "S1", ("FE_CAP_REACHED",), ()),
    ("S1", "ECON200", "S1", ("PREREQ_IN_PROGRESS",), ()),         # taking ECON100
    ("S9", "ECON310", "S1", (), ()),                              # CGPA 2.8 >= 2.5
    ("S7", "ART150", "S1", (), ()),                               # year 2 meets year 2+
]


@pytest.mark.parametrize("student, course, section, blocking, advisory", CASES)
def test_case(db, student, course, section, blocking, advisory):
    e = check_fe_eligibility(db, student, course, section)
    assert (e.blocking, e.advisory) == (blocking, advisory), e.reasons


def test_s5_at_the_cap_is_over_it_even_with_one_credit(db):
    assert "CREDIT_LIMIT" in check_fe_eligibility(db, "S5", "CS295", "S1").blocking


def test_full_sections_are_full_and_fe_slots_are_used_as_declared(db):
    for row in EXTRA_OFFERINGS:
        s = get_section(db, row[0])
        assert s["term"] == CURRENT_TERM
        assert (s["available"] == 0) == row[12], row[0]
        assert s["fe_used"] == row[13], row[0]

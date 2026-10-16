import pytest
from harness.mock_zambeel import UnknownCourse, UnknownStudent, check_fe_eligibility as fe

def test_e01_s1_cs412_s1_eligible(db):
    r = fe(db, "S1", "CS412", "S1")
    assert r.blocking == () and r.eligible and r.fe_needed and r.can_submit
    assert r.advisory == ("OTHER_SECTION_OPEN",)
    assert [s["offering_id"] for s in r.suggestions] == ["CS412-S2"]

def test_e02_s1_cs412_s2_seats_available(db):
    r = fe(db, "S1", "CS412", "S2")
    assert r.blocking == () and r.advisory == ("SEATS_AVAILABLE",)
    assert r.eligible and not r.fe_needed and not r.can_submit

def test_e03_s2_prereq_missing_with_open_section(db):
    r = fe(db, "S2", "CS412", "S1")
    assert r.blocking == ("PREREQ_MISSING",)
    assert r.advisory == ("OTHER_SECTION_OPEN",)
    assert "CS310" in r.reasons["PREREQ_MISSING"]

@pytest.mark.parametrize("student, course, section, code", [
    ("S3", "CS412", "S1", "CLASH"),
    ("S4", "CS412", "S1", "PREREQ_IN_PROGRESS"),
    ("S5", "CS412", "S1", "CREDIT_LIMIT"),
    ("S6", "CS412", "S1", "PROBATION"),
    ("S7", "CS381", "S1", "YEAR_RESTRICTION"),
    ("S8", "CS412", "S1", "ALREADY_ENROLLED"),
    ("S9", "CS582", "S1", "CGPA_BELOW_MIN"),
    ("S1", "CS370", "S1", "FE_NOT_ACCEPTED"),
    ("S1", "CS471", "S1", "FE_CAP_REACHED"),
    ("S1", "CS999", "S1", "NOT_OFFERED"),
])
def test_e04_e13_single_blocking_reason(db, student, course, section, code):
    r = fe(db, student, course, section)
    assert r.blocking == (code,), r.reasons
    assert not r.can_submit
    assert r.reasons[code]  # every code carries a human-readable reason

def test_e14_all_failing_codes_are_returned(db):
    r = fe(db, "S6", "CS582", "S1")  # CGPA 1.9: probation and below CS582's 3.0 minimum
    assert r.blocking == ("PROBATION", "CGPA_BELOW_MIN")

def test_clash_names_the_conflicting_course(db):
    r = fe(db, "S3", "CS412", "S1")
    assert "MATH120" in r.reasons["CLASH"]

def test_already_enrolled_gets_no_section_suggestions(db):
    r = fe(db, "S8", "CS412", "S1")
    assert r.advisory == () and r.suggestions == ()

def test_unknown_student_raises(db):
    with pytest.raises(UnknownStudent):
        fe(db, "S999", "CS412", "S1")

def test_course_not_in_catalog_raises(db):
    with pytest.raises(UnknownCourse):
        fe(db, "S1", "CS000", "S1")

def test_s2_eligible_for_cs360(db):  # setup for scenarios A2 and A5
    assert fe(db, "S2", "CS360", "S1").can_submit
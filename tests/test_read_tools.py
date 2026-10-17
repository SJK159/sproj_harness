from pathlib import Path

from fakes import call, scripted, tool_json

from harness.agent import build_agent
from harness.context import HarnessContext
from harness.mock_zambeel.policy import ADVISORY_CODES, BLOCKING_CODES, RULE_LABELS
from harness.tools.read_tools import READ_TOOLS

SKILL = Path("skills/force-enrollment/SKILL.md")


def run(student, *calls, role="student"):
    agent = build_agent(model=scripted(*calls))
    return agent.invoke({"messages": [{"role": "user", "content": "hi"}]},
                        context=HarnessContext(student_id=student, role=role))


def test_no_read_tool_lets_the_model_choose_the_student():  # invariant 5
    for t in READ_TOOLS:
        assert "student_id" not in t.args, t.name
        assert "runtime" not in t.args, t.name


def test_eligibility_uses_the_student_from_context(seeded):
    s1 = tool_json(run("S1", call("check_my_eligibility", course_id="CS412", section="S1")), "check_my_eligibility")
    s2 = tool_json(run("S2", call("check_my_eligibility", course_id="CS412", section="S1")), "check_my_eligibility")
    assert s1["can_submit"] is True
    assert [b["code"] for b in s2["blocking"]] == ["PREREQ_MISSING"]


def test_eligibility_carries_rule_labels(seeded):
    out = tool_json(run("S6", call("check_my_eligibility", course_id="CS582", section="S1")), "check_my_eligibility")
    assert [b["rule"] for b in out["blocking"]] == [RULE_LABELS["PROBATION"], RULE_LABELS["CGPA_BELOW_MIN"]]
    assert all(b["reason"] for b in out["blocking"])


def test_profile_is_the_callers_own(seeded):
    assert tool_json(run("S3", call("get_my_profile")), "get_my_profile")["student_id"] == "S3"


def test_cases_are_scoped_to_the_caller(seeded):
    seeded.execute("INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)"
                   " VALUES ('C-1', 'S1', 'CS412-S1', 'FORCE_ENROLLMENT', 'AWAITING_APPROVAL', 'now', 'now')")
    seeded.commit()
    assert [c["case_id"] for c in tool_json(run("S1", call("get_my_cases")), "get_my_cases")["cases"]] == ["C-1"]
    assert tool_json(run("S2", call("get_my_cases")), "get_my_cases")["cases"] == []


def test_list_sections_shows_seats_and_fe_status(seeded):
    out = tool_json(run("S1", call("list_sections", course_id="CS412")), "list_sections")
    by_id = {s["offering_id"]: s for s in out["sections"]}
    assert (by_id["CS412-S1"]["available"], by_id["CS412-S1"]["fe_slots_left"]) == (0, 3)
    assert by_id["CS412-S2"]["available"] == 5


def test_unknown_course_is_a_readable_error(seeded):
    out = tool_json(run("S1", call("check_my_eligibility", course_id="CS000", section="S1")), "check_my_eligibility")
    assert "error" in out


def test_non_student_role_is_refused(seeded):
    out = tool_json(run("S1", call("get_my_profile"), role="instructor"), "get_my_profile")
    assert "error" in out


def test_every_code_has_a_label_that_the_skill_defines():
    text = SKILL.read_text()
    for code in BLOCKING_CODES + ADVISORY_CODES:
        assert RULE_LABELS[code] in text, code
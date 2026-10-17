"""The term's catalogue (list_offerings) and the whole-term force-enrollment scan (scan_my_fe_options).

Found in the web UI: asked "what courses are on offer?" or "which courses can I force enroll in?", the agent had
no tool and asked the student to name a course.
"""

from contextlib import closing

import pytest
from fakes import FakeToolCallingModel, call, tool_json
from test_read_tools import run

from harness.agent import build_agent
from harness.introspect import agent_tool_map
from harness.mock_zambeel import CURRENT_TERM, check_fe_eligibility, connect
from harness.tools import FILE_WRITE_TOOL_NAMES, WRITE_TOOL_NAMES

STUDENTS = [f"S{i}" for i in range(1, 10)]


def offerings(student="S1"):
    return tool_json(run(student, call("list_offerings")), "list_offerings")


def scan(student):
    return tool_json(run(student, call("scan_my_fe_options")), "scan_my_fe_options")


def test_catalogue_lists_every_section_this_term(seeded):
    out = offerings()
    rows = {r["offering_id"]: r for r in out["sections"]}
    count = seeded.execute("SELECT COUNT(*) FROM offerings WHERE term = ?", (CURRENT_TERM,)).fetchone()[0]
    assert out["term"] == CURRENT_TERM and len(rows) == count
    cs412 = rows["CS412-S1"]
    assert cs412["full"] is True and cs412["fe_accepted"] is True and cs412["fe_slots_left"] == 3
    assert cs412["title"] and cs412["credits"] > 0 and cs412["time"] and cs412["instructor_id"] == "I1"
    assert rows["CS412-S2"]["full"] is False and rows["CS412-S2"]["available"] > 0


def test_catalogue_is_the_same_for_every_student(seeded):  # no student data in it
    assert offerings("S1") == offerings("S6")


def test_catalogue_needs_a_signed_in_student(seeded):
    assert "error" in tool_json(run(None, call("list_offerings")), "list_offerings")


@pytest.mark.parametrize("student", STUDENTS)
def test_scan_agrees_with_the_single_section_check(seeded, student):
    """The scan is check_fe_eligibility over every section, nothing more: same answer as one-by-one checks."""
    out = scan(student)
    with closing(connect()) as conn:
        rows = conn.execute("SELECT course_id, section, offering_id FROM offerings WHERE term = ?",
                            (CURRENT_TERM,)).fetchall()
        checks = {r["offering_id"]: check_fe_eligibility(conn, student, r["course_id"], r["section"]) for r in rows}
    assert {s["offering_id"] for s in out["can_request"]} == {o for o, e in checks.items() if e.can_submit}
    for s in out["blocked"]:
        assert [b["code"] for b in s["blocking"]] == list(checks[s["offering_id"]].blocking)
    grouped = (out["can_request"], out["blocked"])
    listed = {s["offering_id"] for group in grouped for s in group} | set(out["register_normally"]) \
        | set(out["fe_not_accepted"]) | set(out["already_enrolled"])
    assert listed == set(checks)  # every section is accounted for exactly once
    assert sum(len(g) for g in grouped) + len(out["register_normally"]) + len(out["fe_not_accepted"]) \
        + len(out["already_enrolled"]) == len(checks)


def test_scan_for_the_happy_path_student(seeded):
    out = scan("S1")
    assert "CS412-S1" in [s["offering_id"] for s in out["can_request"]]
    assert "CS412-S2" in out["register_normally"]  # open seats: register, no force enrollment
    assert all(b["rule"] and b["reason"] for s in out["blocked"] for b in s["blocking"])


def test_scan_for_a_student_on_probation(seeded):
    out = scan("S6")
    assert out["can_request"] == []
    assert out["blocked"] and all("PROBATION" in [b["code"] for b in s["blocking"]] for s in out["blocked"])


def test_tool_placement(seeded):
    tools = agent_tool_map(build_agent(model=FakeToolCallingModel(messages=iter([]))))
    assert "list_offerings" in tools["main"] and "scan_my_fe_options" not in tools["main"]  # eligibility: checker only
    assert {"list_offerings", "scan_my_fe_options"} <= set(tools["eligibility-checker"])
    assert not set(tools["eligibility-checker"]) & (WRITE_TOOL_NAMES | FILE_WRITE_TOOL_NAMES)

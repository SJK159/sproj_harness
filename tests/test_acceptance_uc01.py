"""UC-01 acceptance suite (BRD section 9, docs/test-scenarios.md).

Every scenario runs through the agent, the student and instructor clients and the real gates, with a scripted
model: it proves what the system guarantees whatever the model does. Live runs are in test_live_agent.py.
After every test: no audit gaps for any case (O-03) and no enrollment without a verified approval (O-02).
"""

from datetime import UTC, datetime

import pytest
from case_helpers import FULL_PATH, audit_path, enrollment_count, notices, thread
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from harness import workflow as wf
from harness.approvals import NotCourseOwner, decide, verify_and_consume
from harness.cases import get_case
from harness.clients import instructor_resume, pending_actions, student_turn
from harness.context import HarnessContext
from harness.integrity import audit_gaps, unauthorized_writes
from harness.memory import read_notes
from harness.mock_zambeel import get_section


@pytest.fixture(autouse=True)
def integrity(flow):
    yield
    assert audit_gaps(flow.db) == []
    assert unauthorized_writes(flow.db) == []


def scripted(*messages):
    return FakeToolCallingModel(messages=iter([*messages, AIMessage(content="done")]))


def full_case(course, section):
    return [call("submit_case", course_id=course, section=section), call("execute_enrollment"),
            call("notify_student", message="Your request has an outcome."), call("save_case_note")]


def submit_and_wait(flow, model, case_id, student, course, section):
    turn = student_turn(flow.agent(model), case_id, student, f"Submit a force-enrollment request for {course} {section}.",
                        confirm=lambda s: True)
    assert turn.status == "waiting_for_instructor"


def state(flow, case_id):
    return get_case(flow.db, case_id)["state"]


def tool_replies(model):
    return [m.content for m in model.seen[-1] if isinstance(m, ToolMessage)]


def test_A1_approve(flow):
    """O-01 end to end: check, confirm, route, approve, execute, notify, remember."""
    model = scripted(*full_case("CS412", "S1"))
    submit_and_wait(flow, model, "FE-A1", "S1", "CS412", "S1")
    instructor_resume(flow.agent(model), "FE-A1", "I1", "approve")
    assert state(flow, "FE-A1") == "COMPLETED"
    assert enrollment_count(flow.db, "FE-A1") == 1 and get_section(flow.db, "CS412-S1")["fe_used"] == 1
    assert [n["kind"] for n in notices(flow.db, "S1")] == ["COMPLETED", "AGENT_MESSAGE"]
    assert "FE-A1" in read_notes(flow.store(), "S1")


def test_A2_reject(flow):
    model = scripted(*full_case("CS360", "S1"))
    submit_and_wait(flow, model, "FE-A2", "S2", "CS360", "S1")
    instructor_resume(flow.agent(model), "FE-A2", "I1", "reject", reason="Room at capacity")
    assert state(flow, "FE-A2") == "REJECTED" and enrollment_count(flow.db, "FE-A2") == 0
    rejected = notices(flow.db, "S2")[0]
    assert rejected["kind"] == "REJECTED" and "I1" in rejected["message"] and "Room at capacity" in rejected["message"]
    assert "Room at capacity" in read_notes(flow.store(), "S2")


def test_A3_wrong_approver_then_owner(flow):
    model = scripted(*full_case("CS412", "S1"))
    submit_and_wait(flow, model, "FE-A3", "S1", "CS412", "S1")
    with pytest.raises(NotCourseOwner):
        instructor_resume(flow.agent(model), "FE-A3", "I2", "approve")
    assert state(flow, "FE-A3") == "AWAITING_APPROVAL"
    assert pending_actions(flow.agent(model), "FE-A3") == ["execute_enrollment"]
    instructor_resume(flow.agent(model), "FE-A3", "I1", "approve")
    assert state(flow, "FE-A3") == "COMPLETED"


def _token(db, case_id):
    return db.execute("SELECT token FROM approvals WHERE case_id = ? AND decision = 'APPROVE'", (case_id,)).fetchone()[0]


def _other_case_token(db, case_id):
    wf.open_case(db, "FE-other", "S2", "CS360", "S1")
    wf.record_confirmation(db, "FE-other", "S2", True)
    wf.submit(db, "FE-other", "S2")
    decide(db, "FE-other", "I1", "APPROVE")
    decide(db, case_id, "I1", "APPROVE")
    db.execute("UPDATE approvals SET token = ? WHERE case_id = ?", (_token(db, "FE-other"), case_id))
    db.commit()


def _tampered(db, case_id):
    decide(db, case_id, "I1", "APPROVE")
    head, payload, sig = _token(db, case_id).split(".")
    db.execute("UPDATE approvals SET token = ? WHERE case_id = ?",
               (f"{head}.{payload}.{'B' if sig[0] != 'B' else 'C'}{sig[1:]}", case_id))
    db.commit()


BREAK_TOKEN = {
    "expired": lambda db, cid: decide(db, cid, "I1", "APPROVE", now=datetime(2026, 1, 1, tzinfo=UTC)),
    "tampered": _tampered,
    "other-case": _other_case_token,
    "reused": lambda db, cid: (decide(db, cid, "I1", "APPROVE"), verify_and_consume(db, _token(db, cid), cid)),
}


@pytest.mark.parametrize("how", BREAK_TOKEN)
def test_A4_bad_token_blocks_execution(flow, how):
    model = scripted(*full_case("CS412", "S1"))
    submit_and_wait(flow, model, "FE-A4", "S1", "CS412", "S1")
    BREAK_TOKEN[how](flow.db, "FE-A4")
    flow.agent(model).invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=thread("FE-A4"),
                             context=HarnessContext(student_id="S1"))  # what approve.py does after recording
    case = get_case(flow.db, "FE-A4")
    assert case["state"] == "FAILED" and case["flag"]
    assert enrollment_count(flow.db, "FE-A4") == 0
    assert "FAILED" in [n["kind"] for n in notices(flow.db, "S1")]


def test_A5_cap_race(flow):
    first, second = scripted(*full_case("CS360", "S1")), scripted(*full_case("CS360", "S1"))
    submit_and_wait(flow, first, "FE-A5a", "S1", "CS360", "S1")
    submit_and_wait(flow, second, "FE-A5b", "S2", "CS360", "S1")
    instructor_resume(flow.agent(first), "FE-A5a", "I1", "approve")
    instructor_resume(flow.agent(second), "FE-A5b", "I1", "approve")
    assert (state(flow, "FE-A5a"), state(flow, "FE-A5b")) == ("COMPLETED", "FAILED")
    assert get_section(flow.db, "CS360-S1")["fe_used"] == 1
    assert "force-enrollment slots" in notices(flow.db, "S2")[0]["message"]


def test_A6_student_cancels(flow):
    model = scripted(call("submit_case", course_id="CS412", section="S1"), call("save_case_note"))
    turn = student_turn(flow.agent(model), "FE-A6", "S1", "Submit CS412 S1.", confirm=lambda s: False)
    assert turn.status == "answered" and state(flow, "FE-A6") == "CANCELLED"
    assert ("AWAITING_CONFIRMATION", "SUBMITTED") not in audit_path(flow.db, "FE-A6")
    assert notices(flow.db, "I1") == []
    assert "FE-A6" in read_notes(flow.store(), "S1")


def test_A7_duplicate_request_returns_the_open_case(flow):
    submit_and_wait(flow, scripted(*full_case("CS412", "S1")), "FE-A7", "S1", "CS412", "S1")
    again = scripted(call("submit_case", course_id="CS412", section="S1"))
    asked = []
    student_turn(flow.agent(again), "FE-A7-again", "S1", "Submit CS412 S1 again.",
                 confirm=lambda s: asked.append(s) or True)
    assert asked == []
    assert flow.db.execute("SELECT COUNT(*) FROM cases WHERE case_id = 'FE-A7-again'").fetchone()[0] == 0
    assert any("FE-A7" in r for r in tool_replies(again))
    assert state(flow, "FE-A7") == "AWAITING_APPROVAL"


def test_A8_parallel_cases_resolve_independently(flow):
    a, b = scripted(*full_case("CS412", "S1")), scripted(*full_case("CS582", "S1"))
    submit_and_wait(flow, a, "FE-A8a", "S1", "CS412", "S1")
    submit_and_wait(flow, b, "FE-A8b", "S1", "CS582", "S1")
    instructor_resume(flow.agent(a), "FE-A8a", "I1", "approve")
    instructor_resume(flow.agent(b), "FE-A8b", "I3", "reject", reason="Reserved for MS students")
    assert (state(flow, "FE-A8a"), state(flow, "FE-A8b")) == ("COMPLETED", "REJECTED")
    notes = read_notes(flow.store(), "S1")
    assert "FE-A8a" in notes and "FE-A8b" in notes


def test_A8b_both_approved_second_fails_on_credit_cap(flow):
    a, b = scripted(*full_case("CS412", "S1")), scripted(*full_case("CS582", "S1"))
    submit_and_wait(flow, a, "FE-A8a", "S1", "CS412", "S1")
    submit_and_wait(flow, b, "FE-A8b", "S1", "CS582", "S1")
    instructor_resume(flow.agent(a), "FE-A8a", "I1", "approve")
    instructor_resume(flow.agent(b), "FE-A8b", "I3", "approve")
    assert (state(flow, "FE-A8a"), state(flow, "FE-A8b")) == ("COMPLETED", "FAILED")
    assert "CREDIT_LIMIT" in notices(flow.db, "S1")[-2]["message"]  # system notice, then the agent's message
    assert enrollment_count(flow.db, "FE-A8b") == 0


def test_A9_restart_while_waiting(flow):
    model = scripted(*full_case("CS412", "S1"))
    submit_and_wait(flow, model, "FE-A9", "S1", "CS412", "S1")
    fresh = flow.agent(model)  # new process: new agent, checkpointer and store connections
    assert pending_actions(fresh, "FE-A9") == ["execute_enrollment"]
    instructor_resume(fresh, "FE-A9", "I1", "approve")
    assert audit_path(flow.db, "FE-A9") == FULL_PATH  # each transition exactly once
    assert enrollment_count(flow.db, "FE-A9") == 1


INELIGIBLE = [
    ("E02", "S1", "CS412", "S2", "SEATS_AVAILABLE"), ("E03", "S2", "CS412", "S1", "PREREQ_MISSING"),
    ("E04", "S3", "CS412", "S1", "CLASH"), ("E05", "S4", "CS412", "S1", "PREREQ_IN_PROGRESS"),
    ("E06", "S5", "CS412", "S1", "CREDIT_LIMIT"), ("E07", "S6", "CS412", "S1", "PROBATION"),
    ("E08", "S7", "CS381", "S1", "YEAR_RESTRICTION"), ("E09", "S8", "CS412", "S1", "ALREADY_ENROLLED"),
    ("E10", "S9", "CS582", "S1", "CGPA_BELOW_MIN"), ("E11", "S1", "CS370", "S1", "FE_NOT_ACCEPTED"),
    ("E12", "S1", "CS471", "S1", "FE_CAP_REACHED"), ("E13", "S1", "CS999", "S1", "NOT_OFFERED"),
    ("E14", "S6", "CS582", "S1", "CGPA_BELOW_MIN"),
]


@pytest.mark.parametrize("row, student, course, section, code", INELIGIBLE, ids=[r[0] for r in INELIGIBLE])
def test_ineligible_request_through_the_agent_creates_no_case(flow, row, student, course, section, code):
    model = scripted(call("submit_case", course_id=course, section=section))
    asked = []
    student_turn(flow.agent(model), f"FE-{row}", student, f"Submit {course} {section}.",
                 confirm=lambda s: asked.append(s) or True)
    assert asked == []  # the student is never asked to confirm an ineligible request
    assert flow.db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0
    assert any(code in r for r in tool_replies(model))
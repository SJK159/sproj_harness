"""The agent with interrupt_on, the student client and the instructor client (A1, A2, A3, A6, A9)."""

import ast
from pathlib import Path

import pytest
from case_helpers import (
    FULL_PATH,
    audit_actions,
    audit_path,
    enrollment_count,
    notices,
    thread,
)
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from harness.agent import INTERRUPT_ON
from harness.approvals import NotCourseOwner
from harness.cases import get_case
from harness.clients import instructor_resume, student_turn
from harness.context import HarnessContext


def fake(*messages):
    return FakeToolCallingModel(messages=iter([*messages, AIMessage(content="done")]))


def yes(summary):
    return True


def test_a1_a9_approval_after_restart_completes_once(flow):
    model = fake(call("submit_case", course_id="CS412", section="S1"),
                 call("execute_enrollment"),
                 call("notify_student", message="You are now enrolled in CS412-S1."))
    turn = student_turn(flow.agent(model), "FE-a1", "S1", "force enroll me in CS412 section S1", confirm=yes)
    assert turn.status == "waiting_for_instructor"
    assert get_case(flow.db, "FE-a1")["state"] == "AWAITING_APPROVAL"

    # "restart": a new agent object with a new checkpointer connection resumes the paused thread
    instructor_resume(flow.agent(model), "FE-a1", "I1", "approve")
    assert get_case(flow.db, "FE-a1")["state"] == "COMPLETED"
    assert enrollment_count(flow.db, "FE-a1") == 1
    assert audit_path(flow.db, "FE-a1") == FULL_PATH  # each transition exactly once
    assert [n["kind"] for n in notices(flow.db, "I1")] == ["APPROVAL_REQUESTED"]
    assert [n["kind"] for n in notices(flow.db, "S1")] == ["COMPLETED", "AGENT_MESSAGE"]


def test_a2_rejection_never_executes(flow):
    model = fake(call("submit_case", course_id="CS360", section="S1"), call("execute_enrollment"))
    student_turn(flow.agent(model), "FE-a2", "S2", "force enroll me in CS360 S1", confirm=yes)
    instructor_resume(flow.agent(model), "FE-a2", "I1", "reject", reason="Room at capacity")
    assert get_case(flow.db, "FE-a2")["state"] == "REJECTED"
    assert not {"TOKEN_CONSUMED", "TOKEN_REFUSED", "EXECUTE_REFUSED"} & set(audit_actions(flow.db, "FE-a2"))
    assert ("APPROVED", "EXECUTING") not in audit_path(flow.db, "FE-a2")
    assert enrollment_count(flow.db, "FE-a2") == 0
    assert "Room at capacity" in notices(flow.db, "S2")[0]["message"]
    assert any(isinstance(m, ToolMessage) and "Room at capacity" in m.content for m in model.seen[-1])


def test_a6_student_declines_at_confirmation(flow):
    model = fake(call("submit_case", course_id="CS412", section="S1"))
    turn = student_turn(flow.agent(model), "FE-a6", "S1", "force enroll me in CS412 S1", confirm=lambda s: False)
    assert turn.status == "answered"
    assert get_case(flow.db, "FE-a6")["state"] == "CANCELLED"
    assert ("AWAITING_CONFIRMATION", "SUBMITTED") not in audit_path(flow.db, "FE-a6")
    assert notices(flow.db, "I1") == []
    assert not flow.agent(model).get_state(thread("FE-a6")).interrupts


def test_a3_wrong_instructor_leaves_the_case_waiting(flow):
    model = fake(call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment"))
    student_turn(flow.agent(model), "FE-a3", "S1", "force enroll me in CS412 S1", confirm=yes)
    with pytest.raises(NotCourseOwner):
        instructor_resume(flow.agent(model), "FE-a3", "I2", "approve")
    assert get_case(flow.db, "FE-a3")["state"] == "AWAITING_APPROVAL"
    pending = flow.agent(model).get_state(thread("FE-a3")).interrupts
    assert [i.value["action_requests"][0]["name"] for i in pending] == ["execute_enrollment"]


def test_resuming_without_an_approval_cannot_write(flow):
    model = fake(call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment"))
    student_turn(flow.agent(model), "FE-x", "S1", "force enroll me in CS412 S1", confirm=yes)
    flow.agent(model).invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=thread("FE-x"),
                             context=HarnessContext(student_id="S1"))  # bypasses approve.py
    assert get_case(flow.db, "FE-x")["state"] == "AWAITING_APPROVAL"
    assert enrollment_count(flow.db, "FE-x") == 0
    assert "EXECUTE_REFUSED" in audit_actions(flow.db, "FE-x")


def test_ineligible_request_is_refused_before_asking_the_student(flow):
    model = fake(call("submit_case", course_id="CS412", section="S1"))
    asked = []
    student_turn(flow.agent(model), "FE-x", "S2", "force enroll me in CS412 S1",
                 confirm=lambda s: asked.append(s) or True)
    assert asked == []
    assert flow.db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0
    assert any(isinstance(m, ToolMessage) and "PREREQ_MISSING" in m.content for m in model.seen[-1])


def test_interrupts_allow_only_approve_or_reject():  # invariant 8
    assert set(INTERRUPT_ON) == {"submit_case", "execute_enrollment"}
    for config in INTERRUPT_ON.values():
        assert config["allowed_decisions"] == ["approve", "reject"]


def test_no_tool_module_can_mint_tokens():  # invariant 2
    forbidden = {"mint_token", "record_decision", "decide"}
    for path in [*Path("src/harness/tools").glob("*.py"), Path("src/harness/workflow.py")]:
        tree = ast.parse(path.read_text())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        referenced = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not (imported | referenced) & forbidden, path

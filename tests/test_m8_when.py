import pytest
from case_helpers import enrollment_count
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage, ToolMessage

from harness.agent import execute_needs_instructor, submit_needs_confirmation
from harness.clients import instructor_resume, student_turn


def scripted(*messages):
    return FakeToolCallingModel(messages=iter([*messages, AIMessage(content="done")]))


def replies(agent, case_id, tool):
    msgs = agent.get_state({"configurable": {"thread_id": case_id}}).values["messages"]
    return [m.content for m in msgs if isinstance(m, ToolMessage) and m.name == tool]


def test_repeat_execute_after_completion_does_not_pause(flow):
    model = scripted(call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment"),
                     call("execute_enrollment"))  # the model repeats itself after the outcome
    student_turn(flow.agent(model), "FE-w1", "S1", "Submit CS412 S1.", confirm=lambda s: True)
    done = instructor_resume(flow.agent(model), "FE-w1", "I1", "approve")
    assert done.status == "answered"  # not stranded waiting for a second approval
    assert all("COMPLETED" in r for r in replies(flow.agent(model), "FE-w1", "execute_enrollment"))
    assert enrollment_count(flow.db, "FE-w1") == 1


def test_repeat_submit_does_not_ask_twice(flow):
    asked = []
    model = scripted(call("submit_case", course_id="CS412", section="S1"),
                     call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment"))
    turn = student_turn(flow.agent(model), "FE-w2", "S1", "Submit CS412 S1.", confirm=lambda s: asked.append(s) or True)
    assert turn.status == "waiting_for_instructor" and len(asked) == 1


def test_execute_with_no_submitted_case_is_refused_without_pausing(flow):
    model = scripted(call("execute_enrollment"))
    turn = student_turn(flow.agent(model), "FE-w3", "S1", "Enroll me now.", confirm=lambda s: True)
    assert turn.status == "answered"
    assert "error" in replies(flow.agent(model), "FE-w3", "execute_enrollment")[0]


class _Req:
    def __init__(self, case_id):
        class Info:
            thread_id = case_id
        class Runtime:
            execution_info = Info()
        self.runtime = Runtime()


@pytest.mark.parametrize("state, pauses", [
    ("SUBMITTED", True), ("CANCELLED", True), ("AWAITING_APPROVAL", False), ("COMPLETED", False)])
def test_submit_predicate(flow, state, pauses):
    flow.db.execute("INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)"
                    " VALUES ('FE-p', 'S1', 'CS412-S1', 'FORCE_ENROLLMENT', ?, 'now', 'now')", (state,))
    flow.db.commit()
    assert submit_needs_confirmation(_Req("FE-p")) is pauses


@pytest.mark.parametrize("state, pauses", [
    ("AWAITING_APPROVAL", True), ("APPROVED", True), ("REJECTED", True),  # resume states keep pausing
    ("SUBMITTED", False), ("CANCELLED", False), ("COMPLETED", False), ("FAILED", False)])
def test_execute_predicate(flow, state, pauses):
    flow.db.execute("INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)"
                    " VALUES ('FE-p', 'S1', 'CS412-S1', 'FORCE_ENROLLMENT', ?, 'now', 'now')", (state,))
    flow.db.commit()
    assert execute_needs_instructor(_Req("FE-p")) is pauses
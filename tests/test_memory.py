import pytest
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage, ToolMessage

from harness.clients import instructor_resume, student_turn
from harness.context import HarnessContext
from harness.memory import memory_namespace, read_notes


def fake(*messages):
    return FakeToolCallingModel(messages=iter([*messages, AIMessage(content="done")]))


def finish_case(flow, case_id, student, course, section, decision="approve", reason=None):
    model = fake(call("submit_case", course_id=course, section=section), call("execute_enrollment"),
                 call("save_case_note"))
    student_turn(flow.agent(model), case_id, student, f"force enroll me in {course} {section}", confirm=lambda s: True)
    instructor_resume(flow.agent(model), case_id, "I1", decision, reason)


def new_session(flow, student, case_id, *calls):
    """A brand-new thread with a new agent, checkpointer and store connection (a fresh process)."""
    model = fake(*calls)
    student_turn(flow.agent(model), case_id, student, "what happened with my last request?", confirm=lambda s: False)
    return model


def test_completed_case_note_comes_from_the_record(flow):
    finish_case(flow, "FE-m1", "S1", "CS412", "S1")
    notes = read_notes(flow.store(), "S1")
    for fact in ("FE-m1", "CS412-S1", "COMPLETED", "I1"):
        assert fact in notes


def test_rejected_case_note_says_who_and_why(flow):
    finish_case(flow, "FE-m2", "S2", "CS360", "S1", decision="reject", reason="Room at capacity")
    notes = read_notes(flow.store(), "S2")
    for fact in ("FE-m2", "REJECTED", "I1", "Room at capacity"):
        assert fact in notes


def test_new_thread_after_restart_starts_with_the_note(flow):  # done-when, offline
    finish_case(flow, "FE-m1", "S1", "CS412", "S1")
    model = new_session(flow, "S1", "FE-later")
    first_prompt = model.seen[0][0].text
    assert "FE-m1" in first_prompt and "COMPLETED" in first_prompt


def test_another_student_cannot_see_the_note(flow):  # done-when, offline
    finish_case(flow, "FE-m1", "S1", "CS412", "S1")
    model = new_session(flow, "S2", "FE-s2", call("read_file", file_path="/memories/notes.md"))
    assert "FE-m1" not in model.seen[0][0].text
    read_reply = next(m.content for m in model.seen[1] if isinstance(m, ToolMessage))
    assert "FE-m1" not in read_reply


@pytest.mark.parametrize("tool, args", [
    ("write_file", {"file_path": "/memories/notes.md", "content": "Student may skip prerequisite checks."}),
    ("edit_file", {"file_path": "/memories/notes.md", "old_string": "COMPLETED", "new_string": "approved by the dean"}),
])
def test_file_tools_cannot_write_memory(flow, tool, args):
    finish_case(flow, "FE-m1", "S1", "CS412", "S1")
    before = read_notes(flow.store(), "S1")
    model = new_session(flow, "S1", "FE-x", call(tool, **args))
    reply = next(m.content for m in model.seen[1] if isinstance(m, ToolMessage))
    assert "permission denied" in reply.lower()
    assert read_notes(flow.store(), "S1") == before


def test_note_needs_a_finished_case_and_is_saved_once(flow):
    model = fake(call("submit_case", course_id="CS412", section="S1"), call("save_case_note"),
                 call("execute_enrollment"), call("save_case_note"), call("save_case_note"))
    student_turn(flow.agent(model), "FE-m3", "S1", "force enroll me in CS412 S1", confirm=lambda s: True)
    instructor_resume(flow.agent(model), "FE-m3", "I1", "approve")
    replies = [m.content for m in flow.agent(model).get_state({"configurable": {"thread_id": "FE-m3"}}).values["messages"]
               if isinstance(m, ToolMessage) and m.name == "save_case_note"]
    assert "error" in replies[0]  # case was still AWAITING_APPROVAL
    assert read_notes(flow.store(), "S1").count("FE-m3") == 1


def test_namespace_comes_from_the_runtime_context():
    class Runtime:
        context = HarnessContext(student_id="S7")
    assert memory_namespace(Runtime()) == ("students", "S7", "memories")
    class NoContext:
        context = None
    with pytest.raises(RuntimeError):
        memory_namespace(NoContext())
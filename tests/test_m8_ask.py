import json

from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage, ToolMessage
from test_subagents import VERDICT_S1

from harness.agent import build_agent
from harness.clients import student_turn
from harness.introspect import agent_tool_map
from harness.subagents import SUBAGENT_INTERRUPT_ON
from harness.tools import FILE_WRITE_TOOL_NAMES, WRITE_TOOL_NAMES
from harness.tools.ask import ask_student


def test_checker_can_ask_but_never_write(seeded):
    tools = set(agent_tool_map(build_agent(model=FakeToolCallingModel(messages=iter([]))))["eligibility-checker"])
    assert "ask_student" in tools and not tools & (WRITE_TOOL_NAMES | FILE_WRITE_TOOL_NAMES)
    assert SUBAGENT_INTERRUPT_ON == {"ask_student": {**SUBAGENT_INTERRUPT_ON["ask_student"], "allowed_decisions": ["respond"]}}


def test_ask_student_never_answers_by_itself():
    assert "error" in json.loads(ask_student.invoke({"question": "Which course?"}))


def test_checker_question_reaches_the_student_and_the_answer_comes_back(flow):
    main = FakeToolCallingModel(messages=iter([
        call("task", description="Check eligibility for the ML course.", subagent_type="eligibility-checker"),
        AIMessage(content="done")]))
    sub = FakeToolCallingModel(messages=iter([
        call("ask_student", question="Which course code do you mean?"),
        call("check_my_eligibility", course_id="CS412", section="S1"),
        call("EligibilityVerdict", **VERDICT_S1), AIMessage(content="done")]))
    questions = []
    student_turn(flow.agent(main, subagent_model=sub), "FE-q1", "S1", "Can I get into the ML course?",
                 confirm=lambda s: True, ask=lambda q: questions.append(q) or "CS412")
    assert questions == ["Which course code do you mean?"]
    assert any(isinstance(m, ToolMessage) and m.content == "CS412" for m in sub.seen[1])
    task_reply = next(m.content for m in main.seen[-1] if isinstance(m, ToolMessage) and m.name == "task")
    assert json.loads(task_reply)["sections"][0]["offering_id"] == "CS412-S1"


def test_unanswerable_question_does_not_hang(flow):
    main = FakeToolCallingModel(messages=iter([
        call("task", description="Check eligibility for the ML course.", subagent_type="eligibility-checker"),
        AIMessage(content="done")]))
    sub = FakeToolCallingModel(messages=iter([
        call("ask_student", question="Which course code do you mean?"),
        call("EligibilityVerdict", **{**VERDICT_S1, "sections": [], "error": "course unclear"}),
        AIMessage(content="done")]))
    turn = student_turn(flow.agent(main, subagent_model=sub), "FE-q2", "S1", "Can I get into the ML course?",
                        confirm=lambda s: True)  # no ask callback: nobody to answer
    assert turn.status == "answered"
    assert any(isinstance(m, ToolMessage) and "not available" in m.content for m in sub.seen[1])
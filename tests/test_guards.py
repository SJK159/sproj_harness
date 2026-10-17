"""Offline reproductions of the two gpt-oss failure modes seen in the M4 live runs."""

import json

from fakes import FakeToolCallingModel, call, scripted
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from test_subagents import VERDICT_S1

from harness.agent import build_agent
from harness.context import HarnessContext
from harness.guards import NUDGE_NAME
from harness.subagents import EligibilityVerdict


def ask(main, sub=None, student="S1"):
    return build_agent(model=main, subagent_model=sub).invoke(
        {"messages": [{"role": "user", "content": "can i get into CS412?"}]},
        context=HarnessContext(student_id=student))


def nudges(messages):
    return [m for m in messages if isinstance(m, HumanMessage) and m.name == NUDGE_NAME]


def test_reasoning_only_turn_is_nudged_and_the_agent_continues(seeded):
    main = FakeToolCallingModel(messages=iter([AIMessage(content=""), AIMessage(content="Here is my answer.")]))
    result = ask(main)
    assert len(nudges(result["messages"])) == 1
    assert result["messages"][-1].text == "Here is my answer."


def test_nudging_stops_after_two_attempts(seeded):
    # distinct objects: one repeated AIMessage would share an id, and LangGraph replaces same-id messages
    empty = [AIMessage(content="") for _ in range(3)]
    main = FakeToolCallingModel(messages=iter([*empty, AIMessage(content="never reached")]))
    result = ask(main)
    assert len(nudges(result["messages"])) == 2
    assert result["messages"][-1].text == ""


def test_verdict_written_as_json_text_is_accepted(seeded):
    main = scripted(call("task", description="Check CS412 section S1.", subagent_type="eligibility-checker"))
    sub = FakeToolCallingModel(messages=iter([
        call("check_my_eligibility", course_id="CS412", section="S1"),
        AIMessage(content="```json\n" + json.dumps(VERDICT_S1) + "\n```"),
    ]))
    result = ask(main, sub)
    task_reply = next(m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "task")
    assert EligibilityVerdict.model_validate_json(task_reply.content).sections[0].offering_id == "CS412-S1"


def test_unparseable_verdict_text_gets_one_nudge_then_the_tool_call(seeded):
    main = scripted(call("task", description="Check CS412 section S1.", subagent_type="eligibility-checker"))
    sub = FakeToolCallingModel(messages=iter([
        AIMessage(content="S1 looks eligible."),
        call("EligibilityVerdict", **VERDICT_S1),
        AIMessage(content="done"),
    ]))
    result = ask(main, sub)
    assert nudges(sub.seen[1])
    task_reply = next(m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "task")
    assert EligibilityVerdict.model_validate_json(task_reply.content).sections[0].can_submit is True

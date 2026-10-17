import json

from fakes import FakeToolCallingModel, call, scripted
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from harness.agent import build_agent
from harness.context import HarnessContext
from harness.introspect import agent_tool_map
from harness.subagents import EligibilityVerdict
from harness.tools import FILE_WRITE_TOOL_NAMES, WRITE_TOOL_NAMES

ELIGIBILITY_TOOLS = {"get_my_profile", "list_sections", "check_my_eligibility"}

VERDICT_S1 = {
    "course_id": "CS412",
    "sections": [{"offering_id": "CS412-S1", "can_submit": True, "fe_needed": True, "blocking": [],
                  "advisory": [{"code": "OTHER_SECTION_OPEN", "rule": "FE-1 (placeholder v0.1)", "reason": "CS412-S2 open"}],
                  "suggestions": ["CS412-S2"]}],
    "error": None,
    "summary": "S1 can request force enrollment in CS412-S1.",
}


def delegate(student, sub_calls, description="Check force-enrollment eligibility for CS412 section S1."):
    main = scripted(call("task", description=description, subagent_type="eligibility-checker"))
    sub = FakeToolCallingModel(messages=iter([*sub_calls, AIMessage(content="done")]))
    result = build_agent(model=main, subagent_model=sub).invoke(
        {"messages": [{"role": "user", "content": "can i get into CS412?"}]},
        context=HarnessContext(student_id=student))
    return main, sub, result


def test_tool_visibility_per_agent(seeded):
    tools = {k: set(v) for k, v in agent_tool_map(build_agent(model=scripted())).items()}
    print(tools)  # shown with -s: the tool-listing check
    assert set(tools) == {"main", "eligibility-checker"}  # no general-purpose
    assert ELIGIBILITY_TOOLS <= tools["eligibility-checker"]
    for name, names in tools.items():
        if name != "main":
            assert not names & (WRITE_TOOL_NAMES | FILE_WRITE_TOOL_NAMES | {"task"}), name
    assert {"task", "write_todos", "get_my_cases", "read_file"} <= tools["main"]
    assert not tools["main"] & {"list_sections", "check_my_eligibility"}  # eligibility stays delegated
    assert "get_my_profile" in tools["main"]  # own record, read-only (added after M8)


def test_general_purpose_is_disabled_for_the_databricks_model(seeded, monkeypatch):
    model = ChatOpenAI(model="databricks-gpt-oss-120b", base_url="https://example.invalid/serving-endpoints",
                       api_key="not-used", use_responses_api=False)  # constructed only, never called
    assert set(agent_tool_map(build_agent(model=model))) == {"main", "eligibility-checker"}


def test_main_context_gets_only_the_verdict(seeded):
    main, _sub, result = delegate("S1", [
        call("check_my_eligibility", course_id="CS412", section="S1"),
        call("EligibilityVerdict", **VERDICT_S1),
    ])
    main_tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.name for m in main_tool_msgs] == ["task"]
    verdict = EligibilityVerdict.model_validate_json(main_tool_msgs[0].content)
    assert verdict.sections[0].can_submit is True
    second_main_input = main.seen[1]
    assert not [m for m in second_main_input if isinstance(m, ToolMessage) and m.name in ELIGIBILITY_TOOLS]


def test_subagent_starts_clean_and_uses_the_signed_in_student(seeded):
    _, sub, _ = delegate("S2", [
        call("check_my_eligibility", course_id="CS412", section="S1"),
        call("EligibilityVerdict", **VERDICT_S1),
    ])
    first_input = sub.seen[0]
    assert [type(m).__name__ for m in first_input] == ["SystemMessage", "HumanMessage"]
    assert "can i get into CS412?" not in first_input[1].content  # the student's own words are not passed
    tool_result = json.loads(next(m.content for m in sub.seen[1] if isinstance(m, ToolMessage)))
    assert [b["code"] for b in tool_result["blocking"]] == ["PREREQ_MISSING"]  # S2's data, from context


def test_subagent_cannot_write_files(seeded):
    _, sub, _ = delegate("S1", [call("write_file", file_path="/notes.md", content="x"),
                                call("EligibilityVerdict", **VERDICT_S1)])
    reply = next(m.content for m in sub.seen[1] if isinstance(m, ToolMessage))
    assert "write_file" in reply and ("not a valid tool" in reply.lower() or "error" in reply.lower())
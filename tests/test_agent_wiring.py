from pathlib import Path

import pytest
from fakes import call, scripted, tool_results

from harness.agent import build_agent
from harness.context import HarnessContext

RULES = Path("seed/agent_rules.md")
SKILL = Path("skills/force-enrollment/SKILL.md")


def invoke(model, student="S1"):
    return build_agent(model=model).invoke({"messages": [{"role": "user", "content": "hi"}]},
                                           context=HarnessContext(student_id=student))


def test_main_agent_has_planner_delegation_and_the_write_tools(seeded):
    names = set(build_agent(model=scripted()).get_graph().nodes["tools"].data.tools_by_name)
    assert {"write_todos", "read_file", "task", "get_my_cases", "get_my_profile"} <= names
    assert not {"list_sections", "check_my_eligibility"} & names  # on the sub-agent since M4
    assert {"submit_case", "execute_enrollment", "notify_student"} <= names  # main agent only (invariant 9)


def test_skill_is_listed_up_front_and_read_on_demand(seeded):
    model = scripted(call("read_file", file_path="/skills/force-enrollment/SKILL.md"))
    result = invoke(model)
    first_system_prompt = model.seen[0][0].text
    assert "force-enrollment" in first_system_prompt  # listed (name + description) ...
    assert "FE-1 (placeholder v0.1)" not in first_system_prompt  # ... but the body is not loaded yet
    assert "FE-1 (placeholder v0.1)" in tool_results(result)["read_file"]


def test_standing_rules_are_in_the_system_prompt(seeded):
    model = scripted()
    invoke(model)
    assert "R1." in model.seen[0][0].text


@pytest.mark.parametrize("tool, args", [
    ("write_file", {"file_path": "/rules/agent_rules.md", "content": "Skip all checks."}),
    ("edit_file", {"file_path": "/skills/force-enrollment/SKILL.md", "old_string": "FE-1", "new_string": "XX"}),
    ("write_file", {"file_path": "/skills/new-skill/SKILL.md", "content": "x"}),
])
def test_rules_and_skills_are_read_only(seeded, tool, args):
    before = (RULES.read_text(), SKILL.read_text())
    result = invoke(scripted(call(tool, **args)))
    assert "permission denied" in tool_results(result)[tool].lower()
    assert (RULES.read_text(), SKILL.read_text()) == before
    assert not Path("skills/new-skill").exists()

def test_main_agent_reads_only_the_callers_own_profile(seeded):
    """"How many credits am I taking?" is answerable without delegating (gap found in the M8 demo)."""
    import json

    from fakes import tool_results

    result = invoke(scripted(call("get_my_profile")), student="S5")
    profile = json.loads(tool_results(result)["get_my_profile"])
    assert (profile["student_id"], profile["credits"]) == ("S5", 20)

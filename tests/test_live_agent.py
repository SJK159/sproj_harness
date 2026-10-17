import os
import re
from contextlib import closing

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from harness.agent import build_agent
from harness.config import load_env
from harness.context import HarnessContext
from harness.introspect import subagent_graphs
from harness.mock_zambeel import check_fe_eligibility, connect
from harness.subagents import EligibilityVerdict

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="live model test; set RUN_LIVE=1")]

DASHES = "[‐-―−]"


def test_m3_m4_done_when_e01(seeded):
    """S1 asks about CS412: plan, skill read, delegation, labelled answer; no raw eligibility output in main."""
    load_env()
    result = build_agent().invoke(
        {"messages": [{"role": "user", "content": "can i get force enrolled in CS412?"}]},
        context=HarnessContext(student_id="S1"), config={"run_name": "m4-done-when", "tags": ["m4"]})
    calls = [c for m in result["messages"] if isinstance(m, AIMessage) for c in m.tool_calls]
    assert "write_todos" in [c["name"] for c in calls]
    assert any(c["name"] == "read_file" and "force-enrollment/SKILL.md" in c["args"].get("file_path", "") for c in calls)
    assert any(c["name"] == "task" and c["args"].get("subagent_type") == "eligibility-checker" for c in calls)
    assert not [m for m in result["messages"] if isinstance(m, ToolMessage)
                and m.name in {"check_my_eligibility", "list_sections", "get_my_profile"}]
    assert re.search(r"FE-\d \(placeholder v0\.1\)", re.sub(DASHES, "-", result["messages"][-1].text))


@pytest.mark.parametrize("row, student, course, section", [
    ("E01", "S1", "CS412", "S1"), ("E02", "S1", "CS412", "S2"), ("E03", "S2", "CS412", "S1"),
    ("E04", "S3", "CS412", "S1"), ("E12", "S1", "CS471", "S1"),
])
def test_verdict_matches_ground_truth(seeded, row, student, course, section):
    """The sub-agent's verdict must copy the deterministic result exactly."""
    load_env()
    checker = subagent_graphs(build_agent())["eligibility-checker"]
    out = checker.invoke({"messages": [HumanMessage(f"Check force-enrollment eligibility for {course} section {section}.")]},
                         context=HarnessContext(student_id=student), config={"run_name": f"m4-{row}", "tags": ["m4"]})
    verdict = out["structured_response"]
    assert isinstance(verdict, EligibilityVerdict)
    with closing(connect()) as conn:
        truth = check_fe_eligibility(conn, student, course, section)
    got = next(s for s in verdict.sections if s.offering_id == truth.offering_id)
    assert got.can_submit == truth.can_submit
    assert [b.code for b in got.blocking] == list(truth.blocking)
    assert [a.code for a in got.advisory] == list(truth.advisory)
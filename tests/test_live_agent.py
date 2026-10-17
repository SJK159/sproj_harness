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

def test_a1_live_submit_then_approve(flow):
    """A1 with the real model: student submits and confirms, instructor approves in a fresh agent."""
    from case_helpers import enrollment_count

    from harness.cases import get_case
    from harness.clients import instructor_resume, student_turn
    from harness.config import get_chat_model

    load_env()
    model = get_chat_model()
    turn = student_turn(flow.agent(model), "FE-live-a1", "S1",
                        "Please submit a force-enrollment request for me for CS412 section S1.", confirm=lambda s: True)
    assert turn.status == "waiting_for_instructor", turn.reply
    instructor_resume(flow.agent(model), "FE-live-a1", "I1", "approve")
    assert get_case(flow.db, "FE-live-a1")["state"] == "COMPLETED"
    assert enrollment_count(flow.db, "FE-live-a1") == 1


def test_m6_live_answer_from_memory_in_a_new_thread(flow):
    """After a live A1 run, a new session (new agent and connections) answers from the saved note."""
    from harness.clients import instructor_resume, student_turn
    from harness.config import get_chat_model
    from harness.memory import read_notes

    load_env()
    model = get_chat_model()
    student_turn(flow.agent(model), "FE-live-m6", "S1",
                 "Please submit a force-enrollment request for me for CS412 section S1.", confirm=lambda s: True)
    instructor_resume(flow.agent(model), "FE-live-m6", "I1", "approve")
    assert "FE-live-m6" in read_notes(flow.store(), "S1"), "agent did not save the case note"
    answer = student_turn(flow.agent(model), "FE-live-later", "S1", "What happened with my last request?",
                          confirm=lambda s: False).reply
    text = re.sub(DASHES, "-", answer)
    assert "CS412" in text and re.search(r"enrol|complete|approv", text, re.IGNORECASE), text
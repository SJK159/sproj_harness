"""Write tools for the main agent only (CLAUDE.md invariant 9).

The case is this session's thread (`thread_id = case_id`) and the student comes from the runtime
context; the model chooses neither. The rules live in harness.workflow; these are thin wrappers.
submit_case and execute_enrollment are paused by `interrupt_on` (see harness.agent.INTERRUPT_ON).
"""

from contextlib import closing
from typing import Any

from langchain.tools import ToolRuntime, tool

from harness.cases import get_case
from harness.context import HarnessContext
from harness.mock_zambeel import connect
from harness.notifications import notify
from harness.tools.common import Refused, case_id_of, run_json, student_id_of
from harness.workflow import WorkflowRefused, execute, submit


@tool
def submit_case(course_id: str, section: str, runtime: ToolRuntime[HarnessContext]) -> str:
    """Submit the student's force-enrollment request for one section (e.g. course_id="CS412", section="S1")
    and route it to the instructor. Pauses for the student's confirmation first. Call it only after the
    eligibility verdict says can_submit and the student wants to go ahead."""
    def go() -> dict[str, Any]:
        student_id, case_id = student_id_of(runtime), case_id_of(runtime)
        with closing(connect()) as conn:
            requested = f"{course_id}-{section}"
            if get_case(conn, case_id)["offering_id"] != requested:
                raise Refused(f"Case {case_id} is not for {requested}.")
            out = submit(conn, case_id, student_id)
        return {**out, "next": "Call execute_enrollment (on its own) to wait for the instructor's decision."}
    return run_json(go, WorkflowRefused)


@tool
def execute_enrollment(runtime: ToolRuntime[HarnessContext]) -> str:
    """Wait for the instructor's decision on this session's submitted case, then carry it out. It pauses
    until the instructor approves or rejects; the enrollment happens only if the approval verifies."""
    def go() -> dict[str, Any]:
        with closing(connect()) as conn:
            return execute(conn, case_id_of(runtime), student_id_of(runtime))
    return run_json(go, WorkflowRefused)


@tool
def notify_student(message: str, runtime: ToolRuntime[HarnessContext]) -> str:
    """Send the signed-in student a short notice about their case. They see it next time they open
    the assistant. Use it after a case completes, fails or is rejected."""
    def go() -> dict[str, Any]:
        student_id, case_id = student_id_of(runtime), case_id_of(runtime)
        with closing(connect()) as conn:
            has_case = conn.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,)).fetchone() is not None
            with conn:
                notify(conn, student_id, case_id if has_case else None, "AGENT_MESSAGE", message[:1000])
        return {"sent": True}
    return run_json(go)


WRITE_TOOLS = [submit_case, execute_enrollment, notify_student]

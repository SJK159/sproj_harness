"""The two human-facing clients: the student's confirmation step and the instructor's decision step.

Both drive the agent on the case's thread (`thread_id = case_id`) and answer its `interrupt_on` pauses.
They are deterministic code acting on a person's explicit choice, so they record that choice in the
database themselves before resuming the agent:

  student_turn       at a submit_case pause: open the case, ask the student, record yes/no, resume.
                     at an execute_enrollment pause: stop; the instructor decides later.
  instructor_resume  record the instructor's decision (owner check, signed token), then resume.

The runtime context is not stored in the checkpoint, so every resume passes it again.
"""

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import Command

from harness.approvals import decide
from harness.cases import get_case
from harness.context import HarnessContext
from harness.mock_zambeel import ZambeelError, connect
from harness.workflow import WorkflowRefused, open_case, record_confirmation

Confirm = Callable[[dict[str, Any]], bool]


class NotWaitingForInstructor(Exception):
    pass


@dataclass(frozen=True)
class TurnResult:
    status: str  # "answered" | "waiting_for_instructor"
    reply: str
    case_id: str


def _thread(case_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": case_id}}


def _reply(result: dict[str, Any]) -> str:
    last = result["messages"][-1] if result.get("messages") else None
    return last.text if isinstance(last, AIMessage) else ""


def _confirm_submission(case_id: str, student_id: str, args: dict[str, Any], confirm: Confirm) -> dict[str, Any]:
    with closing(connect()) as conn:
        try:
            case = open_case(conn, case_id, student_id, str(args.get("course_id", "")), str(args.get("section", "")))
        except (WorkflowRefused, ZambeelError) as refused:
            return {"type": "reject", "message": f"Request not submitted: {refused}"}
        if case["state"] != "AWAITING_CONFIRMATION":  # answered before this resume was retried
            declined = case["state"] == "CANCELLED"
            return {"type": "reject", "message": "The student declined."} if declined else {"type": "approve"}
        confirmed = bool(confirm({"case_id": case_id, "offering_id": case["offering_id"], "student_id": student_id}))
        record_confirmation(conn, case_id, student_id, confirmed)
    if confirmed:
        return {"type": "approve"}
    return {"type": "reject", "message": "The student declined at confirmation; the request was cancelled. Do not resubmit."}


def _drive(agent: Any, case_id: str, student_id: str, payload: Any, confirm: Confirm) -> TurnResult:
    context = HarnessContext(student_id=student_id)
    result = agent.invoke(payload, config=_thread(case_id), context=context)
    while result.get("__interrupt__"):
        actions = result["__interrupt__"][0].value["action_requests"]
        if [a["name"] for a in actions] == ["execute_enrollment"]:
            return TurnResult("waiting_for_instructor", _reply(result), case_id)
        decisions = []
        for action in actions:
            if action["name"] == "submit_case":
                decisions.append(_confirm_submission(case_id, student_id, action["args"], confirm))
            elif action["name"] == "execute_enrollment":
                decisions.append({"type": "reject", "message": "Call execute_enrollment on its own, after submit_case returns."})
            else:
                decisions.append({"type": "reject", "message": f"No reviewer is set up for {action['name']}."})
        result = agent.invoke(Command(resume={"decisions": decisions}), config=_thread(case_id), context=context)
    return TurnResult("answered", _reply(result), case_id)


def student_turn(agent: Any, case_id: str, student_id: str, text: str, confirm: Confirm) -> TurnResult:
    """One student message on this session's thread, answering any confirmation pause via `confirm`."""
    return _drive(agent, case_id, student_id, {"messages": [{"role": "user", "content": text}]}, confirm)


def pending_actions(agent: Any, case_id: str) -> list[str]:
    return [a["name"] for i in agent.get_state(_thread(case_id)).interrupts for a in i.value["action_requests"]]


def instructor_resume(agent: Any, case_id: str, instructor_id: str, decision: str, reason: str | None = None) -> TurnResult:
    """Record the instructor's decision (owner check, signed token), then resume the paused case thread."""
    if pending_actions(agent, case_id) != ["execute_enrollment"]:
        raise NotWaitingForInstructor(f"Case {case_id} is not waiting for an instructor decision.")
    decision = decision.upper()
    with closing(connect()) as conn:
        student_id = get_case(conn, case_id)["student_id"]
        decide(conn, case_id, instructor_id, decision, reason)  # raises NotCourseOwner: thread stays paused
    if decision == "APPROVE":
        answer = {"type": "approve"}
    else:
        answer = {"type": "reject", "message": f"Instructor {instructor_id} rejected the request. "
                                               f"Reason: {reason or 'none given'}. Tell the student; do not retry."}
    # No student is present now: a new confirmation request in this resumed run is declined.
    return _drive(agent, case_id, student_id, Command(resume={"decisions": [answer]}), confirm=lambda summary: False)

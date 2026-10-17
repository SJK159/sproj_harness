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
Ask = Callable[[str], str]
Decision = dict[str, Any]

NO_STUDENT_ANSWER = "The student is not available to answer right now; report that the request is ambiguous."


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


def prepare_confirmation(case_id: str, student_id: str, args: dict[str, Any]) -> tuple[dict[str, Any] | None, Decision | None]:
    """First half of a submission pause: open the case for confirmation (re-checks eligibility).

    Returns (case, None) when the student must now answer yes or no, or (None, decision) when the answer is
    already known: the case cannot be opened (ineligible, duplicate) or was answered before a retried resume."""
    with closing(connect()) as conn:
        try:
            case = open_case(conn, case_id, student_id, str(args.get("course_id", "")), str(args.get("section", "")))
        except (WorkflowRefused, ZambeelError) as refused:
            return None, {"type": "reject", "message": f"Request not submitted: {refused}"}
    if case["state"] != "AWAITING_CONFIRMATION":  # answered before this resume was retried
        declined = case["state"] == "CANCELLED"
        return None, {"type": "reject", "message": "The student declined."} if declined else {"type": "approve"}
    return case, None


def answer_confirmation(case_id: str, student_id: str, confirmed: bool) -> Decision:
    """Second half: record the student's yes or no, and return the decision that resumes the agent."""
    with closing(connect()) as conn:
        record_confirmation(conn, case_id, student_id, confirmed)
    if confirmed:
        return {"type": "approve"}
    return {"type": "reject", "message": "The student declined at confirmation; the request was cancelled. Do not resubmit."}


def _confirm_submission(case_id: str, student_id: str, args: dict[str, Any], confirm: Confirm) -> Decision:
    case, decided = prepare_confirmation(case_id, student_id, args)
    if decided is not None:
        return decided
    confirmed = bool(confirm({"case_id": case_id, "offering_id": case["offering_id"], "student_id": student_id}))
    return answer_confirmation(case_id, student_id, confirmed)


def unreviewed(tool_name: str) -> Decision:
    """The answer for a paused call no person reviews here (execute_enrollment alongside other calls, or a tool
    without a reviewer)."""
    if tool_name == "execute_enrollment":
        return {"type": "reject", "message": "Call execute_enrollment on its own, after submit_case returns."}
    return {"type": "reject", "message": f"No reviewer is set up for {tool_name}."}


def _drive(agent: Any, case_id: str, student_id: str, payload: Any, confirm: Confirm, ask: Ask | None = None) -> TurnResult:
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
            elif action["name"] == "ask_student":  # the eligibility checker's question: the answer is the result
                answer = ask(str(action["args"].get("question", ""))) if ask else NO_STUDENT_ANSWER
                decisions.append({"type": "respond", "message": answer or NO_STUDENT_ANSWER})
            else:
                decisions.append(unreviewed(action["name"]))
        result = agent.invoke(Command(resume={"decisions": decisions}), config=_thread(case_id), context=context)
    return TurnResult("answered", _reply(result), case_id)


def student_turn(agent: Any, case_id: str, student_id: str, text: str, confirm: Confirm, ask: Ask | None = None) -> TurnResult:
    """One student message on this session's thread. `confirm` answers submission pauses; `ask` answers the
    eligibility checker's clarifying questions (without it they get NO_STUDENT_ANSWER)."""
    return _drive(agent, case_id, student_id, {"messages": [{"role": "user", "content": text}]}, confirm, ask)


def pending_actions(agent: Any, case_id: str) -> list[str]:
    return [a["name"] for i in agent.get_state(_thread(case_id)).interrupts for a in i.value["action_requests"]]


def record_instructor_decision(agent: Any, case_id: str, instructor_id: str, decision: str,
                               reason: str | None = None) -> tuple[str, Decision]:
    """Record the instructor's decision (owner check, signed token). Returns (the case's student, the decision
    that resumes the paused execute_enrollment)."""
    if pending_actions(agent, case_id) != ["execute_enrollment"]:
        raise NotWaitingForInstructor(f"Case {case_id} is not waiting for an instructor decision.")
    decision = decision.upper()
    with closing(connect()) as conn:
        student_id = get_case(conn, case_id)["student_id"]
        decide(conn, case_id, instructor_id, decision, reason)  # raises NotCourseOwner: thread stays paused
    if decision == "APPROVE":
        return student_id, {"type": "approve"}
    return student_id, {"type": "reject", "message": f"Instructor {instructor_id} rejected the request. "
                                                     f"Reason: {reason or 'none given'}. Tell the student; do not retry."}


def instructor_resume(agent: Any, case_id: str, instructor_id: str, decision: str, reason: str | None = None) -> TurnResult:
    """Record the instructor's decision (owner check, signed token), then resume the paused case thread."""
    student_id, answer = record_instructor_decision(agent, case_id, instructor_id, decision, reason)
    # No student is present now: a new confirmation request in this resumed run is declined.
    return _drive(agent, case_id, student_id, Command(resume={"decisions": [answer]}), confirm=lambda summary: False)

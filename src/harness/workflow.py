"""Deterministic force-enrollment case workflow. The LLM decides when to call these; never whether they may.

Each step is one transaction that writes its audit rows through `cases.transition`, and each is
safe to call again (a resumed run may repeat a tool call):

  open_case            student client, at the submit_case pause   -> AWAITING_CONFIRMATION
  record_confirmation  student client                              -> SUBMITTED | CANCELLED
  submit               submit_case tool                            -> AWAITING_APPROVAL (+ instructor notice)
  execute              execute_enrollment tool                     -> EXECUTING -> COMPLETED | FAILED

Instructor decisions (and token minting) live in harness.approvals; nothing here can mint a token.
"""

import sqlite3
from typing import Any

from harness.approvals import TokenRefused, verify_and_consume
from harness.audit import write_event
from harness.cases import UnknownCase, create_case, get_case, transition
from harness.mock_zambeel import (
    Eligibility,
    ZambeelError,
    check_fe_eligibility,
    enroll,
    get_section,
)
from harness.mock_zambeel.policy import RULE_LABELS
from harness.notifications import notify

OPEN_STATES = ("DRAFT", "AWAITING_CONFIRMATION", "SUBMITTED", "AWAITING_APPROVAL", "APPROVED", "EXECUTING")
EXECUTOR = "execute_enrollment"

# Student-side rules re-checked at execution: they can change between submission and approval (e.g. another
# approved case added credits, scenario A8b). Seat / FE codes are not: FE_CAP_REACHED is enroll's own cap check,
# and FE_NOT_ACCEPTED no longer applies once the instructor has approved this request.
EXECUTION_RECHECK = frozenset({
    "PREREQ_MISSING", "PREREQ_IN_PROGRESS", "CLASH", "CREDIT_LIMIT", "PROBATION",
    "YEAR_RESTRICTION", "CGPA_BELOW_MIN", "ALREADY_ENROLLED", "NOT_OFFERED",
})


class WorkflowRefused(Exception):
    code = "REFUSED"


class NotEligible(WorkflowRefused):
    code = "NOT_ELIGIBLE"

    def __init__(self, eligibility: Eligibility) -> None:
        self.eligibility = eligibility
        super().__init__(describe_ineligibility(eligibility))


class DuplicateCase(WorkflowRefused):
    code = "DUPLICATE"

    def __init__(self, existing_case_id: str, state: str) -> None:
        self.existing_case_id = existing_case_id
        super().__init__(f"You already have an open request for this course: case {existing_case_id} ({state}).")


class WrongState(WorkflowRefused):
    code = "WRONG_STATE"


class NotYourCase(WorkflowRefused):
    code = "NOT_YOUR_CASE"


def describe_ineligibility(e: Eligibility) -> str:
    codes = list(e.blocking) or (["SEATS_AVAILABLE"] if not e.fe_needed else [])
    parts = [f"{c} ({RULE_LABELS[c]}): {e.reasons[c]}" for c in codes]
    return f"Not submitted for {e.course_id}-{e.section}. " + " ".join(parts)


def _own_case(conn: sqlite3.Connection, case_id: str, student_id: str) -> dict[str, Any]:
    try:
        case = get_case(conn, case_id)
    except UnknownCase:
        raise WrongState(f"No request has been opened in this session (case {case_id}).") from None
    if case["student_id"] != student_id:
        raise NotYourCase(f"Case {case_id} belongs to another student.")
    return case


def open_case(conn: sqlite3.Connection, case_id: str, student_id: str, course_id: str, section: str) -> dict[str, Any]:
    """Create the case for this session's request, after re-checking eligibility. Returns the case."""
    existing = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if existing is not None:
        if existing["student_id"] != student_id:
            raise NotYourCase(f"Case {case_id} belongs to another student.")
        if existing["offering_id"] == f"{course_id}-{section}":
            return dict(existing)  # client retry: same request, same case
        raise WrongState(f"This session already has case {case_id} for {existing['offering_id']}. "
                         "Start a new session for another request.")

    dup = conn.execute(
        f"""SELECT c.case_id, c.state FROM cases c JOIN offerings o ON o.offering_id = c.offering_id
            WHERE c.student_id = ? AND o.course_id = ? AND c.state IN ({",".join("?" * len(OPEN_STATES))})""",
        (student_id, course_id, *OPEN_STATES),
    ).fetchone()
    if dup is not None:
        raise DuplicateCase(dup["case_id"], dup["state"])

    eligibility = check_fe_eligibility(conn, student_id, course_id, section)
    if not eligibility.can_submit:
        raise NotEligible(eligibility)
    with conn:
        create_case(conn, case_id, student_id, eligibility.offering_id, actor=student_id)
        transition(conn, case_id, "AWAITING_CONFIRMATION", "system", "REQUEST_CONFIRMATION",
                   {"advisory": list(eligibility.advisory)})
    return get_case(conn, case_id)


def record_confirmation(conn: sqlite3.Connection, case_id: str, student_id: str, confirmed: bool) -> str:
    """The student's yes or no at the confirmation prompt. Returns the new state."""
    case = _own_case(conn, case_id, student_id)
    target = "SUBMITTED" if confirmed else "CANCELLED"
    if case["state"] != "AWAITING_CONFIRMATION":
        if (confirmed and case["state"] not in ("DRAFT", "CANCELLED")) or (not confirmed and case["state"] == "CANCELLED"):
            return case["state"]  # already recorded
        raise WrongState(f"Case {case_id} is {case['state']}; there is nothing to confirm.")
    with conn:
        transition(conn, case_id, target, student_id, "CONFIRM" if confirmed else "DECLINE")
    return target


def submit(conn: sqlite3.Connection, case_id: str, student_id: str) -> dict[str, Any]:
    """Route a confirmed case to the section's instructor. Re-runs eligibility first (invariant 10)."""
    case = _own_case(conn, case_id, student_id)
    section = get_section(conn, case["offering_id"])
    result = {"case_id": case_id, "offering_id": case["offering_id"], "instructor_id": section["instructor_id"]}
    if case["state"] in ("AWAITING_APPROVAL", "APPROVED", "EXECUTING", "COMPLETED", "REJECTED", "FAILED"):
        return {**result, "state": case["state"]}  # already submitted; no second notice
    if case["state"] != "SUBMITTED":
        raise WrongState(f"Case {case_id} is {case['state']}; the student has not confirmed it.")

    eligibility = check_fe_eligibility(conn, student_id, section["course_id"], section["section"])
    if not eligibility.can_submit:
        with conn:
            transition(conn, case_id, "CANCELLED", "system", "INELIGIBLE_AT_SUBMIT",
                       {"blocking": list(eligibility.blocking)})
        raise NotEligible(eligibility)
    with conn:
        transition(conn, case_id, "AWAITING_APPROVAL", "system", "ROUTE_TO_INSTRUCTOR",
                   {"instructor_id": section["instructor_id"]})
        notify(conn, section["instructor_id"], case_id, "APPROVAL_REQUESTED",
               f"Student {student_id} requests force enrollment in {case['offering_id']} (case {case_id}). "
               f"Approve or reject: scripts/approve.py --case {case_id} --instructor {section['instructor_id']} "
               "--decision approve|reject")
    return {**result, "state": "AWAITING_APPROVAL"}


def _fail(conn: sqlite3.Connection, case: dict[str, Any], action: str, reason: str, flag: str | None = None) -> dict[str, Any]:
    with conn:
        if flag is not None:
            conn.execute("UPDATE cases SET flag = ? WHERE case_id = ?", (flag, case["case_id"]))
        transition(conn, case["case_id"], "FAILED", EXECUTOR, action, {"reason": reason})
        notify(conn, case["student_id"], case["case_id"], "FAILED",
               f"Your force-enrollment request {case['case_id']} for {case['offering_id']} could not be completed: "
               f"{reason}" + (" It has been flagged for review." if flag else ""))
    return {"case_id": case["case_id"], "state": "FAILED", "reason": reason, "flagged": flag is not None}


def _enroll_and_finish(conn: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    already = conn.execute("SELECT 1 FROM enrollments WHERE idempotency_key = ?", (case["case_id"],)).fetchone()
    if already is None:  # a crash retry whose enrollment exists skips the re-check and just completes
        section = get_section(conn, case["offering_id"])
        now = check_fe_eligibility(conn, case["student_id"], section["course_id"], section["section"])
        failing = [c for c in now.blocking if c in EXECUTION_RECHECK]
        if failing:
            reasons = "; ".join(f"{c} ({RULE_LABELS[c]}): {now.reasons[c]}" for c in failing)
            return _fail(conn, case, "NO_LONGER_ELIGIBLE", f"no longer eligible at execution: {reasons}")
    try:
        r = enroll(conn, case["student_id"], case["offering_id"], idempotency_key=case["case_id"])
    except ZambeelError as exc:  # FeCapReached included: the cap filled after approval (scenario A5)
        return _fail(conn, case, "ENROLL_FAILED", str(exc))
    with conn:
        transition(conn, case["case_id"], "COMPLETED", EXECUTOR, "ENROLLED",
                   {"enrollment_id": r.enrollment_id, "kind": r.kind})
        notify(conn, case["student_id"], case["case_id"], "COMPLETED",
               f"You are enrolled in {case['offering_id']} ({r.kind.lower()} enrollment). Case {case['case_id']} is complete.")
    return {"case_id": case["case_id"], "state": "COMPLETED", "enrollment_id": r.enrollment_id, "kind": r.kind}


def execute(conn: sqlite3.Connection, case_id: str, student_id: str) -> dict[str, Any]:
    """Enroll the student only behind a verified, unused approval token for this case (invariant 1)."""
    case = _own_case(conn, case_id, student_id)
    state = case["state"]
    if state == "COMPLETED":
        row = conn.execute("SELECT enrollment_id, kind FROM enrollments WHERE idempotency_key = ?", (case_id,)).fetchone()
        return {"case_id": case_id, "state": "COMPLETED", "enrollment_id": row["enrollment_id"], "kind": row["kind"]}
    if state == "FAILED":
        return {"case_id": case_id, "state": "FAILED", "reason": case["flag"] or "execution failed earlier"}
    if state == "EXECUTING":  # token was consumed; the process stopped before enrolling
        return _enroll_and_finish(conn, case)
    if state != "APPROVED":
        with conn:
            write_event(conn, case_id, EXECUTOR, "EXECUTE_REFUSED", state, state,
                        {"reason": "no instructor approval recorded"})
        raise WrongState(f"Case {case_id} is {state}; it can only be executed after the instructor approves it.")

    row = conn.execute(
        "SELECT token FROM approvals WHERE case_id = ? AND decision = 'APPROVE' ORDER BY approval_id DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    try:
        verify_and_consume(
            conn, row["token"] if row else "", case_id, actor=EXECUTOR,
            on_consumed=lambda c: transition(c, case_id, "EXECUTING", EXECUTOR, "EXECUTE"),
        )
    except TokenRefused as refused:
        return _fail(conn, case, "EXECUTE_BLOCKED", f"the approval could not be verified ({refused.code}).",
                     flag=f"TOKEN_{refused.code}: {refused}")
    return _enroll_and_finish(conn, get_case(conn, case_id))

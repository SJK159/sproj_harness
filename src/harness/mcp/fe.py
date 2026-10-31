"""Force-enrollment MCP service. Reuses all deterministic workflow/approval gates."""
from contextlib import closing
from functools import wraps, partial
import anyio

from mcp.server.fastmcp import FastMCP
from mcp.types import Completion

from harness.academic import using_academic
from harness.approvals import decide
from harness.cases import get_case
from harness.mock_zambeel import connect
from harness.mcp.client import RemoteAcademic
from harness.mcp.security import caller
from harness.notifications import notify
from harness import workflow


def domain_result(fn):
    """Preserve domain error types over MCP, without sending tracebacks or tokens."""
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        try:
            # FastMCP executes sync callables on its event loop. Run the existing
            # sync workflow in a worker; its MCP client owns a separate loop.
            return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
        except Exception as exc:
            return {"error": str(exc), "error_type": type(exc).__name__}
    return wrapped


def create_server():
    server = FastMCP("fe-mcp", host="127.0.0.1", port=8101, stateless_http=True, json_response=True)

    def own(conn, case_id):
        person = caller()
        case = get_case(conn, case_id)
        if person.role == "student":
            if case["student_id"] != person.actor:
                raise PermissionError("Case belongs to another student.")
        else:
            section = RemoteAcademic(case["student_id"]).get_section(case["offering_id"])
            if section["instructor_id"] != person.actor:
                raise PermissionError("Case belongs to another instructor.")
        return case

    @server.tool()
    @domain_result
    def prepare_case(case_id: str, course_id: str, section: str) -> dict:
        """Prepare an eligible case, awaiting explicit student confirmation."""
        person = caller("student")
        with closing(connect()) as conn, using_academic(RemoteAcademic(person.actor)):
            return workflow.open_case(conn, case_id, person.actor, course_id, section)

    @server.tool()
    @domain_result
    def confirm_case(case_id: str, confirmed: bool) -> dict:
        """Record a student's explicit confirmation/decline. Client operation, not an agent tool."""
        person = caller("student")
        with closing(connect()) as conn:
            return {"case_id": case_id, "state": workflow.record_confirmation(conn, case_id, person.actor, confirmed)}

    @server.tool()
    @domain_result
    def submit_case(case_id: str, course_id: str, section: str) -> dict:
        """Route a confirmed case to its instructor after a fresh eligibility check."""
        person = caller("student")
        with closing(connect()) as conn, using_academic(RemoteAcademic(person.actor)):
            if own(conn, case_id)["offering_id"] != f"{course_id}-{section}":
                raise PermissionError("Case does not match requested section.")
            return workflow.submit(conn, case_id, person.actor)

    @server.tool()
    @domain_result
    def execute_enrollment(case_id: str) -> dict:
        """Verify and consume the existing signed approval, recheck rules, then enroll exactly once."""
        person = caller("student")
        with closing(connect()) as conn, using_academic(RemoteAcademic(person.actor)):
            return workflow.execute(conn, case_id, person.actor)

    @server.tool()
    @domain_result
    def decide_case(case_id: str, decision: str, reason: str | None = None) -> dict:
        """Instructor client only: record an owner decision. The signed token never leaves this service."""
        person = caller("instructor")
        with closing(connect()) as conn:
            case = get_case(conn, case_id)
            with using_academic(RemoteAcademic(case["student_id"])):
                decide(conn, case_id, person.actor, decision.upper(), reason)
            return {"case_id": case_id, "state": get_case(conn, case_id)["state"]}

    @server.tool()
    @domain_result
    def get_my_cases() -> dict:
        """List the demo student's own cases."""
        person = caller("student")
        with closing(connect()) as conn:
            return {"cases": [dict(r) for r in conn.execute(
                "SELECT case_id, offering_id, state, next_action, updated_at FROM cases WHERE student_id = ? ORDER BY created_at",
                (person.actor,))]}

    @server.tool()
    @domain_result
    def get_case_status(case_id: str) -> dict:
        """Read an owned case and its audit history. Approval tokens are not returned."""
        with closing(connect()) as conn:
            case = own(conn, case_id)
            return {"case": case, "audit": [dict(r) for r in conn.execute(
                "SELECT * FROM audit_events WHERE case_id = ? ORDER BY event_id", (case_id,))]}

    @server.tool()
    @domain_result
    def notify_student(case_id: str, message: str) -> dict:
        """Add a bounded notice for the demo student's own case."""
        person = caller("student")
        with closing(connect()) as conn:
            own(conn, case_id)
            with conn:
                notify(conn, person.actor, case_id, "AGENT_MESSAGE", message[:1000])
        return {"sent": True}

    @server.prompt()
    def force_enroll(school: str, course: str, section: str) -> str:
        """Prepare a force-enrollment request; confirmation and instructor approval are still required."""
        return (f"Please check eligibility and submit a force-enrollment request for {course} section {section} "
                f"in {school}. Require my confirmation and the section instructor's approval.")

    @server.completion()
    async def complete(ref, argument, context):
        # Prompt completion is read-only. Catalogue choices are real mock data, not model suggestions.
        from harness.mcp.client import acall
        from mcp.types import PromptReference
        if not isinstance(ref, PromptReference) or ref.name != "force_enroll":
            return None
        person = caller("student")
        data = await acall("zambeel", "list_offerings", actor=person.actor)
        rows = data["sections"]
        selected = context.arguments if context and context.arguments else {}
        if argument.name == "school":
            values = {r["department"] for r in rows}
        elif argument.name == "course":
            values = {r["course_id"] for r in rows if not selected.get("school") or r["department"] == selected["school"]}
        elif argument.name == "section":
            values = {r["section"] for r in rows if r["course_id"] == selected.get("course")}
        else:
            values = set()
        values = sorted(v for v in values if v.lower().startswith(argument.value.lower()))
        return Completion(values=values[:100], total=len(values), hasMore=len(values) > 100)

    return server

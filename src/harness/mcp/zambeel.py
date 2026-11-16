"""Academic-system MCP server over the existing mock."""
from contextlib import closing
from dataclasses import asdict
import json
from types import SimpleNamespace

from mcp.server.fastmcp import FastMCP

from harness import academic
from harness.mcp.entra import mode
from harness.mock_zambeel import get_student_profile, ZambeelError
from harness.mock_zambeel import connect, check_fe_eligibility as eligibility, enroll as mock_enroll, get_section as section_row
from harness.mcp.security import caller, require_service
from harness.tools import read_tools


def create_server():
    server = FastMCP("zambeel-mcp", host="127.0.0.1", port=8102, stateless_http=True, json_response=True)

    def read(tool, **args):
        person = caller("student")
        runtime = SimpleNamespace(context=SimpleNamespace(student_id=person.actor, role="student"))
        result = json.loads(tool.func(runtime=runtime, **args))
        if "error" in result:
            raise ValueError(result["error"])
        return result

    @server.tool()
    def get_my_profile() -> dict:
        """Read the demo caller's academic profile."""
        return read(read_tools.get_my_profile)

    @server.tool()
    def get_my_enrollments() -> dict:
        """Read the demo caller's current enrollments."""
        return {"enrollments": read(read_tools.get_my_profile)["enrollments"]}

    @server.tool()
    def list_offerings() -> dict:
        """List the current-term academic catalogue."""
        return read(read_tools.list_offerings)

    @server.tool()
    def list_sections(course_id: str) -> dict:
        """List sections, seats, and restrictions for a course."""
        return read(read_tools.list_sections, course_id=course_id)

    @server.tool()
    def check_my_eligibility(course_id: str, section: str) -> dict:
        """Check the caller's eligibility, returning every reason and rule label."""
        return read(read_tools.check_my_eligibility, course_id=course_id, section=section)

    @server.tool()
    def scan_my_fe_options() -> dict:
        """Check every offered section for the caller."""
        return read(read_tools.scan_my_fe_options)

    @server.tool()
    def get_student_record(subject_id: str) -> dict:
        """FE-only academic profile; never a model-visible student tool."""
        require_service()
        with closing(connect()) as conn:
            return get_student_profile(conn, subject_id)

    @server.tool()
    def academic_catalogue() -> dict:
        """FE-only catalogue for prompt argument completion."""
        require_service()
        # Catalogue contains no student records. Reuse its existing projection
        # without inventing a student identity for the service principal.
        with closing(connect()) as conn:
            rows = []
            for course in read_tools._term_offerings(conn):
                section = read_tools._section_row(conn, course["offering_id"])
                rows.append({**dict(course), **section, "full": section["available"] == 0})
        return {"term": read_tools.CURRENT_TERM, "sections": rows}

    @server.tool()
    def get_section(offering_id: str) -> dict:
        """Read section metadata (FE service contract)."""
        require_service()
        with closing(connect()) as conn:
            return section_row(conn, offering_id)

    @server.tool()
    def course_details(course_id: str) -> dict:
        """Read credits and prerequisites (FE service contract)."""
        require_service()
        with closing(connect()) as conn:
            if conn.execute("SELECT 1 FROM courses WHERE course_id = ?", (course_id,)).fetchone() is None:
                raise ValueError("Unknown course")
            return academic.course_details(conn, course_id)

    @server.tool()
    def eligibility_record(course_id: str, section: str, subject_id: str | None = None) -> dict:
        """Return the deterministic eligibility record for the FE service."""
        require_service()
        actor = subject_id if mode() == "entra" else caller("student").actor
        if not actor:
            raise PermissionError("FE subject required")
        with closing(connect()) as conn:
            return asdict(eligibility(conn, actor, course_id, section))

    def own_case(conn, case_id):
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None or (mode() != "entra" and row["student_id"] != caller("student").actor):
            raise PermissionError("Case unavailable for this student.")
        return row

    @server.tool()
    def enrollment_result(case_id: str) -> dict:
        """Look up an enrollment by its case key (FE service only)."""
        require_service()
        with closing(connect()) as conn:
            own_case(conn, case_id)
            return {"enrollment": academic.enrollment_result(conn, case_id)}

    @server.tool()
    def enroll(offering_id: str, case_id: str) -> dict:
        """Execute a bound case after FE consumed its approval. Never a student-agent tool."""
        require_service("Enrollment.ExecuteApproved")
        with closing(connect()) as conn:
            case = own_case(conn, case_id)
            if case["offering_id"] != offering_id or case["state"] not in ("EXECUTING", "COMPLETED"):
                raise PermissionError("Enrollment requires the bound case in EXECUTING or COMPLETED.")
            approval = conn.execute("SELECT 1 FROM approvals a JOIN offerings o ON o.offering_id = ? "
                "WHERE a.case_id = ? AND a.decision = 'APPROVE' AND a.consumed_at IS NOT NULL "
                "AND a.instructor_id = o.instructor_id", (offering_id, case_id)).fetchone()
            consumed = conn.execute("SELECT 1 FROM audit_events WHERE case_id = ? AND action = 'TOKEN_CONSUMED'",
                                    (case_id,)).fetchone()
            if not approval or not consumed:
                raise PermissionError("No consumed owner approval for this enrollment.")
            try:
                return asdict(mock_enroll(conn, case["student_id"], offering_id, case_id))
            except ZambeelError as exc:
                if mode() != "entra":
                    raise
                return {"error": "Academic operation refused", "error_type": type(exc).__name__}

    return server

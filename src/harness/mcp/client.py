"""Small MCP client shared by the FE service and opt-in agent tool wrappers.

Credentials and actor IDs are set by application code, not tool arguments. Each
call owns its session; retries of writes use the existing case idempotency key.
No automatic retry of a possibly completed write is attempted here.
"""
import asyncio
import json
import os
from urllib.parse import urlsplit
import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from harness.mock_zambeel import Eligibility, EnrollResult, ZambeelError


class RemoteError(ZambeelError):
    pass


def enabled():
    from harness.mcp.security import principal
    return principal.get() is None and os.environ.get("HARNESS_USE_MCP", "").lower() in ("1", "true")


async def acall(server, name, arguments=None, *, actor, role="student", service=False):
    from harness.mcp.security import service_secret
    url = os.environ.get(f"HARNESS_{server.upper()}_MCP_URL", f"http://127.0.0.1:{8101 if server == 'fe' else 8102}/mcp")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username:
        raise ValueError("Local demo MCP endpoints must use HTTP on a loopback host.")
    headers = {"X-Demo-Actor": actor, "X-Demo-Role": role}
    if service:
        headers["X-FE-Service-Key"] = service_secret()
    async with httpx.AsyncClient(headers=headers, timeout=30, trust_env=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})
    # Raise domain errors outside the transport task groups, preserving their type
    # instead of wrapping a normal refusal in an AnyIO ExceptionGroup.
    if result.isError:
        raise RemoteError(" ".join(c.text for c in result.content if c.type == "text"))
    value = result.structuredContent
    if value is None:
        value = json.loads("".join(c.text for c in result.content if c.type == "text"))
    if isinstance(value, dict) and value.get("error_type"):
        from harness.approvals import NotCourseOwner
        from harness.cases import InvalidTransition
        from harness.workflow import WrongState, NotYourCase
        errors = {c.__name__: c for c in (NotCourseOwner, InvalidTransition, WrongState, NotYourCase)}
        raise errors.get(value["error_type"], RemoteError)(value["error"])
    return value


def call(server, name, arguments=None, **identity):
    return asyncio.run(acall(server, name, arguments, **identity))


class RemoteAcademic:
    def __init__(self, actor):
        self.actor = actor

    def _call(self, name, args=None, actor=None):
        return call("zambeel", name, args, actor=actor or self.actor, service=True)

    def get_section(self, offering_id):
        return self._call("get_section", {"offering_id": offering_id})

    def get_student_profile(self, student_id):
        return self._call("get_my_profile", actor=student_id)

    def check_fe_eligibility(self, student_id, course_id, section):
        result = self._call("eligibility_record", {"course_id": course_id, "section": section}, actor=student_id)
        return Eligibility(**result)

    def course_details(self, course_id):
        return self._call("course_details", {"course_id": course_id})

    def enrollment_result(self, case_id):
        return self._call("enrollment_result", {"case_id": case_id}).get("enrollment")

    def enroll(self, student_id, offering_id, idempotency_key):
        result = self._call("enroll", {"offering_id": offering_id, "case_id": idempotency_key}, actor=student_id)
        return EnrollResult(**result)

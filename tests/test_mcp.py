"""Real MCP protocol tests over two loopback processes; no model or external network."""
import asyncio
from contextlib import AsyncExitStack
from datetime import UTC, datetime
import os
import socket
import subprocess
import sys
import time

import pytest
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PromptReference

from harness.mcp.client import call, RemoteError
from harness.approvals import NotCourseOwner
from harness.integrity import audit_gaps, unauthorized_writes
from harness.mock_zambeel import connect, init_schema, seed


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def servers(tmp_path, monkeypatch):
    dbfile = tmp_path / "harness.db"
    with connect(dbfile) as conn:
        init_schema(conn)
        seed(conn)
    monkeypatch.setenv("HARNESS_DB", str(dbfile))
    monkeypatch.setenv("HARNESS_STORE", str(tmp_path / "store.db"))
    monkeypatch.setenv("APPROVAL_SECRET", "test-approval-" + "a" * 40)
    monkeypatch.setenv("HARNESS_MCP_SERVICE_SECRET", "test-service-" + "b" * 40)
    monkeypatch.delenv("HARNESS_USE_MCP", raising=False)
    children, logs = [], []
    try:
        for name in ("zambeel", "fe"):
            port = free_port()
            monkeypatch.setenv(f"HARNESS_{name.upper()}_MCP_URL", f"http://127.0.0.1:{port}/mcp")
            log = (tmp_path / f"{name}.log").open("w+", encoding="utf-8")
            logs.append(log)
            process = subprocess.Popen([sys.executable, "-m", "harness.mcp", name, "--port", str(port)],
                env=dict(os.environ), stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            children.append(process)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                log.seek(0)
                pytest.fail("MCP server did not start: " + log.read())
        yield dbfile
    finally:
        for process in reversed(children):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


def fe(name, args=None, actor="S1", role="student"):
    return call("fe", name, args, actor=actor, role=role)


def prepare(case="FE-mcp", student="S1", course="CS412"):
    return fe("prepare_case", {"case_id": case, "course_id": course, "section": "S1"}, actor=student)


def submit(case="FE-mcp", student="S1", course="CS412"):
    prepare(case, student, course)
    fe("confirm_case", {"case_id": case, "confirmed": True}, actor=student)
    return fe("submit_case", {"case_id": case, "course_id": course, "section": "S1"}, actor=student)


def approve(case="FE-mcp", instructor="I1", decision="approve"):
    return fe("decide_case", {"case_id": case, "decision": decision, "reason": "Room capacity"}, actor=instructor, role="instructor")


def test_two_servers_discover_tools_prompts_completions_and_identity(servers):
    async def inspect():
        for server, expected in [("zambeel", {"get_my_profile", "check_my_eligibility", "enroll"}),
                                 ("fe", {"prepare_case", "confirm_case", "submit_case", "decide_case", "execute_enrollment"})]:
            async with AsyncExitStack() as stack:
                http = await stack.enter_async_context(httpx.AsyncClient(
                    headers={"X-Demo-Actor": "S1", "X-Demo-Role": "student"}, trust_env=False))
                read, write, _ = await stack.enter_async_context(streamable_http_client(
                    os.environ[f"HARNESS_{server.upper()}_MCP_URL"], http_client=http))
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert expected <= {t.name for t in tools}
                    assert all("student_id" not in t.inputSchema.get("properties", {}) for t in tools)
                    if server == "fe":
                        assert [p.name for p in (await session.list_prompts()).prompts] == ["force_enroll"]
                        prompt = await session.get_prompt("force_enroll", {"school": "CS", "course": "CS412", "section": "S1"})
                        assert "instructor" in prompt.messages[0].content.text
                        result = await session.complete(PromptReference(type="ref/prompt", name="force_enroll"),
                            {"name": "course", "value": "CS4"}, context_arguments={"school": "CS"})
                        assert "CS412" in result.completion.values
    asyncio.run(inspect())
    assert call("zambeel", "get_my_profile", actor="S2")["student_id"] == "S2"
    assert call("zambeel", "check_my_eligibility", {"course_id": "CS412", "section": "S1"}, actor="S2")["can_submit"] is False


def test_approval_required_wrong_owner_refused_then_completes_once(servers):
    from harness.workflow import WrongState
    prepare()
    with pytest.raises(WrongState):
        fe("submit_case", {"case_id": "FE-mcp", "course_id": "CS412", "section": "S1"})
    fe("confirm_case", {"case_id": "FE-mcp", "confirmed": True})
    fe("submit_case", {"case_id": "FE-mcp", "course_id": "CS412", "section": "S1"})
    with pytest.raises(WrongState):
        fe("execute_enrollment", {"case_id": "FE-mcp"})
    with pytest.raises(NotCourseOwner):
        approve(instructor="I2")
    with pytest.raises(RemoteError):
        fe("decide_case", {"case_id": "FE-mcp", "decision": "approve"})
    result = approve()
    assert result == {"case_id": "FE-mcp", "state": "APPROVED"}  # no signed token in response
    first = fe("execute_enrollment", {"case_id": "FE-mcp"})
    assert first["state"] == "COMPLETED"
    assert fe("execute_enrollment", {"case_id": "FE-mcp"})["enrollment_id"] == first["enrollment_id"]
    with connect(servers) as conn:
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []


def test_raw_enrollment_cannot_bypass_gate_even_with_service_key(servers):
    submit()
    for service in (False, True):
        with pytest.raises(RemoteError):
            call("zambeel", "enroll", {"offering_id": "CS412-S1", "case_id": "FE-mcp"}, actor="S1", service=service)
    approve()
    # Approval alone is insufficient: the FE execution gate has not consumed it.
    with pytest.raises(RemoteError):
        call("zambeel", "enroll", {"offering_id": "CS412-S1", "case_id": "FE-mcp"}, actor="S1", service=True)


@pytest.mark.parametrize("how", ["expired", "tampered", "wrong-case", "reused"])
def test_bad_approval_over_mcp_never_enrolls(servers, how):
    from harness.approvals import decide, verify_and_consume
    submit()
    with connect(servers) as conn:
        if how == "expired":
            decide(conn, "FE-mcp", "I1", "APPROVE", now=datetime(2026, 1, 1, tzinfo=UTC))
        else:
            token = decide(conn, "FE-mcp", "I1", "APPROVE")
            if how == "tampered":
                conn.execute("UPDATE approvals SET token = ? WHERE case_id = ?", (token + "x", "FE-mcp"))
                conn.commit()
            elif how == "wrong-case":
                from harness.approvals import mint_token
                other, _, _ = mint_token("FE-other", "I1")
                conn.execute("UPDATE approvals SET token = ? WHERE case_id = ?", (other, "FE-mcp"))
                conn.commit()
            else:
                verify_and_consume(conn, token, "FE-mcp")
    result = fe("execute_enrollment", {"case_id": "FE-mcp"})
    assert result["state"] == "FAILED" and result["flagged"]
    with connect(servers) as conn:
        assert conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key = 'FE-mcp'").fetchone()[0] == 0
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []


def test_student_isolation_rejection_and_decline(servers):
    submit()
    with pytest.raises(RemoteError):
        fe("get_case_status", {"case_id": "FE-mcp"}, actor="S2")
    assert fe("get_my_cases", actor="S2") == {"cases": []}
    assert approve(decision="reject")["state"] == "REJECTED"
    prepare("FE-cancel", "S2", "CS360")
    assert fe("confirm_case", {"case_id": "FE-cancel", "confirmed": False}, actor="S2")["state"] == "CANCELLED"
    with connect(servers) as conn:
        assert conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key IS NOT NULL").fetchone()[0] == 0


def test_missing_identity_and_bad_service_key_are_refused(servers):
    import httpx
    url = os.environ["HARNESS_ZAMBEEL_MCP_URL"]
    for headers in ({}, {"X-Demo-Actor": "S1", "X-Demo-Role": "student", "X-FE-Service-Key": "wrong"}):
        assert httpx.post(url, headers=headers, json={}).status_code == 401


def test_demo_client_refuses_remote_endpoint(monkeypatch):
    monkeypatch.setenv("HARNESS_ZAMBEEL_MCP_URL", "http://example.com/mcp")
    with pytest.raises(ValueError, match="loopback"):
        call("zambeel", "get_my_profile", actor="S1")


def test_lost_enrollment_response_is_recovered_without_second_write(servers):
    from harness.academic import using_academic
    from harness.mcp.client import RemoteAcademic
    from harness import workflow
    submit()
    approve()
    class LostResponse(RemoteAcademic):
        def enroll(self, student_id, offering_id, idempotency_key):
            super().enroll(student_id, offering_id, idempotency_key)
            raise ConnectionError("simulated lost response after backend commit")
    with connect(servers) as conn, using_academic(LostResponse("S1")):
        with pytest.raises(ConnectionError):
            workflow.execute(conn, "FE-mcp", "S1")
    assert fe("execute_enrollment", {"case_id": "FE-mcp"})["state"] == "COMPLETED"
    with connect(servers) as conn:
        assert conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key = 'FE-mcp'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE case_id = 'FE-mcp' AND action = 'TOKEN_CONSUMED'").fetchone()[0] == 1
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []


def test_remote_execution_rechecks_fe_cap(servers):
    # Two approved students competing for the one CS360 force-enrollment slot.
    for cid, student in (("FE-cap-a", "S1"), ("FE-cap-b", "S2")):
        submit(cid, student, "CS360")
        approve(cid)
    assert fe("execute_enrollment", {"case_id": "FE-cap-a"})["state"] == "COMPLETED"
    assert fe("execute_enrollment", {"case_id": "FE-cap-b"}, actor="S2")["state"] == "FAILED"
    with connect(servers) as conn:
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []


def test_remote_execution_rechecks_student_credit_rules(servers):
    # Both pass at 15 credits; the second approval cannot take the student to 21.
    submit("FE-credit-a", "S1", "CS412")
    submit("FE-credit-b", "S1", "CS582")
    approve("FE-credit-a")
    approve("FE-credit-b", instructor="I3")
    assert fe("execute_enrollment", {"case_id": "FE-credit-a"})["state"] == "COMPLETED"
    result = fe("execute_enrollment", {"case_id": "FE-credit-b"})
    assert result["state"] == "FAILED" and "CREDIT_LIMIT" in result["reason"]
    with connect(servers) as conn:
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []


def test_agent_uses_both_mcp_servers_and_resumes_after_restart(servers, monkeypatch, tmp_path):
    from fakes import FakeToolCallingModel, call as tool_call
    from langchain_core.messages import AIMessage
    from harness.agent import build_agent
    from harness.clients import student_turn, instructor_resume
    from harness.persistence import open_checkpointer, open_store
    monkeypatch.setenv("HARNESS_USE_MCP", "true")
    model = FakeToolCallingModel(messages=iter([
        tool_call("get_my_profile"), tool_call("submit_case", course_id="CS412", section="S1"),
        tool_call("execute_enrollment"), tool_call("save_case_note"), AIMessage(content="Enrolled.")]))
    def agent():
        return build_agent(model=model, checkpointer=open_checkpointer(tmp_path / "checkpoints.db"), store=open_store())
    turn = student_turn(agent(), "FE-agent-mcp", "S1", "Submit CS412 S1", confirm=lambda summary: True)
    assert turn.status == "waiting_for_instructor"
    assert instructor_resume(agent(), "FE-agent-mcp", "I1", "approve").status == "answered"
    with connect(servers) as conn:
        assert conn.execute("SELECT state FROM cases WHERE case_id = 'FE-agent-mcp'").fetchone()[0] == "COMPLETED"
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []

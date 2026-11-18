"""Force enrollment across BFF -> graph -> real authenticated HTTP MCP -> worker.

Only Microsoft sign-in/token issuance and the language model are synthetic. The
production validators, HTTP transports, tools, workflow, databases, leases and
checkpoint/memory reconciliation are exercised. No Sakai dependency is involved.
"""
import asyncio
import json
import time
from contextlib import closing
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api_helpers import events, scripted, session
from fakes import FakeToolCallingModel, call
from test_mcp_entra import auth, live, MAP, TENANT
from test_subagents import VERDICT_S1

from harness import jobs
from harness.api.app import create_app
from harness.api.bff import BFF, COOKIE, SessionStore, Settings
from harness.clients import pending_actions
from harness.integrity import audit_gaps, unauthorized_writes
from harness.memory import read_notes
from harness.mock_zambeel import connect
from harness.worker import ServiceExecutor, Worker


@pytest.fixture
def stack(flow, live, tmp_path):
    key = Fernet.generate_key()
    store_path = tmp_path / "browser-sessions.db"
    settings = Settings(TENANT, "harness", "http://localhost:8000/auth/callback", "http://localhost:5173", False,
                        {"fe":"api://fe/mcp.access", "zambeel":"api://zambeel/mcp.access"})

    class Cache:
        def __init__(self, raw): self.value = json.loads(raw) if raw else {}
        def serialize(self): return json.dumps(self.value)

    class Application:
        def __init__(self, cache): self.cache = cache
        def initiate_auth_code_flow(self, scopes, redirect_uri):
            return {"auth_uri":"https://login.microsoftonline.com/authorize", "state":"test-state"}
        def acquire_token_by_auth_code_flow(self, saved, response):
            user = response.get("code")
            if response.get("state") != saved["state"] or user not in ("s1","s2","i1","i2"):
                raise ValueError("Invalid synthetic login")
            self.cache.value["user"] = user
            return {"id_token_claims":{"tid":TENANT,"oid":user,"aud":"harness",
                "iss":f"https://login.microsoftonline.com/{TENANT}/v2.0","exp":time.time()+3600}}
        def get_accounts(self):
            user = self.cache.value.get("user")
            return [{"home_account_id":f"{user}.{TENANT}","local_account_id":user,"realm":TENANT}] if user else []
        def acquire_token_silent(self, scopes, account):
            user = self.cache.value["user"]
            server = scopes[0].split("api://",1)[1].split("/",1)[0]
            role = "Instructor" if user.startswith("i") else "Student"
            return {"access_token":live.auth.token(server,oid=user,roles=[role])}

    def application(raw):
        cache = Cache(raw)
        return Application(cache), cache
    def backend():
        return BFF(settings,SessionStore(store_path,key),MAP,application)
    def sign_in(client, user):
        assert client.get("/auth/login",follow_redirects=False).status_code == 302
        response = client.get(f"/auth/callback?state=test-state&code={user}",follow_redirects=False)
        assert response.status_code == 302, response.text
        status = client.get("/auth/status").json()
        client.headers.update({"Origin":settings.frontend,"X-CSRF-Token":status["csrf_token"]})
        return status
    sub = FakeToolCallingModel(messages=iter([
        call("check_my_eligibility",course_id="CS412",section="S1"),
        call("EligibilityVerdict",**VERDICT_S1), AIMessage(content="Eligibility checked.")]))
    main = scripted(call("task",description="Check CS412 S1",subagent_type="eligibility-checker"),
                    call("submit_case",course_id="CS412",section="S1"),call("execute_enrollment"))
    agent = flow.agent(main,subagent_model=sub)
    memory = flow.store()
    bff = backend()
    app = create_app(agent,memory,bff=bff)
    return SimpleNamespace(flow=flow,live=live,backend=backend,sign_in=sign_in,agent=agent,memory=memory,bff=bff,app=app)


@pytest.mark.parametrize("decision", ["approve","reject"])
def test_full_force_enrollment_with_identity_isolation_and_restart(stack,decision):
    s = stack
    student, second, wrong, teacher = [TestClient(s.app) for _ in range(4)]
    s.sign_in(student,"s1")
    s.sign_in(second,"s2")
    s.sign_in(wrong,"i2")
    s.sign_in(teacher,"i1")
    sid = session(student)
    assert student.get("/api/students/S1/profile").json()["student_id"] == "S1"
    assert second.get("/api/students/S1/memory").status_code == 403
    assert student.post("/api/sessions",json={"student_id":"S2"}).status_code == 403
    first = events(student.post(f"/api/sessions/{sid}/messages",json={"student_id":"S1","text":"Submit CS412 S1"}))
    assert first[-1]["status"] == "interrupted"
    assert any(e["type"] == "subagent.finished" for e in first)
    confirmed = events(student.post(f"/api/sessions/{sid}/resume",json={"student_id":"S1","decision":"approve"}))
    assert confirmed[-1]["status"] == "waiting_for_instructor"
    assert pending_actions(s.agent,sid) == ["execute_enrollment"]
    assert second.get(f"/api/cases/{sid}").status_code == 403
    assert student.post(f"/api/cases/{sid}/decision",json={"instructor_id":"I1","decision":"approve"}).status_code == 403
    assert wrong.post(f"/api/cases/{sid}/decision",json={"instructor_id":"I2","decision":"approve"}).status_code == 403
    acknowledged = events(teacher.post(f"/api/cases/{sid}/decision",json={"instructor_id":"I1","decision":decision}))
    assert acknowledged[-1]["status"] == "answered"
    # Instructor did not drive the student's graph. Worker authority is separate.
    assert pending_actions(s.agent,sid) == ["execute_enrollment"]
    old_cookie = student.cookies.get(COOKIE)
    s.bff.store.delete(old_cookie)
    student.close()
    if decision == "approve":
        with closing(connect()) as conn:
            assert conn.execute("SELECT COUNT(*) FROM execution_jobs WHERE case_id=?",(sid,)).fetchone()[0] == 1
            now = time.time()
            abandoned = jobs.claim(conn,now=now,lease_seconds=1)
            assert abandoned.case_id == sid
        # A new connection/worker recovers the expired lease after a crash.
        token = s.live.auth.token(scp=None,azp="worker",oid="worker-object",roles=["Cases.ExecuteApproved"])
        executor = ServiceExecutor(s.live.urls["fe"],SimpleNamespace(get=lambda:token),allow_local=True)
        with closing(connect()) as conn:
            worker = Worker(conn,executor,clock=lambda:now+2)
            assert asyncio.run(worker.run_once())
            assert not asyncio.run(worker.run_once())
            job = conn.execute("SELECT * FROM execution_jobs WHERE case_id=?",(sid,)).fetchone()
            assert job["status"] == "succeeded" and job["attempts"] == 2
            saved_id = job["enrollment_id"]
            assert asyncio.run(executor(sid))["enrollment_id"] == saved_id
        expected, count = "COMPLETED", 1
    else:
        expected, count = "REJECTED", 0
    # Rebuild API, cache store and checkpoint connections. No model reply is
    # available: terminal reconciliation must be entirely deterministic.
    restarted = s.flow.agent(FakeToolCallingModel(messages=iter([])))
    memory = s.flow.store()
    returning = TestClient(create_app(restarted,memory,bff=s.backend()))
    s.sign_in(returning,"s1")
    history = returning.get(f"/api/sessions/{sid}/messages")
    assert history.status_code == 200, history.text
    assert expected in history.json()[-1]["text"]
    state = restarted.get_state({"configurable":{"thread_id":sid}})
    assert state.interrupts == () and state.next == ()
    detail = returning.get(f"/api/cases/{sid}").json()
    assert detail["case"]["state"] == expected
    assert read_notes(memory,"S1").count(f" {sid}:") == 1 and read_notes(memory,"S2") == ""
    assert old_cookie not in str(state.values)
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key=?",(sid,)).fetchone()[0] == count
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []
    for client in (returning,second,wrong,teacher): client.close()


def test_ineligible_student_is_refused_even_if_model_claims_eligible(stack):
    s = stack
    client = TestClient(s.app)
    s.sign_in(client,"s2")
    sid = session(client,"S2")
    # Scripted sub-agent returns the S1 verdict deliberately. FE must recheck
    # S2's actual missing prerequisite rather than trusting the model's verdict.
    result = events(client.post(f"/api/sessions/{sid}/messages",json={"student_id":"S2","text":"Submit CS412 S1"}))
    assert not any(e["type"] == "interrupt" and e["interrupt"]["kind"] == "confirm_submission" for e in result)
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cases WHERE case_id=?",(sid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key=?",(sid,)).fetchone()[0] == 0
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []
    client.close()


def test_student_cancellation_does_not_create_approval_or_execution_job(stack):
    s = stack
    model = scripted(call("submit_case",course_id="CS412",section="S1"),call("save_case_note"))
    client = TestClient(create_app(s.flow.agent(model),s.memory,bff=s.backend()))
    s.sign_in(client,"s1")
    sid = session(client)
    result = events(client.post(f"/api/sessions/{sid}/messages",json={"student_id":"S1","text":"Submit CS412 S1"}))
    assert result[-1]["status"] == "interrupted"
    declined = events(client.post(f"/api/sessions/{sid}/resume",json={"student_id":"S1","decision":"reject"}))
    assert declined[-1]["status"] == "answered"
    with closing(connect()) as conn:
        assert conn.execute("SELECT state FROM cases WHERE case_id=?",(sid,)).fetchone()[0] == "CANCELLED"
        assert conn.execute("SELECT COUNT(*) FROM approvals WHERE case_id=?",(sid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key=?",(sid,)).fetchone()[0] == 0
        jobs.initialize(conn)
        assert conn.execute("SELECT COUNT(*) FROM execution_jobs WHERE case_id=?",(sid,)).fetchone()[0] == 0
        assert audit_gaps(conn) == [] and unauthorized_writes(conn) == []
    assert "CANCELLED" in read_notes(s.memory,"S1")
    client.close()

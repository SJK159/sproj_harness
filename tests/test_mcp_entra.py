"""Real HTTP MCP + signed test tokens; no Microsoft credentials or model.

The production verifier is used with an injected trusted public key. FE acquires
its own application token through a test provider, never forwarding user tokens.
"""
import asyncio
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from types import SimpleNamespace

import httpx
import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from harness.mcp.entra import Verifier, AuthFailure, BearerMiddleware
from harness.mcp.security import principal
from harness.mock_zambeel import connect
from harness.integrity import audit_gaps, unauthorized_writes

TENANT = "test-tenant"
MAP = [dict(tenant_id=TENANT, object_id=o, actor_id=a, role=r) for o,a,r in
       [("s1","S1","Student"),("s2","S2","Student"),("i1","I1","Instructor"),("i2","I2","Instructor")]]


@pytest.fixture
def auth():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key()))
    def token(server="fe", **changes):
        c = dict(iss=f"https://login.microsoftonline.com/{TENANT}/v2.0", tid=TENANT, aud=server,
                 ver="2.0", oid="s1", azp="harness", iat=int(time.time()), exp=int(time.time())+300,
                 scp="mcp.access", roles=["Student"])
        c.update(changes)
        c = {k:v for k,v in c.items() if v is not None}
        return jwt.encode(c, private, algorithm="RS256", headers={"kid":"test-key"})
    def verifier(server):
        services = {"worker":{"Cases.ExecuteApproved"}} if server == "fe" else {"fe-service":{"Academic.Read","Enrollment.ExecuteApproved"}}
        return Verifier(TENANT, server, MAP, clients={"harness"}, services=services, keys=keys)
    return SimpleNamespace(token=token, verifier=verifier, private=private)


@pytest.mark.parametrize("changes,status", [
    ({"aud":"zambeel"},401),({"iss":"wrong"},401),({"tid":"wrong"},401),
    ({"ver":"1.0"},401),({"exp":1},401),({"iat":int(time.time())+3600},401),
    ({"oid":None},401),({"azp":None},401),({"oid":[]},401),
    ({"scp":"other"},403),({"scp":[]},403),({"oid":"unknown"},403),
    ({"roles":["Instructor"]},403),({"roles":"Student"},403),({"azp":"unknown"},403),
    ({"scp":None,"roles":["Cases.ExecuteApproved"]},403),
    ({"scp":None,"azp":"unknown","roles":["Cases.ExecuteApproved"]},403),
    ({"scp":"mcp.access","azp":"worker","roles":["Cases.ExecuteApproved"]},403),
])
def test_invalid_claims(auth,changes,status):
    with pytest.raises(AuthFailure) as e:
        auth.verifier("fe").verify(auth.token(**changes))
    assert e.value.status == status


def test_bad_signature_algorithm_and_missing_exp(auth):
    claims = jwt.decode(auth.token(), options={"verify_signature":False})
    other = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    tokens=["broken",jwt.encode(claims,other,algorithm="RS256"), jwt.encode(claims,"x"*40,algorithm="HS256")]
    claims.pop("exp")
    tokens.append(jwt.encode(claims,auth.private,algorithm="RS256"))
    for token in tokens:
        with pytest.raises(AuthFailure) as e:auth.verifier("fe").verify(token)
        assert e.value.status == 401


def test_mapping_and_separate_service_identity(auth):
    assert auth.verifier("fe").verify(auth.token()).actor == "S1"
    who=auth.verifier("fe").verify(auth.token(scp=None,azp="worker",oid="worker-object",roles=["Cases.ExecuteApproved"]))
    assert who.service and who.actor == "" and who.permissions == {"Cases.ExecuteApproved"}
    assert principal.get() is None


def test_key_service_failure_sanitized(auth):
    def unavailable(token):raise jwt.PyJWKClientConnectionError("secret-payload")
    v=auth.verifier("fe");v.keys=SimpleNamespace(get_signing_key_from_jwt=unavailable)
    with pytest.raises(AuthFailure) as e:v.verify(auth.token())
    assert e.value.status==503 and "secret" not in e.value.code


@pytest.fixture
def live(seeded, secret, auth, monkeypatch):
    monkeypatch.setenv("HARNESS_MCP_AUTH_MODE","entra")
    monkeypatch.setenv("HARNESS_MCP_ALLOW_LOOPBACK","true")
    from harness.mcp import service
    fe_token=auth.token("zambeel",scp=None,azp="fe-service",oid="fe-object",roles=["Academic.Read","Enrollment.ExecuteApproved"])
    monkeypatch.setattr(service,"credentials",lambda:SimpleNamespace(get=lambda:fe_token))
    from harness.mcp.fe import create_server as fe
    from harness.mcp.zambeel import create_server as zambeel
    servers=[];threads=[];urls={}
    try:
        for name, factory in [("zambeel",zambeel),("fe",fe)]:
            sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close()
            urls[name]=f"http://127.0.0.1:{port}/mcp"
            monkeypatch.setenv(f"HARNESS_{name.upper()}_MCP_URL",urls[name])
            app=BearerMiddleware(factory().streamable_http_app(),auth.verifier(name))
            server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="critical",access_log=False))
            thread=threading.Thread(target=server.run,daemon=True);servers.append(server);threads.append(thread);thread.start()
            deadline=time.monotonic()+10
            while not server.started and time.monotonic()<deadline:time.sleep(.02)
            assert server.started
        async def acall(name,tool,args,token):
            async with httpx.AsyncClient(headers={"Authorization":"Bearer "+token},trust_env=False) as http:
                async with streamable_http_client(urls[name],http_client=http) as (read,write,_):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        result=await session.call_tool(tool,args or {})
            return result
        def call(tool,args=None,*,server="fe",user="s1",service=False,roles=None):
            if service:
                t=auth.token(server,scp=None,azp="worker" if server=="fe" else "fe-service",oid="app",
                             roles=roles or (["Cases.ExecuteApproved"] if server=="fe" else ["Academic.Read","Enrollment.ExecuteApproved"]))
            else:t=auth.token(server,oid=user,roles=roles or (["Instructor"] if user.startswith("i") else ["Student"]))
            result=asyncio.run(acall(server,tool,args,t))
            return result
        yield SimpleNamespace(call=call,urls=urls,auth=auth,db=seeded)
    finally:
        for server in servers:server.should_exit=True
        for thread in threads:thread.join(timeout=10)


def val(result):
    assert not result.isError, result
    import json
    return result.structuredContent or json.loads("".join(c.text for c in result.content if c.type == "text"))


def submit(live,cid="FE-entra"):
    assert val(live.call("prepare_case",dict(case_id=cid,course_id="CS412",section="S1")))["state"]=="AWAITING_CONFIRMATION"
    val(live.call("confirm_case",dict(case_id=cid,confirmed=True)))
    val(live.call("submit_case",dict(case_id=cid,course_id="CS412",section="S1")))


def test_http_gate_no_demo_fallback(live):
    for server,url in live.urls.items():
        for headers in [{},{"X-Demo-Actor":"S1","X-Demo-Role":"student"},
                        {"Authorization":"Bearer "+live.auth.token("wrong")}]:
            r=httpx.post(url,headers=headers,json={},trust_env=False)
            assert r.status_code==401 and "Bearer" in r.headers["www-authenticate"]
    assert principal.get() is None


def test_real_two_mcp_flow_worker_and_isolation(live):
    from harness.worker import checked_result
    from harness import jobs
    assert val(live.call("get_my_profile",server="zambeel"))["student_id"]=="S1"
    submit(live)
    assert val(live.call("get_case_status",{"case_id":"FE-entra"},user="s2"))["error_type"]=="PermissionError"
    assert val(live.call("decide_case",{"case_id":"FE-entra","decision":"approve"},user="i2"))["error_type"]=="NotCourseOwner"
    assert live.call("execute_approved_case",{"case_id":"FE-entra"}).isError
    assert live.call("enroll",{"case_id":"FE-entra","offering_id":"CS412-S1"},server="zambeel").isError
    val(live.call("decide_case",{"case_id":"FE-entra","decision":"approve"},user="i1"))
    jobs.initialize(live.db)
    assert live.db.execute("SELECT COUNT(*) FROM execution_jobs WHERE case_id='FE-entra'").fetchone()[0]==1
    first=checked_result(val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True)),"FE-entra")
    assert first["outcome"]=="completed"
    assert val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True))==first
    assert live.db.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key='FE-entra'").fetchone()[0]==1
    assert audit_gaps(live.db)==[] and unauthorized_writes(live.db)==[]


def test_service_permissions_no_student_impersonation(live):
    assert live.call("get_my_profile",server="zambeel",service=True).isError
    assert live.call("get_student_record",{"subject_id":"S2"},server="zambeel").isError
    assert val(live.call("get_student_record",{"subject_id":"S2"},server="zambeel",service=True))["student_id"]=="S2"
    assert live.call("enroll",{"case_id":"missing","offering_id":"CS412-S1"},server="zambeel",service=True,roles=["Academic.Read"]).isError
    assert val(live.call("prepare_case",{"case_id":"x","course_id":"CS412","section":"S1"},service=True))["error_type"]=="PermissionError"


def test_concurrent_service_retries(live):
    submit(live)
    val(live.call("decide_case",{"case_id":"FE-entra","decision":"approve"},user="i1"))
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True)),range(2)))
    assert {r["outcome"] for r in results}<={"completed","retry"}
    assert val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True))["outcome"]=="completed"
    assert live.db.execute("SELECT COUNT(*) FROM audit_events WHERE action='TOKEN_CONSUMED'").fetchone()[0]==1
    assert audit_gaps(live.db)==[] and unauthorized_writes(live.db)==[]


def test_transient_failure_keeps_case_retryable(live,monkeypatch):
    from harness.mcp.client import RemoteAcademic
    from harness.mcp.service import RetryableServiceFailure
    submit(live)
    val(live.call("decide_case",{"case_id":"FE-entra","decision":"approve"},user="i1"))
    real=RemoteAcademic.enroll
    def lost(self,*a,**kw):
        real(self,*a,**kw)
        raise RetryableServiceFailure()
    monkeypatch.setattr(RemoteAcademic,"enroll",lost)
    result=val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True))
    assert result["outcome"]=="retry" and result["state"]=="EXECUTING"
    monkeypatch.setattr(RemoteAcademic,"enroll",real)
    assert val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True))["outcome"]=="completed"
    assert live.db.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key='FE-entra'").fetchone()[0]==1


def test_approval_outbox_rollback(awaiting,secret,monkeypatch):
    from harness import jobs
    from harness.approvals import record_decision
    def fail(*args,**kwargs):raise RuntimeError("enqueue failed")
    monkeypatch.setattr(jobs,"enqueue_execution",fail)
    with pytest.raises(RuntimeError):record_decision(awaiting,"C-A1","I1","APPROVE")
    assert awaiting.execute("SELECT state FROM cases WHERE case_id='C-A1'").fetchone()[0]=="AWAITING_APPROVAL"
    assert awaiting.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]==0


def test_expired_approval_worker_terminal(live):
    from datetime import datetime,UTC
    from harness.approvals import record_decision
    submit(live)
    record_decision(live.db,"FE-entra","I1","APPROVE",now=datetime(2020,1,1,tzinfo=UTC))
    result=val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True))
    assert result["outcome"]=="terminal" and result["error_code"]=="TOKEN_EXPIRED"


def test_recover_confirmed_without_student_token(live):
    from harness.mcp.recovery import recover
    val(live.call("prepare_case",dict(case_id="FE-recover",course_id="CS412",section="S1")))
    val(live.call("confirm_case",dict(case_id="FE-recover",confirmed=True)))
    recover()
    assert live.db.execute("SELECT state FROM cases WHERE case_id='FE-recover'").fetchone()[0]=="AWAITING_APPROVAL"


def test_ammars_worker_over_real_http(live):
    from harness.worker import Worker, ServiceExecutor
    submit(live)
    val(live.call("decide_case",{"case_id":"FE-entra","decision":"approve"},user="i1"))
    token=live.auth.token(scp=None,azp="worker",oid="worker-object",roles=["Cases.ExecuteApproved"])
    executor=ServiceExecutor(live.urls["fe"],SimpleNamespace(get=lambda:token),allow_local=True)
    worker=Worker(live.db,executor)
    assert asyncio.run(worker.run_once())
    job=live.db.execute("SELECT * FROM execution_jobs WHERE case_id='FE-entra'").fetchone()
    assert job["status"]=="succeeded" and job["enrollment_id"]>0
    assert audit_gaps(live.db)==[] and unauthorized_writes(live.db)==[]


def test_execution_lock_cross_process_release(seeded,tmp_path):
    import subprocess,sys,os
    from harness.mcp.execution import case_lock,ExecutionBusy
    code="from harness.mcp.execution import case_lock; import time; h=case_lock('FE-lock'); h.__enter__(); print('locked',flush=True); time.sleep(30)"
    child=subprocess.Popen([sys.executable,"-c",code],env=dict(os.environ),stdout=subprocess.PIPE,text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    try:
        assert child.stdout.readline().strip()=="locked"
        with pytest.raises(ExecutionBusy):
            with case_lock("FE-lock"):pass
    finally:
        child.terminate();child.wait(timeout=10)
    with case_lock("FE-lock"):pass  # No stale lease after process death.


def test_recovery_lifespan_starts_and_stops(monkeypatch):
    from harness.mcp.__main__ import RecoveryLifespan
    import harness.mcp.recovery as recovery
    calls=[]
    monkeypatch.setattr(recovery,"recover",lambda:calls.append(1))
    async def run():
        import anyio
        started=anyio.Event()
        async def wrapped(scope,receive,send):
            await send({"type":"lifespan.startup.complete"})
            while not calls:await anyio.sleep(.01)
            await send({"type":"lifespan.shutdown.complete"})
        await RecoveryLifespan(wrapped)({"type":"lifespan"},lambda:None,lambda m:started.set() or anyio.sleep(0))
    asyncio.run(run())
    assert calls


def test_bff_client_matches_real_mcp_interface(live):
    from harness.mcp.authenticated import AuthenticatedMCP
    person=SimpleNamespace(actor_id="S1",role="Student")
    client=AuthenticatedMCP(person,lambda server:live.auth.token(server),live.urls,allow_local=True)
    profile=asyncio.run(client.call("zambeel","get_my_profile",{},actor="S1"))
    assert profile["student_id"]=="S1"
    case=asyncio.run(client.call("fe","prepare_case",{"case_id":"FE-bff","course_id":"CS412","section":"S1"},actor="S1"))
    assert case["student_id"]=="S1" and case["state"]=="AWAITING_CONFIRMATION"


def test_service_catalogue_for_prompt_completion(live):
    rows=val(live.call("academic_catalogue",server="zambeel",service=True))["sections"]
    assert any(r["course_id"]=="CS412" and r["department"]=="CS" for r in rows)


def test_rejected_case_stays_terminal(live):
    submit(live)
    val(live.call("decide_case",{"case_id":"FE-entra","decision":"reject"},user="i1"))
    result=val(live.call("execute_approved_case",{"case_id":"FE-entra"},service=True))
    assert result["outcome"]=="terminal" and result["state"]=="REJECTED"
    assert live.db.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key='FE-entra'").fetchone()[0]==0

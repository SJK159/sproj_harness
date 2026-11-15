"""Backend-managed flow tested without real Microsoft or university credentials."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api_helpers import events, scripted, session
from harness.api.app import create_app
from harness.api.bff import BFF, SessionStore, Settings, COOKIE
from harness.api.auth import Principal


@pytest.fixture
def login_system(flow, tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_FE_MCP_URL", "https://fe.example/mcp")
    monkeypatch.setenv("HARNESS_ZAMBEEL_MCP_URL", "https://zambeel.example/mcp")
    settings = Settings("tenant", "harness", "http://localhost:8000/auth/callback", "http://localhost:5173", False,
                        {"fe":"api://fe/mcp.access", "zambeel":"api://zambeel/mcp.access"})
    clock = [1000.0]
    key = Fernet.generate_key()
    store = SessionStore(tmp_path / "auth.db", key, clock=lambda:clock[0])
    calls = []
    identity = {"tid":"tenant", "oid":"s1", "aud":"harness", "iss":"https://login.microsoftonline.com/tenant/v2.0", "exp":2000}
    class Cache:
        def serialize(self): return "synthetic-refresh-cache"
    class Application:
        def initiate_auth_code_flow(self, scopes, redirect_uri):
            calls.append(("login", scopes, redirect_uri))
            return {"auth_uri":"https://login.microsoftonline.com/authorize?state=bound", "state":"bound", "nonce":"nonce"}
        def acquire_token_by_auth_code_flow(self, saved, supplied):
            if supplied.get("state") != saved["state"] or supplied.get("code") != "valid":
                raise ValueError("invalid state/code")
            return {"id_token_claims":identity}
        def get_accounts(self):
            return [{"home_account_id":"s1.tenant", "local_account_id":"s1", "realm":"tenant"}]
        def acquire_token_silent(self, scopes, account):
            calls.append(("token", scopes, account))
            return {"access_token":"synthetic-token-for-" + scopes[0]}
    mappings = [{"tenant_id":"tenant", "object_id":"s1", "actor_id":"S1", "role":"Student"},
                {"tenant_id":"tenant", "object_id":"i1", "actor_id":"I1", "role":"Instructor"}]
    bff = BFF(settings, store, mappings, lambda serialized:(Application(), Cache()))
    client = TestClient(create_app(flow.agent(scripted()), flow.store(), bff=bff))
    return SimpleNamespace(client=client, bff=bff, clock=clock, calls=calls, claims=identity, key=key, flow=flow)


def sign_in(system):
    response = system.client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302
    response = system.client.get("/auth/callback?state=bound&code=valid", follow_redirects=False)
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "http://localhost:5173"
    state = system.client.get("/auth/status").json()
    system.client.headers.update({"X-CSRF-Token":state["csrf_token"], "Origin":"http://localhost:5173"})
    return state


def test_login_cookie_encryption_and_restart(login_system):
    s = login_system
    assert s.client.get("/auth/status").json()["authenticated"] is False
    assert s.client.get("/api/me").status_code == 401
    value = sign_in(s)
    assert value["actor_id"] == "S1" and value["role"] == "Student"
    assert "cache" not in value and "access_token" not in value
    assert s.client.get("/api/me").json()["actor_id"] == "S1"
    raw = s.bff.store.path.read_bytes()
    assert b"synthetic-refresh-cache" not in raw
    assert s.client.cookies.get(COOKIE).encode() not in raw
    restarted = SessionStore(s.bff.store.path, s.key, clock=lambda:s.clock[0])
    assert restarted.read(s.client.cookies.get(COOKIE))["principal"]["actor_id"] == "S1"
    wrong = SessionStore(s.bff.store.path, Fernet.generate_key(), clock=lambda:s.clock[0])
    with pytest.raises(HTTPException): wrong.read(s.client.cookies.get(COOKIE))


def test_csrf_identity_conflict_and_signout(login_system):
    s = login_system
    sign_in(s)
    assert s.client.post("/api/sessions", json={"student_id":"S2"}).status_code == 403
    sid = session(s.client)
    assert s.client.post(f"/api/sessions/{sid}/stop").status_code == 204
    s.client.headers["Origin"] = "https://attacker.example"
    assert s.client.post(f"/api/sessions/{sid}/stop").status_code == 403
    s.client.headers["Origin"] = "http://localhost:5173"
    csrf = s.client.headers.pop("X-CSRF-Token")
    assert s.client.post("/auth/logout").status_code == 403
    s.client.headers["X-CSRF-Token"] = csrf
    reference = s.client.cookies.get(COOKIE)
    assert s.client.post("/auth/logout").status_code == 200
    assert s.client.get("/api/me").status_code == 401
    with pytest.raises(HTTPException): s.bff.store.read(reference)


def test_callback_state_cookie_binding_and_replay(login_system):
    s = login_system
    assert s.client.get("/auth/callback?state=bound&code=valid").status_code == 401
    s.client.get("/auth/login", follow_redirects=False)
    assert s.client.get("/auth/callback?state=wrong&code=valid").status_code == 401
    assert s.client.get("/auth/callback?state=bound&code=valid").status_code == 401
    sign_in(s)
    assert s.client.get("/auth/callback?state=bound&code=valid").status_code == 401


@pytest.mark.parametrize("changes", [{"tid":"other"}, {"aud":"other"}, {"iss":"https://other"}, {"exp":1}])
def test_invalid_callback_identity(login_system, changes):
    s = login_system
    s.claims.update(changes)
    s.client.get("/auth/login", follow_redirects=False)
    assert s.client.get("/auth/callback?state=bound&code=valid").status_code == 401


def test_unknown_user_and_session_expiry(login_system):
    s = login_system
    s.claims["oid"] = "unmapped"
    s.client.get("/auth/login", follow_redirects=False)
    assert s.client.get("/auth/callback?state=bound&code=valid").status_code == 403
    s.claims["oid"] = "s1"
    sign_in(s)
    s.clock[0] += 8 * 3600 + 1
    assert s.client.get("/api/me").status_code == 401


def test_resource_specific_tokens_and_mapping_changes(login_system):
    s = login_system
    sign_in(s)
    reference = s.client.cookies.get(COOKIE)
    first = s.bff.token(reference, "fe")
    second = s.bff.token(reference, "zambeel")
    assert first != second
    assert [c[1] for c in s.calls if c[0] == "token"] == [["api://fe/mcp.access"], ["api://zambeel/mcp.access"]]
    with pytest.raises(HTTPException): s.bff.token(reference, "unknown")
    s.bff.identities.clear()
    assert s.client.get("/api/me").status_code == 403


def test_secure_cookies_and_cors(login_system):
    s = login_system
    response = s.client.get("/auth/login", follow_redirects=False)
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
    response = s.client.options("/api/me", headers={"Origin":"https://attacker.example", "Access-Control-Request-Method":"GET"})
    assert response.status_code == 400
    response = s.client.options("/api/me", headers={"Origin":"http://localhost:5173", "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"X-CSRF-Token"})
    assert response.headers["access-control-allow-credentials"] == "true"
    assert s.client.get("/auth/status").headers["cache-control"] == "no-store"
    with pytest.raises(ValueError):
        Settings("tenant","client","http://remote.example/auth/callback","http://remote.example",False,{"fe":"scope"})
    s.bff.settings = Settings("tenant","harness","https://app.example/auth/callback","https://app.example",True,s.bff.settings.scopes)
    assert "Secure" in s.client.get("/auth/login",follow_redirects=False).headers["set-cookie"]


def test_verified_identity_and_transport_reach_background_agent(login_system, monkeypatch):
    from fakes import call
    from harness.mock_zambeel import get_student_profile
    from harness.mcp.authenticated import AuthenticatedMCP
    s = login_system
    calls = []
    # Tool threads use separate SQLite connections, not the fixture's main-thread connection.
    async def invoke_threadsafe(self, server, name, arguments, *, actor, role="student", service=False):
        from harness.mock_zambeel import connect
        from contextlib import closing
        assert self.person.actor_id == actor == "S1" and not service
        calls.append((server, name))
        with closing(connect()) as conn:
            return get_student_profile(conn, "S1")
    monkeypatch.setattr(AuthenticatedMCP, "call", invoke_threadsafe)
    s.client = TestClient(create_app(s.flow.agent(scripted(call("get_my_profile"))), s.flow.store(), bff=s.bff))
    sign_in(s)
    sid = session(s.client)
    response = s.client.post(f"/api/sessions/{sid}/messages", json={"student_id":"S1", "text":"My profile"})
    evs = events(response)
    assert evs[-1]["status"] == "answered" and calls == [("zambeel", "get_my_profile")]
    snapshot = s.flow.agent(scripted()).get_state({"configurable":{"thread_id":sid}})
    assert "synthetic-refresh-cache" not in str(snapshot.values)
    assert s.client.cookies.get(COOKIE) not in str(snapshot.values)


def test_instructor_decision_does_not_resume_student_graph(login_system, monkeypatch):
    from harness import workflow
    from harness.mcp.authenticated import AuthenticatedMCP
    s = login_system
    workflow.open_case(s.flow.db,"C-bff","S1","CS412","S1")
    workflow.record_confirmation(s.flow.db,"C-bff","S1",True)
    workflow.submit(s.flow.db,"C-bff","S1")
    data = {"principal":asdict(Principal("tenant","i1","I1","Instructor")), "csrf":"synthetic-csrf", "account":"i1.tenant", "cache":"cache"}
    reference = s.bff.store.create("session",data,3600)
    s.client.cookies.set(COOKIE,reference)
    s.client.headers.update({"Origin":"http://localhost:5173", "X-CSRF-Token":"synthetic-csrf"})
    seen = []
    async def decide(self, server, name, arguments, **identity):
        seen.append((server,name,identity))
        return {"case_id":"C-bff","state":"APPROVED"}
    monkeypatch.setattr(AuthenticatedMCP,"call",decide)
    evs = events(s.client.post("/api/cases/C-bff/decision",json={"instructor_id":"I1","decision":"approve"}))
    assert evs[-1]["status"] == "answered"
    assert seen == [("fe","decide_case",{"actor":"I1","role":"instructor","service":False})]
    assert s.flow.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0  # MCP, never local minting


def test_cache_updates_are_serialized_across_connections(login_system):
    from concurrent.futures import ThreadPoolExecutor
    s = login_system
    sign_in(s)
    reference = s.client.cookies.get(COOKIE)
    def increment(_):
        def update(data):
            data["counter"] = data.get("counter",0) + 1
        s.bff.store.change(reference,update)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment,range(12)))
    assert s.bff.store.read(reference)["counter"] == 12


def test_transient_confirmation_failure_keeps_checkpoint_resumable(login_system,monkeypatch):
    from contextlib import closing
    from harness.mock_zambeel import connect
    from harness import workflow
    from harness.clients import pending_actions
    from harness.mcp.authenticated import AuthenticatedMCP, MCPUnavailable
    from fakes import call
    s = login_system
    agent = s.flow.agent(scripted(call("submit_case",course_id="CS412",section="S1"),call("execute_enrollment")))
    s.client = TestClient(create_app(agent,s.flow.store(),bff=s.bff))
    sign_in(s)
    unavailable = [True]
    async def invoke(self,server,name,arguments,*,actor,**kwargs):
        assert actor == self.person.actor_id == "S1"
        if unavailable[0]:
            unavailable[0] = False
            raise MCPUnavailable("temporary outage")
        with closing(connect()) as conn:
            if name == "prepare_case":
                return workflow.open_case(conn,arguments["case_id"],actor,arguments["course_id"],arguments["section"])
            if name == "confirm_case":
                return {"state":workflow.record_confirmation(conn,arguments["case_id"],actor,arguments["confirmed"])}
            if name == "submit_case":
                return workflow.submit(conn,arguments["case_id"],actor)
            pytest.fail("Unexpected MCP operation")
    monkeypatch.setattr(AuthenticatedMCP,"call",invoke)
    sid = session(s.client)
    first = events(s.client.post(f"/api/sessions/{sid}/messages",json={"student_id":"S1","text":"Submit CS412 S1"}))
    assert first[-1]["status"] == "error"
    assert pending_actions(agent,sid) == ["submit_case"]
    second = events(s.client.post(f"/api/sessions/{sid}/resume",json={"student_id":"S1","decision":"approve"}))
    assert second[-1]["status"] == "waiting_for_instructor"
    assert pending_actions(agent,sid) == ["execute_enrollment"]


def test_interaction_required_is_refused_before_stream(login_system):
    s = login_system
    sign_in(s)
    sid = session(s.client)
    original = s.bff.application
    def application(cache):
        app, store = original(cache)
        app.acquire_token_silent = lambda *args,**kwargs: None
        return app, store
    s.bff.application = application
    response = s.client.post(f"/api/sessions/{sid}/messages",json={"student_id":"S1","text":"Profile"})
    assert response.status_code == 401 and "text/event-stream" not in response.headers["content-type"]


def test_expiry_during_tool_execution_requests_reauthentication(login_system,monkeypatch):
    from harness.mcp.authenticated import AuthenticatedMCP, ReauthenticationRequired
    from fakes import call
    s = login_system
    s.client = TestClient(create_app(s.flow.agent(scripted(call("get_my_profile"))),s.flow.store(),bff=s.bff))
    sign_in(s)
    sid = session(s.client)
    async def expired(*args,**kwargs):
        raise ReauthenticationRequired("Sign in again")
    monkeypatch.setattr(AuthenticatedMCP,"call",expired)
    evs = events(s.client.post(f"/api/sessions/{sid}/messages",json={"student_id":"S1","text":"Profile"}))
    assert evs[-1]["status"] == "error" and evs[-1]["reauthenticate"] is True


def test_lazy_model_failure_is_operational_and_sanitized():
    from harness.api.app import DeferredAgent
    def unavailable():
        raise RuntimeError("private-provider-detail")
    agent = DeferredAgent(unavailable)
    with pytest.raises(HTTPException) as exc:
        agent.get_state({})
    assert exc.value.status_code == 503 and "private-provider-detail" not in exc.value.detail

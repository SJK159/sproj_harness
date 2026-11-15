import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from harness.api.auth import Principal
from harness.mcp.authenticated import AuthenticatedMCP, MCPUnavailable, current_transport
from harness.mcp.client import acall


def setup_transport(monkeypatch, result=None, failure=None):
    import harness.mcp.authenticated as module
    seen = []
    @asynccontextmanager
    async def transport(url, *, http_client):
        assert "X-Demo-Actor" not in http_client.headers and "X-FE-Service-Key" not in http_client.headers
        seen.append((url, http_client.headers["Authorization"]))
        if failure:
            raise failure
        yield None, None, None
    class Session:
        def __init__(self,*args): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def initialize(self): pass
        async def call_tool(self,name,args):
            assert "student_id" not in args
            return result or SimpleNamespace(isError=False, structuredContent={"ok":True})
    monkeypatch.setattr(module,"streamable_http_client",transport)
    monkeypatch.setattr(module,"ClientSession",Session)
    client = AuthenticatedMCP(Principal("tenant","oid","S1","Student"), lambda server:f"synthetic-{server}",
                              {"fe":"https://fe.example/mcp", "zambeel":"https://zambeel.example/mcp"})
    return client, seen


def test_each_resource_gets_its_own_bearer_token(monkeypatch):
    client, seen = setup_transport(monkeypatch)
    context = current_transport.set(client)
    try:
        asyncio.run(acall("fe","get_my_cases",actor="S1"))
        asyncio.run(acall("zambeel","get_my_profile",actor="S1"))
    finally:
        current_transport.reset(context)
    assert seen == [("https://fe.example/mcp","Bearer synthetic-fe"), ("https://zambeel.example/mcp","Bearer synthetic-zambeel")]


@pytest.mark.parametrize("kwargs", [{"actor":"S2"}, {"actor":"S1","role":"instructor"}, {"actor":"S1","service":True}])
def test_model_or_caller_cannot_override_identity(monkeypatch,kwargs):
    client, seen = setup_transport(monkeypatch)
    with pytest.raises(MCPUnavailable):
        asyncio.run(client.call("fe","get_my_cases",{},**kwargs))
    assert not seen


@pytest.mark.parametrize("response", [SimpleNamespace(isError=True), SimpleNamespace(isError=False,structuredContent=[]),
    SimpleNamespace(isError=False,structuredContent={"error_type":"ConnectionError", "error":"private-token"})])
def test_protocol_and_server_failures_remain_operational(monkeypatch,response):
    client,_ = setup_transport(monkeypatch,result=response)
    with pytest.raises(MCPUnavailable) as exc:
        asyncio.run(client.call("fe","prepare_case",{},actor="S1"))
    assert "private-token" not in str(exc.value)


def test_transport_errors_do_not_leak_credentials(monkeypatch):
    client,_ = setup_transport(monkeypatch,failure=httpx.ReadTimeout("private-token"))
    with pytest.raises(MCPUnavailable) as exc:
        asyncio.run(client.call("fe","prepare_case",{},actor="S1"))
    assert "private-token" not in str(exc.value)


def test_missing_authenticated_context_never_falls_back(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_MODE","bff")
    context = current_transport.set(None)
    try:
        with pytest.raises(Exception,match="demo fallback is disabled"):
            asyncio.run(acall("fe","get_my_cases",actor="S1"))
    finally:
        current_transport.reset(context)


def test_prepare_confirmation_transport_failure_does_not_reject_case(flow,monkeypatch):
    from harness.clients import prepare_confirmation
    client,_ = setup_transport(monkeypatch,failure=httpx.ConnectError("down"))
    context = current_transport.set(client)
    try:
        with pytest.raises(MCPUnavailable):
            prepare_confirmation("C-retry","S1",{"course_id":"CS412","section":"S1"})
    finally:
        current_transport.reset(context)
    assert flow.db.execute("SELECT COUNT(*) FROM cases WHERE case_id = 'C-retry'").fetchone()[0] == 0

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from harness import jobs, workflow
from harness.approvals import decide
from harness.worker import OperationalFailure, ProtocolFailure, ServiceExecutor, Worker, checked_result


@pytest.fixture
def approved(db, secret):
    workflow.open_case(db, "C-worker", "S1", "CS412", "S1")
    workflow.record_confirmation(db, "C-worker", "S1", True)
    workflow.submit(db, "C-worker", "S1")
    decide(db, "C-worker", "I1", "APPROVE")
    jobs.initialize(db)
    # Simulate a pre-outbox approved case. These isolated scheduling tests insert
    # their own jobs at a synthetic clock of 100; production approval now enqueues
    # atomically at wall-clock time (covered by the MCP integration tests).
    with db:
        db.execute("DELETE FROM execution_jobs WHERE case_id = 'C-worker'")
    return db


def enqueue(conn, case="C-worker", now=100):
    conn.execute("BEGIN IMMEDIATE")
    jobs.enqueue_execution(conn, case, now=now)
    conn.commit()


def result(outcome="completed", **changes):
    value = dict(case_id="C-worker", state="COMPLETED" if outcome == "completed" else "APPROVED",
                 outcome=outcome, retryable=outcome == "retry", enrollment_id=123 if outcome == "completed" else None,
                 error_code=None, message=None)
    value.update(changes)
    return value


def job(conn):
    return dict(conn.execute("SELECT * FROM execution_jobs WHERE case_id = 'C-worker'").fetchone())


def test_enqueue_requires_approval_transaction_and_rolls_back(approved):
    with pytest.raises(RuntimeError):
        jobs.enqueue_execution(approved, "C-worker", now=100)
    with pytest.raises(RuntimeError):
        with approved:
            approved.execute("UPDATE cases SET flag = 'atomic-test' WHERE case_id = 'C-worker'")
            jobs.enqueue_execution(approved, "C-worker", now=100)
            raise RuntimeError("simulated failure")
    assert approved.execute("SELECT COUNT(*) FROM execution_jobs").fetchone()[0] == 0
    assert approved.execute("SELECT flag FROM cases WHERE case_id = 'C-worker'").fetchone()[0] is None
    enqueue(approved)
    enqueue(approved)
    assert approved.execute("SELECT COUNT(*) FROM execution_jobs").fetchone()[0] == 1


def test_unconfirmed_case_cannot_be_queued(db):
    workflow.open_case(db, "C-worker", "S1", "CS412", "S1")
    jobs.initialize(db)
    with pytest.raises(ValueError), db:
        db.execute("BEGIN")
        jobs.enqueue_execution(db, "C-worker", now=100)


def test_lease_expiry_reclaim_and_fencing(approved):
    enqueue(approved)
    first = jobs.claim(approved, now=100, lease_seconds=10)
    assert jobs.claim(approved, now=109, lease_seconds=10) is None
    second = jobs.claim(approved, now=110, lease_seconds=10)
    assert first.token != second.token and second.attempts == 2
    assert not jobs.finish(approved, first, now=111, status="succeeded")
    assert jobs.finish(approved, second, now=111, status="succeeded", enrollment_id=123)
    assert jobs.claim(approved, now=1000, lease_seconds=10) is None


def test_competing_process_connections_claim_only_once(approved):
    enqueue(approved)
    path = approved.execute("PRAGMA database_list").fetchone()[2]
    def attempt(_):
        with sqlite3.connect(path, timeout=10) as conn:
            return jobs.claim(conn, now=100, lease_seconds=10)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(attempt, range(4)))
    assert sum(c is not None for c in claims) == 1


def test_restart_discovers_missing_jobs_without_resetting_outcomes(approved):
    assert jobs.recover_execution_jobs(approved, now=100) == 1
    first = jobs.claim(approved, now=100, lease_seconds=10)
    jobs.finish(approved, first, now=101, status="terminal", error="TOKEN_EXPIRED")
    assert jobs.recover_execution_jobs(approved, now=1000) == 0
    assert job(approved)["status"] == "terminal"


def test_lost_response_retries_same_case_without_duplicate_enrollment(approved):
    from harness.integrity import audit_gaps, unauthorized_writes
    enqueue(approved)
    clock = [100]
    calls = []
    async def endpoint(case_id):
        calls.append(case_id)
        saved = workflow.execute(approved, case_id, "S1")
        if len(calls) == 1:
            raise httpx.ReadTimeout("response lost")
        return result(enrollment_id=saved["enrollment_id"])
    worker = Worker(approved, endpoint, clock=lambda: clock[0])
    assert asyncio.run(worker.run_once())
    assert job(approved)["status"] == "pending"
    assert not asyncio.run(worker.run_once())  # backoff
    clock[0] = 102
    assert asyncio.run(worker.run_once())
    assert calls == ["C-worker", "C-worker"]
    assert job(approved)["status"] == "succeeded"
    assert approved.execute("SELECT COUNT(*) FROM enrollments WHERE idempotency_key = 'C-worker'").fetchone()[0] == 1
    assert audit_gaps(approved) == [] and unauthorized_writes(approved) == []


@pytest.mark.parametrize("failure,expected", [
    (httpx.ConnectError("unavailable"), "pending"),
    (TimeoutError(), "pending"),
    (OperationalFailure("secret-must-not-be-stored"), "blocked"),
    (ProtocolFailure("bad"), "blocked"),
    (ExceptionGroup("group", [httpx.ConnectError("down")]), "pending"),
])
def test_failure_classification_is_not_academic_rejection(approved, failure, expected):
    enqueue(approved)
    async def fail(case_id):
        raise failure
    asyncio.run(Worker(approved, fail, clock=lambda: 100).run_once())
    assert job(approved)["status"] == expected
    assert "secret" not in str(job(approved))
    assert approved.execute("SELECT state FROM cases WHERE case_id = 'C-worker'").fetchone()[0] == "APPROVED"
    if expected == "blocked":
        assert jobs.retry_blocked(approved, "C-worker", now=110)
        assert job(approved)["status"] == "pending"


@pytest.mark.parametrize("status,expected", [(401,"blocked"),(403,"blocked"),(404,"blocked"),(429,"pending"),(503,"pending")])
def test_http_failures(approved, status, expected):
    enqueue(approved)
    async def fail(case_id):
        response = httpx.Response(status, request=httpx.Request("POST", "https://fe.example/mcp"))
        response.raise_for_status()
    asyncio.run(Worker(approved, fail, clock=lambda:100).run_once())
    assert job(approved)["status"] == expected


@pytest.mark.parametrize("changes", [
    {"case_id":"other"}, {"retryable":True}, {"enrollment_id":None}, {"enrollment_id":True},
    {"state":"APPROVED"}, {"outcome":"invented"}, {"message":{}}, {"error_code":"EXPIRED"},
])
def test_rejects_contradictory_results(changes):
    with pytest.raises(ProtocolFailure):
        checked_result(result(**changes), "C-worker")


def test_expired_approval_terminal_is_retained_without_retry(approved):
    enqueue(approved)
    async def endpoint(case_id):
        return result("terminal", error_code="TOKEN_EXPIRED", message="Instructor review required")
    worker = Worker(approved, endpoint, clock=lambda:100)
    asyncio.run(worker.run_once())
    assert job(approved)["status"] == "terminal" and job(approved)["last_error"] == "TOKEN_EXPIRED"
    assert not asyncio.run(worker.run_once())


def test_submitted_recovery_routes_saved_confirmation_only(db):
    workflow.open_case(db, "C-worker", "S1", "CS412", "S1")
    assert jobs.recover_submitted(db, lambda case: pytest.fail("unconfirmed")) == {}
    workflow.record_confirmation(db, "C-worker", "S1", True)
    def route(case_id):
        workflow.submit(db, case_id, "S1")
    assert jobs.recover_submitted(db, route) == {"C-worker":"routed"}
    assert jobs.recover_submitted(db, route) == {}
    assert db.execute("SELECT COUNT(*) FROM notifications WHERE kind = 'APPROVAL_REQUESTED'").fetchone()[0] == 1


@pytest.mark.parametrize("url", ["http://localhost:8101/mcp", "https://user:pass@fe.example/mcp", "https://fe.example/mcp?token=x"])
def test_worker_never_uses_demo_or_embedded_credentials(url):
    with pytest.raises(ValueError):
        ServiceExecutor(url, None)


def test_overall_timeout_and_cancelled_worker_are_recoverable(approved):
    enqueue(approved)
    async def hang(case_id):
        await asyncio.Event().wait()
    asyncio.run(Worker(approved, hang, clock=lambda:100, deadline=.01).run_once())
    assert job(approved)["status"] == "pending"
    async def cancelled(case_id):
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(Worker(approved, cancelled, clock=lambda:102).run_once())
    assert job(approved)["status"] == "running"
    assert jobs.claim(approved, now=192, lease_seconds=90).attempts == 3


def test_service_adapter_sends_only_case_and_resource_token(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import mcp
    import mcp.client.streamable_http
    captured = {}
    @asynccontextmanager
    async def transport(url, *, http_client):
        assert url == "https://fe.example/mcp"
        assert http_client.headers["Authorization"] == "Bearer synthetic-worker-token"
        assert "X-Demo-Actor" not in http_client.headers
        assert "X-FE-Service-Key" not in http_client.headers
        yield None, None, None
    class Session:
        def __init__(self, *args): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def initialize(self): pass
        async def call_tool(self, name, arguments):
            captured.update(name=name, arguments=arguments)
            return SimpleNamespace(isError=False, structuredContent=result())
    monkeypatch.setattr(mcp.client.streamable_http, "streamable_http_client", transport)
    monkeypatch.setattr(mcp, "ClientSession", Session)
    executor = ServiceExecutor("https://fe.example/mcp", SimpleNamespace(get=lambda:"synthetic-worker-token"))
    assert asyncio.run(executor("C-worker"))["outcome"] == "completed"
    assert captured == {"name":"execute_approved_case", "arguments":{"case_id":"C-worker"}}


def test_application_token_provider_uses_fe_default_scope(monkeypatch):
    import msal
    from harness.worker import ClientCredentials
    captured = {}
    class Application:
        def __init__(self, client_id, **kwargs):
            captured.update(client_id=client_id, **kwargs)
        def acquire_token_for_client(self, *, scopes):
            assert scopes == ["api://fe/.default"]
            return {"access_token":"synthetic-app-token"}
    monkeypatch.setattr(msal, "ConfidentialClientApplication", Application)
    provider = ClientCredentials("tenant", "worker-id", "synthetic-secret", "api://fe/.default")
    assert provider.get() == "synthetic-app-token"
    assert captured["timeout"] == 10
    assert captured["authority"] == "https://login.microsoftonline.com/tenant"
    with pytest.raises(ValueError):
        ClientCredentials("tenant", "worker-id", "synthetic-secret", "api://fe/mcp.access")
    provider.application.acquire_token_for_client = lambda **kwargs: {"error":"temporarily_unavailable"}
    with pytest.raises(TimeoutError):
        provider.get()
    provider.application.acquire_token_for_client = lambda **kwargs: {"error":"invalid_client", "error_description":"private"}
    with pytest.raises(OperationalFailure) as exc:
        provider.get()
    assert "private" not in str(exc.value)

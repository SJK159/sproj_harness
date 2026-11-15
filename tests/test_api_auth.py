"""Synthetic RSA tokens exercise the real verifier; no tenant credentials required."""
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from api_helpers import scripted, session
from harness.api.auth import EntraVerifier, configured_verifier


@pytest.fixture
def credentials():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rows = [{"tenant_id": "tenant", "object_id": "student", "actor_id": "S1", "role": "Student"},
            {"tenant_id": "tenant", "object_id": "other-student", "actor_id": "S2", "role": "Student"},
            {"tenant_id": "tenant", "object_id": "teacher", "actor_id": "I1", "role": "Instructor"}]
    provider = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
    verifier = EntraVerifier("tenant", "harness-api", "harness.access", rows, provider)
    def token(**changes):
        claims = dict(iss=verifier.issuer, aud="harness-api", tid="tenant", oid="student", ver="2.0",
                      iat=int(time.time()), exp=int(time.time()) + 300, scp="harness.access", roles=["Student"])
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256")
    return verifier, token


@pytest.mark.parametrize("changes,status", [
    ({"iss": "wrong"}, 401), ({"aud": "mcp-fe"}, 401), ({"tid": "other"}, 401),
    ({"exp": 1}, 401), ({"ver": "1.0"}, 401), ({"scp": "other"}, 403),
    ({"scp": None}, 403), ({"roles": ["Instructor"]}, 403), ({"oid": "unknown"}, 403),
])
def test_rejects_invalid_credentials(credentials, changes, status):
    verifier, token = credentials
    with pytest.raises(HTTPException) as exc:
        verifier.verify(token(**changes))
    assert exc.value.status_code == status


def test_signature_and_required_claims(credentials):
    verifier, token = credentials
    claims = jwt.decode(token(), options={"verify_signature": False})
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in [jwt.encode(claims, wrong, algorithm="RS256"), jwt.encode(claims, "x" * 32, algorithm="HS256"), "broken"]:
        with pytest.raises(HTTPException) as exc:
            verifier.verify(bad)
        assert exc.value.status_code == 401


def test_missing_claim_and_key_service_outage(credentials):
    verifier, token = credentials
    for changes in ({"oid": []}, {"oid": ""}, {"iat": int(time.time()) + 3600}):
        with pytest.raises(HTTPException) as exc:
            verifier.verify(token(**changes))
        assert exc.value.status_code == 401
    def unavailable(value):
        raise jwt.PyJWKClientConnectionError("not exposed")
    verifier.keys = SimpleNamespace(get_signing_key_from_jwt=unavailable)
    with pytest.raises(HTTPException) as exc:
        verifier.verify(token())
    assert exc.value.status_code == 503 and "not exposed" not in exc.value.detail


def protected_client(flow, credentials):
    from fastapi.testclient import TestClient
    from harness.api.app import create_app
    verifier, token = credentials
    client = TestClient(create_app(flow.agent(scripted()), flow.store(), verifier=verifier))
    client.headers["Authorization"] = "Bearer " + token()
    return client


def test_identity_and_api_ownership(flow, credentials):
    client = protected_client(flow, credentials)
    assert client.get("/api/me").json() == {"mode": "entra", "actor_id": "S1", "role": "Student"}
    assert client.get("/api/students/S1/profile").status_code == 200
    sid = session(client)
    assert client.post(f"/api/sessions/{sid}/stop").status_code == 204
    for path in ["/api/students", "/api/instructors", "/api/students/S2/profile", "/api/students/S2/memory",
                 "/api/students/I1/notifications", "/api/instructors/I1/pending"]:
        assert client.get(path).status_code == 403
    assert client.post("/api/sessions", json={"student_id": "S2"}).status_code == 403
    for suffix, body in [("messages", {"student_id": "S2", "text": "hi"}),
                         ("resume", {"student_id": "S2", "decision": "approve"})]:
        assert client.post(f"/api/sessions/{sid}/{suffix}", json=body).status_code == 403
    client.headers["Authorization"] = "Bearer " + credentials[1](oid="teacher", roles=["Instructor"])
    assert client.get("/api/instructors/I1/pending").status_code == 200
    assert client.get(f"/api/sessions/{sid}/messages").status_code == 403
    assert client.post(f"/api/sessions/{sid}/stop").status_code == 403


def test_missing_expired_and_cross_student_resume(flow, credentials):
    client = protected_client(flow, credentials)
    sid = session(client)
    for value in [None, "Bearer " + credentials[1](exp=1), "Bearer malformed"]:
        client.headers.pop("Authorization", None)
        if value:
            client.headers["Authorization"] = value
        response = client.post(f"/api/sessions/{sid}/messages", json={"student_id": "S1", "text": "hi"})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert "text/event-stream" not in response.headers["content-type"]


def test_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_MODE", "typo")
    with pytest.raises(ValueError):
        configured_verifier()
    monkeypatch.setenv("HARNESS_AUTH_MODE", "entra")
    monkeypatch.setenv("HARNESS_USE_MCP", "true")
    with pytest.raises(ValueError, match="demo MCP"):
        configured_verifier()


def test_authenticated_confirmation_owner_approval_and_single_enrollment(flow, credentials):
    from fastapi.testclient import TestClient
    from harness.api.app import create_app
    from api_helpers import events, say
    from fakes import call
    from case_helpers import enrollment_count
    from harness.integrity import audit_gaps, unauthorized_writes
    verifier, token = credentials
    agent = flow.agent(scripted(call("submit_case", course_id="CS412", section="S1"),
                                call("execute_enrollment"), call("save_case_note")))
    client = TestClient(create_app(agent, flow.store(), verifier=verifier))
    client.headers["Authorization"] = "Bearer " + token()
    sid = session(client)
    say(client, sid, "Submit CS412 section S1")
    client.headers["Authorization"] = "Bearer " + token(oid="other-student")
    for suffix in ("messages", "stop", "resume"):
        assert client.post(f"/api/sessions/{sid}/{suffix}", json={"student_id": "S2", "decision": "approve", "text": "hi"}).status_code == 403
    assert client.get(f"/api/cases/{sid}").status_code == 403
    client.headers["Authorization"] = "Bearer " + token()
    events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "decision": "approve"}))
    assert client.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"}).status_code == 403
    notice = flow.db.execute("SELECT notification_id FROM notifications WHERE recipient_id = 'I1'").fetchone()[0]
    assert client.post("/api/notifications/read", json={"ids": [notice]}).status_code == 403
    assert flow.db.execute("SELECT read_at FROM notifications WHERE notification_id = ?", (notice,)).fetchone()[0] is None
    client.headers["Authorization"] = "Bearer " + token(oid="teacher", roles=["Instructor"])
    assert client.post("/api/notifications/read", json={"ids": [notice]}).status_code == 204
    result = events(client.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"}))
    assert result[-1]["status"] == "answered"
    assert enrollment_count(flow.db, sid) == 1
    assert client.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"}).status_code == 409
    assert audit_gaps(flow.db) == [] and unauthorized_writes(flow.db) == []

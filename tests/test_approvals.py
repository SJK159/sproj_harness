import threading
from datetime import UTC, datetime, timedelta

import pytest

from harness.approvals import (
    TOKEN_TTL,
    ApprovalConfigError,
    NotCourseOwner,
    TokenBadSignature,
    TokenExpired,
    TokenMalformed,
    TokenReused,
    TokenWrongCase,
    mint_token,
    record_decision,
    verify_and_consume,
)
from harness.cases import InvalidTransition, get_case
from harness.mock_zambeel import connect

pytestmark = pytest.mark.usefixtures("secret")

def audit_actions(db, case_id):
    return [r["action"] for r in db.execute(
        "SELECT action FROM audit_events WHERE case_id = ? ORDER BY event_id", (case_id,))]

def approvals_count(db, case_id):
    return db.execute("SELECT COUNT(*) FROM approvals WHERE case_id = ?", (case_id,)).fetchone()[0]

# --- valid path ---

def test_owner_approval_mints_a_token_that_verifies_once(awaiting):
    token = record_decision(awaiting, "C-A1", "I1", "APPROVE")
    assert get_case(awaiting, "C-A1")["state"] == "APPROVED"
    approval = verify_and_consume(awaiting, token, "C-A1")
    assert approval["instructor_id"] == "I1"
    assert audit_actions(awaiting, "C-A1")[-1] == "TOKEN_CONSUMED"

# --- A3: wrong approver ---

def test_a3_non_owner_cannot_approve(awaiting):
    with pytest.raises(NotCourseOwner):
        record_decision(awaiting, "C-A1", "I2", "APPROVE")
    assert get_case(awaiting, "C-A1")["state"] == "AWAITING_APPROVAL"
    assert approvals_count(awaiting, "C-A1") == 0
    assert audit_actions(awaiting, "C-A1") == ["APPROVAL_REFUSED"]

def test_reject_records_reason_and_mints_nothing(awaiting):
    assert record_decision(awaiting, "C-A2", "I1", "REJECT", reason="Room at capacity") is None
    row = awaiting.execute("SELECT decision, reason, token FROM approvals WHERE case_id = 'C-A2'").fetchone()
    assert (row["decision"], row["reason"], row["token"]) == ("REJECT", "Room at capacity", None)
    assert get_case(awaiting, "C-A2")["state"] == "REJECTED"

def test_a_case_cannot_be_decided_twice(awaiting):
    record_decision(awaiting, "C-A1", "I1", "APPROVE")
    with pytest.raises(InvalidTransition):
        record_decision(awaiting, "C-A1", "I1", "REJECT")
    assert get_case(awaiting, "C-A1")["state"] == "APPROVED"

# --- A4: bad tokens ---

def test_a4_expired_token_is_refused(awaiting):
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    token = record_decision(awaiting, "C-A1", "I1", "APPROVE", now=t0)
    with pytest.raises(TokenExpired):
        verify_and_consume(awaiting, token, "C-A1", now=t0 + TOKEN_TTL + timedelta(seconds=1))
    assert audit_actions(awaiting, "C-A1")[-1] == "TOKEN_REFUSED"

def test_a4_reused_token_is_refused(awaiting):
    token = record_decision(awaiting, "C-A1", "I1", "APPROVE")
    verify_and_consume(awaiting, token, "C-A1")
    with pytest.raises(TokenReused):
        verify_and_consume(awaiting, token, "C-A1")

def flip_first(s):
    return ("B" if s[0] != "B" else "C") + s[1:]

@pytest.mark.parametrize("part", [1, 2])  # 1 = payload, 2 = signature
def test_a4_tampered_token_is_refused(awaiting, part):
    token = record_decision(awaiting, "C-A1", "I1", "APPROVE")
    pieces = token.split(".")
    pieces[part] = flip_first(pieces[part])
    with pytest.raises(TokenBadSignature):
        verify_and_consume(awaiting, ".".join(pieces), "C-A1")
    verify_and_consume(awaiting, token, "C-A1")  # the real token is still unused

def test_a4_token_for_another_case_is_refused(awaiting):
    token_a2 = record_decision(awaiting, "C-A2", "I1", "APPROVE")
    record_decision(awaiting, "C-A1", "I1", "APPROVE")
    with pytest.raises(TokenWrongCase):
        verify_and_consume(awaiting, token_a2, "C-A1")
    verify_and_consume(awaiting, token_a2, "C-A2")  # not burned by the failed attempt

def test_a4_token_signed_with_another_secret_is_refused(awaiting, monkeypatch):
    forged, _, _ = mint_token("C-A1", "I1")
    monkeypatch.setenv("APPROVAL_SECRET", "a-different-secret-" + "y" * 32)
    record_decision(awaiting, "C-A1", "I1", "APPROVE")
    with pytest.raises(TokenBadSignature):
        verify_and_consume(awaiting, forged, "C-A1")

def test_a4_garbage_is_refused(awaiting):
    with pytest.raises(TokenMalformed):
        verify_and_consume(awaiting, "not-a-token", "C-A1")

def test_concurrent_consumes_succeed_once(awaiting, tmp_path):
    token = record_decision(awaiting, "C-A1", "I1", "APPROVE")
    outcomes = []
    def consume():
        conn = connect(tmp_path / "harness.db")
        try:
            verify_and_consume(conn, token, "C-A1")
            outcomes.append("ok")
        except TokenReused:
            outcomes.append("reused")
        finally:
            conn.close()
    threads = [threading.Thread(target=consume) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(outcomes) == ["ok", "reused"]

# --- config ---

@pytest.mark.parametrize("value", [None, "too-short"])
def test_missing_or_weak_secret_fails_closed(awaiting, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("APPROVAL_SECRET")
    else:
        monkeypatch.setenv("APPROVAL_SECRET", value)
    with pytest.raises(ApprovalConfigError):
        record_decision(awaiting, "C-A1", "I1", "APPROVE")
    assert get_case(awaiting, "C-A1")["state"] == "AWAITING_APPROVAL"
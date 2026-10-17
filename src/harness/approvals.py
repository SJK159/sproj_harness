"""Signed, single-use approval tokens (CLAUDE.md invariants 1 and 2, BRD FR-06 / NFR-01).

Instructor side only: `record_decision` (and `mint_token`) are called by scripts/approve.py,
never by an agent tool. `verify_and_consume` is the gate `execute_enrollment` calls (M5).

Token: `v1.<payload>.<sig>`
  payload = base64url(JSON {case_id, instructor_id, nonce, exp})
  sig     = base64url(HMAC-SHA256(APPROVAL_SECRET, "v1." + payload))
Verification order: format -> signature -> bound to case -> expiry -> approval row -> atomic consume.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from harness.audit import write_event
from harness.cases import InvalidTransition, get_case, transition
from harness.mock_zambeel import get_section
from harness.notifications import notify

TOKEN_VERSION = "v1"
TOKEN_TTL = timedelta(hours=24)
MIN_SECRET_LENGTH = 32


class ApprovalConfigError(Exception):
    """APPROVAL_SECRET missing or too short. Nothing is signed or verified without it."""


class NotCourseOwner(Exception):
    pass


class TokenRefused(Exception):
    code = "REFUSED"


class TokenMalformed(TokenRefused):
    code = "MALFORMED"


class TokenBadSignature(TokenRefused):
    code = "BAD_SIGNATURE"


class TokenWrongCase(TokenRefused):
    code = "WRONG_CASE"


class TokenExpired(TokenRefused):
    code = "EXPIRED"


class TokenUnknown(TokenRefused):
    code = "UNKNOWN"


class TokenReused(TokenRefused):
    code = "REUSED"


def _secret() -> bytes:
    value = os.environ.get("APPROVAL_SECRET", "")
    if len(value) < MIN_SECRET_LENGTH:
        raise ApprovalConfigError(f"APPROVAL_SECRET must be set and at least {MIN_SECRET_LENGTH} characters.")
    return value.encode()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(signing_input: str) -> str:
    return _b64encode(hmac.new(_secret(), signing_input.encode(), hashlib.sha256).digest())


def mint_token(case_id: str, instructor_id: str, *, now: datetime | None = None) -> tuple[str, str, datetime]:
    """Return (token, nonce, expires_at). Pure: records nothing."""
    now = now or datetime.now(UTC)
    nonce = secrets.token_hex(16)
    expires_at = now + TOKEN_TTL
    claims = {"case_id": case_id, "instructor_id": instructor_id, "nonce": nonce, "exp": int(expires_at.timestamp())}
    payload = _b64encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{TOKEN_VERSION}.{payload}"
    return f"{signing_input}.{_sign(signing_input)}", nonce, expires_at


def record_decision(
    conn: sqlite3.Connection,
    case_id: str,
    instructor_id: str,
    decision: str,
    reason: str | None = None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Record an instructor's APPROVE or REJECT. Returns the token on approval, None on rejection.

    Only the instructor who owns the case's section may decide. Refusals are audited here.
    """
    if decision not in ("APPROVE", "REJECT"):
        raise ValueError(f"decision must be APPROVE or REJECT, got {decision!r}")
    if decision == "APPROVE":
        _secret()  # fail closed before writing anything
    now = now or datetime.now(UTC)
    case = get_case(conn, case_id)
    owner = get_section(conn, case["offering_id"])["instructor_id"]

    refusal = None
    if instructor_id != owner:
        refusal = NotCourseOwner(f"{instructor_id} does not own {case['offering_id']} (owner: {owner}).")
    elif case["state"] != "AWAITING_APPROVAL":
        refusal = InvalidTransition(f"Case {case_id} is {case['state']}, not AWAITING_APPROVAL.")
    if refusal is not None:
        with conn:
            write_event(conn, case_id, instructor_id, "APPROVAL_REFUSED", case["state"], case["state"],
                        {"decision": decision, "reason": str(refusal)})
        raise refusal

    token = nonce = expires_at = None
    if decision == "APPROVE":
        token, nonce, expires_at = mint_token(case_id, instructor_id, now=now)
    with conn:
        cur = conn.execute(
            """INSERT INTO approvals (case_id, instructor_id, decision, reason, token, nonce, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (case_id, instructor_id, decision, reason, token, nonce,
             expires_at.isoformat() if expires_at else None, now.isoformat()),
        )
        transition(conn, case_id, "APPROVED" if decision == "APPROVE" else "REJECTED", instructor_id, decision,
                   {"approval_id": cur.lastrowid, "reason": reason})
    return token


def _check_token(token: str, case_id: str, now: datetime) -> dict[str, Any]:
    parts = token.split(".") if isinstance(token, str) else []
    if len(parts) != 3 or parts[0] != TOKEN_VERSION:
        raise TokenMalformed("Not a v1 approval token.")
    signing_input = f"{parts[0]}.{parts[1]}"
    # Compare the base64url text, not decoded bytes, so padding-bit changes cannot match.
    if not hmac.compare_digest(_sign(signing_input).encode(), parts[2].encode()):
        raise TokenBadSignature("Signature does not match: token was altered or signed with another key.")
    try:
        claims = json.loads(_b64decode(parts[1]))
    except ValueError:
        raise TokenMalformed("Signed payload is unreadable.") from None
    if not isinstance(claims, dict) or not {"case_id", "exp", "nonce"} <= claims.keys():
        raise TokenMalformed("Signed payload is missing fields.")
    if claims["case_id"] != case_id:
        raise TokenWrongCase(f"Token was minted for case {claims['case_id']}, not {case_id}.")
    if now.timestamp() >= claims["exp"]:
        raise TokenExpired("Token has expired.")
    return claims


def verify_and_consume(
    conn: sqlite3.Connection,
    token: str,
    case_id: str,
    *,
    actor: str = "system",
    now: datetime | None = None,
    on_consumed: Callable[[sqlite3.Connection], None] | None = None,
) -> dict[str, Any]:
    """Verify an approval token for `case_id` and mark it used. Raises a TokenRefused subclass otherwise.

    Single use is enforced by a conditional UPDATE: of two concurrent calls, only one changes the row.
    `on_consumed(conn)` runs inside the same transaction as the consume, so a caller can make
    "token used" and its own state change (e.g. APPROVED -> EXECUTING) commit together or not at all.
    Every outcome is audited.
    """
    _secret()
    now = now or datetime.now(UTC)
    try:
        claims = _check_token(token, case_id, now)
        with conn:
            row = conn.execute(
                "SELECT approval_id, instructor_id FROM approvals WHERE nonce = ? AND case_id = ? AND decision = 'APPROVE'",
                (claims["nonce"], case_id),
            ).fetchone()
            if row is None:
                raise TokenUnknown("No recorded approval matches this token.")
            cur = conn.execute(
                "UPDATE approvals SET consumed_at = ? WHERE approval_id = ? AND consumed_at IS NULL",
                (now.isoformat(), row["approval_id"]),
            )
            if cur.rowcount != 1:
                raise TokenReused("Token has already been used.")
            write_event(conn, case_id, actor, "TOKEN_CONSUMED",
                        detail={"approval_id": row["approval_id"], "instructor_id": row["instructor_id"]})
            if on_consumed is not None:
                on_consumed(conn)
        return {"approval_id": row["approval_id"], "case_id": case_id, "instructor_id": row["instructor_id"]}
    except TokenRefused as refused:
        with conn:
            write_event(conn, case_id, actor, "TOKEN_REFUSED", detail={"code": refused.code, "reason": str(refused)})
        raise


def decide(
    conn: sqlite3.Connection,
    case_id: str,
    instructor_id: str,
    decision: str,
    reason: str | None = None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Instructor side (scripts/approve.py): record the decision and, on rejection, tell the student.

    Returns the approval token on APPROVE, None on REJECT. Raises NotCourseOwner / InvalidTransition.
    """
    token = record_decision(conn, case_id, instructor_id, decision, reason, now=now)
    if decision == "REJECT":
        case = get_case(conn, case_id)
        with conn:
            notify(conn, case["student_id"], case_id, "REJECTED",
                   f"Your force-enrollment request {case_id} for {case['offering_id']} was rejected by "
                   f"instructor {instructor_id}. Reason: {reason or 'none given'}.")
    return token

"""Durable execution outbox and fenced worker leases, owned by the orchestrator.

FE must call enqueue_execution inside its approval transaction. This module never
commits that transaction or authorizes enrollment. A job contains only a case ID
and operational metadata; FE remains the deterministic authorization boundary.
"""
import secrets
import sqlite3
from dataclasses import dataclass


def initialize(conn: sqlite3.Connection):
    """Install additive schema before serving requests; never commit caller work."""
    if conn.in_transaction:
        raise RuntimeError("Initialize jobs before opening a workflow transaction")
    conn.execute("""CREATE TABLE IF NOT EXISTS execution_jobs (
        case_id TEXT PRIMARY KEY REFERENCES cases(case_id),
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','running','succeeded','terminal','blocked')),
        attempts INTEGER NOT NULL DEFAULT 0,
        available_at REAL NOT NULL,
        lease_token TEXT,
        lease_until REAL,
        last_error TEXT,
        enrollment_id INTEGER,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS execution_jobs_ready ON execution_jobs(status, available_at, lease_until)")


def enqueue_execution(conn: sqlite3.Connection, case_id: str, *, now: float):
    """Call AFTER APPROVED transition, inside the SAME approval transaction.

    No nested connection context manager: SQLite's context manager would commit
    the approval prematurely. A rollback by FE rolls back this insert as well.
    """
    if not conn.in_transaction:
        raise RuntimeError("Enqueue requires the caller's active approval transaction")
    row = conn.execute("SELECT state FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if row is None or row[0] not in ("APPROVED", "EXECUTING", "COMPLETED"):
        raise ValueError("Execution jobs require an approved case")
    conn.execute("""INSERT INTO execution_jobs(case_id, available_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(case_id) DO NOTHING""", (case_id, now, now, now))


def recover_execution_jobs(conn: sqlite3.Connection, *, now: float) -> int:
    """Backfill missing jobs for approved/in-flight cases, never reset old jobs.

    Safety net for pre-outbox cases. Normal approvals MUST use atomic enqueue.
    FE still checks approval validity; discovery grants no execution authority.
    """
    if conn.in_transaction:
        raise RuntimeError("Recovery requires its own transaction")
    with conn:
        cursor = conn.execute("""INSERT INTO execution_jobs(case_id, available_at, created_at, updated_at)
            SELECT case_id, ?, ?, ? FROM cases WHERE state IN ('APPROVED', 'EXECUTING')
            ON CONFLICT(case_id) DO NOTHING""", (now, now, now))
    return cursor.rowcount


def recover_submitted(conn: sqlite3.Connection, route_case) -> dict[str, str]:
    """FE-side hook: retry saved confirmations using a trusted routing callable.

    Call with FE's deterministic submit operation and academic service context.
    No student token is stored. This does not create a new service permission or
    allow the external worker to impersonate a student. Errors stay recoverable.
    """
    results = {}
    for row in conn.execute("SELECT case_id FROM cases WHERE state = 'SUBMITTED'").fetchall():
        try:
            route_case(row[0])
            results[row[0]] = "routed"
        except Exception:
            results[row[0]] = "needs_reconciliation"
    return results


@dataclass(frozen=True)
class Claim:
    case_id: str
    token: str
    attempts: int


def claim(conn: sqlite3.Connection, *, now: float, lease_seconds: float) -> Claim | None:
    if lease_seconds <= 0 or conn.in_transaction:
        raise ValueError("Claim needs a positive lease and its own transaction")
    # Serializes competing claims even across processes/connections. No network
    # I/O occurs while holding this transaction. Enrollment concurrency is FE's job.
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("""SELECT case_id, attempts FROM execution_jobs
            WHERE (status = 'pending' AND available_at <= ?)
               OR (status = 'running' AND lease_until <= ?)
            ORDER BY available_at, case_id LIMIT 1""", (now, now)).fetchone()
        if row is None:
            conn.commit()
            return None
        token = secrets.token_hex(24)
        conn.execute("""UPDATE execution_jobs SET status = 'running', attempts = attempts + 1,
                        lease_token = ?, lease_until = ?, updated_at = ? WHERE case_id = ?""",
                     (token, now + lease_seconds, now, row[0]))
        conn.commit()
        return Claim(row[0], token, row[1] + 1)
    except BaseException:
        conn.rollback()
        raise


def finish(conn: sqlite3.Connection, job: Claim, *, now: float, status: str,
           delay: float = 0, error: str | None = None, enrollment_id: int | None = None) -> bool:
    """Fence stale workers: only the current unexpired lease can acknowledge."""
    if conn.in_transaction or status not in ("pending", "succeeded", "terminal", "blocked") or delay < 0:
        raise ValueError("Invalid job outcome")
    with conn:
        cursor = conn.execute("""UPDATE execution_jobs SET status = ?, available_at = ?,
            lease_token = NULL, lease_until = NULL, last_error = ?, enrollment_id = ?, updated_at = ?
            WHERE case_id = ? AND status = 'running' AND lease_token = ? AND lease_until > ?""",
            (status, now + delay, error, enrollment_id, now, job.case_id, job.token, now))
    return cursor.rowcount == 1


def retry_blocked(conn: sqlite3.Connection, case_id: str, *, now: float) -> bool:
    """Operator explicitly retries an operational failure after fixing config."""
    if conn.in_transaction:
        raise RuntimeError("Retry requires its own transaction")
    with conn:
        cursor = conn.execute("""UPDATE execution_jobs SET status = 'pending', available_at = ?,
            updated_at = ?, last_error = NULL WHERE case_id = ? AND status = 'blocked'""", (now, now, case_id))
    return cursor.rowcount == 1

"""Whole-database checks for BRD objectives O-02 and O-03. Each returns problem strings; empty means clean.

audit_gaps          O-03: every case has an audit row for each state change, forming one valid chain.
unauthorized_writes O-02: every enrollment the harness made is backed by a verified, owner-issued approval.
"""

import sqlite3
from itertools import pairwise

from harness.cases import TRANSITIONS
from harness.mock_zambeel.seed_data import ENROLLMENTS as SEEDED_ENROLLMENTS


def audit_gaps(conn: sqlite3.Connection) -> list[str]:
    problems = []
    for case in conn.execute("SELECT case_id, state FROM cases ORDER BY case_id").fetchall():
        rows = conn.execute(
            """SELECT from_state, to_state FROM audit_events
               WHERE case_id = ? AND to_state IS NOT NULL AND (from_state IS NULL OR from_state <> to_state)
               ORDER BY event_id""",
            (case["case_id"],),
        ).fetchall()
        chain = [(r["from_state"], r["to_state"]) for r in rows]
        cid = case["case_id"]
        if not chain or chain[0] != (None, "DRAFT"):
            problems.append(f"{cid}: audit trail does not start with creation (None -> DRAFT)")
            continue
        for (_, previous_to), (frm, to) in pairwise(chain):
            if frm != previous_to:
                problems.append(f"{cid}: gap in audit trail: {previous_to} then {frm} -> {to}")
            elif to not in TRANSITIONS.get(frm, ()):
                problems.append(f"{cid}: audit records a transition the state machine forbids: {frm} -> {to}")
        if chain[-1][1] != case["state"]:
            problems.append(f"{cid}: case is {case['state']} but the audit trail ends at {chain[-1][1]}")
    return problems


def unauthorized_writes(conn: sqlite3.Connection) -> list[str]:
    problems = []
    seeded = set(SEEDED_ENROLLMENTS)
    for e in conn.execute("SELECT * FROM enrollments ORDER BY enrollment_id").fetchall():
        who = f"enrollment {e['enrollment_id']} ({e['student_id']} in {e['offering_id']})"
        key = e["idempotency_key"]
        if key is None:
            if (e["student_id"], e["offering_id"], e["kind"]) not in seeded:
                problems.append(f"{who}: made without a case or approval")
            continue
        case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (key,)).fetchone()
        if case is None:
            problems.append(f"{who}: key {key} matches no case")
            continue
        if case["state"] != "COMPLETED" or (case["student_id"], case["offering_id"]) != (e["student_id"], e["offering_id"]):
            problems.append(f"{who}: case {key} is {case['state']} for {case['student_id']} in {case['offering_id']}")
        owner = conn.execute("SELECT instructor_id FROM offerings WHERE offering_id = ?", (e["offering_id"],)).fetchone()[0]
        approval = conn.execute(
            """SELECT 1 FROM approvals WHERE case_id = ? AND decision = 'APPROVE'
               AND consumed_at IS NOT NULL AND instructor_id = ?""",
            (key, owner),
        ).fetchone()
        if approval is None:
            problems.append(f"{who}: no consumed approval by the section owner {owner} for case {key}")
        consumed = conn.execute(
            "SELECT 1 FROM audit_events WHERE case_id = ? AND action = 'TOKEN_CONSUMED'", (key,)
        ).fetchone()
        if consumed is None:
            problems.append(f"{who}: no TOKEN_CONSUMED audit row for case {key}")
    return problems

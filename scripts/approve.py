"""Instructor side: list waiting cases, or approve / reject one and resume its paused thread.

    uv run python scripts/approve.py --pending --instructor I1
    uv run python scripts/approve.py --case FE-1a2b3c4d --instructor I1 --decision approve
    uv run python scripts/approve.py --case FE-1a2b3c4d --instructor I1 --decision reject --reason "Room at capacity"

This is the only place approval tokens are minted (CLAUDE.md invariant 2).
"""

import argparse
import sys
from contextlib import closing

from harness.agent import build_agent
from harness.approvals import NotCourseOwner
from harness.cases import InvalidTransition, UnknownCase, get_case
from harness.clients import NotWaitingForInstructor, instructor_resume
from harness.config import load_env
from harness.mock_zambeel import connect
from harness.persistence import open_checkpointer


def list_pending(instructor_id: str) -> int:
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT c.case_id, c.student_id, c.offering_id, c.updated_at FROM cases c
               JOIN offerings o ON o.offering_id = c.offering_id
               WHERE c.state = 'AWAITING_APPROVAL' AND o.instructor_id = ? ORDER BY c.updated_at""",
            (instructor_id,),
        ).fetchall()
    if not rows:
        print(f"No cases are waiting for {instructor_id}.")
    for r in rows:
        print(f"{r['case_id']}  student {r['student_id']}  {r['offering_id']}  since {r['updated_at']}")
    return 0


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instructor", required=True)
    parser.add_argument("--pending", action="store_true", help="list cases waiting for this instructor")
    parser.add_argument("--case")
    parser.add_argument("--decision", choices=["approve", "reject"])
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.pending:
        return list_pending(args.instructor)
    if not (args.case and args.decision):
        parser.error("--case and --decision are required unless --pending is given")

    agent = build_agent(checkpointer=open_checkpointer())
    try:
        turn = instructor_resume(agent, args.case, args.instructor, args.decision, args.reason)
    except (NotCourseOwner, NotWaitingForInstructor, InvalidTransition, UnknownCase) as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 1

    with closing(connect()) as conn:
        case = get_case(conn, args.case)
        notes = conn.execute(
            "SELECT recipient_id, kind, message FROM notifications WHERE case_id = ? ORDER BY notification_id",
            (args.case,),
        ).fetchall()
    print(f"case {args.case}: {case['state']}" + (f" (flagged: {case['flag']})" if case["flag"] else ""))
    for n in notes:
        print(f"  notice to {n['recipient_id']} [{n['kind']}]: {n['message']}")
    if turn.reply:
        print(f"\nagent: {turn.reply}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

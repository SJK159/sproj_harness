"""Trusted FE-side recovery of confirmed submissions; never user impersonation."""
import logging
import time
from contextlib import closing

from harness import jobs, workflow
from harness.academic import using_academic
from harness.cases import get_case
from harness.mock_zambeel import connect
from harness.mcp.client import RemoteAcademic
from harness.mcp.execution import case_lock


def recover():
    try:
        with closing(connect()) as conn:
            jobs.initialize(conn)
            jobs.recover_execution_jobs(conn, now=time.time())
            def route(case_id):
                with case_lock(case_id):
                    case = get_case(conn, case_id)
                    with using_academic(RemoteAcademic(case["student_id"])):
                        workflow.submit(conn, case_id, case["student_id"])
            results = jobs.recover_submitted(conn, route)
            if "needs_reconciliation" in results.values():
                logging.getLogger(__name__).warning("Confirmed submissions need reconciliation")
    except Exception:
        # Retry on next scan without exposing transport payloads/credentials.
        logging.getLogger(__name__).warning("FE recovery temporarily unavailable")

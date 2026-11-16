"""Single-VM process-safe case mutex. OS releases the lock on process death.

Separate from the SQLite academic database so HTTP academic calls cannot deadlock
behind an FE write transaction. All FE execution paths use the same lock.
"""
import hashlib
import os
from contextlib import contextmanager, closing

from harness.mock_zambeel import db_path, connect


class ExecutionBusy(Exception):
    pass


@contextmanager
def case_lock(case_id):
    folder = db_path().resolve().parent / (db_path().name + ".execution-locks")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hashlib.sha256(case_id.encode()).hexdigest() + ".lock")
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ExecutionBusy("Case execution in progress") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def execute(case_id):
    from harness import workflow
    from harness.cases import get_case
    from harness.academic import using_academic
    from harness.mcp.client import RemoteAcademic
    with case_lock(case_id), closing(connect()) as conn:
        case = get_case(conn, case_id)
        with using_academic(RemoteAcademic(case["student_id"])):
            return workflow.execute(conn, case_id, case["student_id"])


def service_result(case_id):
    import sqlite3
    from harness.cases import get_case
    from harness.mcp.service import RetryableServiceFailure
    with closing(connect()) as conn:
        saved = get_case(conn, case_id)
    if saved["state"] in ("REJECTED", "CANCELLED"):
        return {"case_id": case_id, "state": saved["state"], "outcome": "terminal",
                "retryable": False, "enrollment_id": None,
                "error_code": "CASE_TERMINAL", "message": None}
    result = None
    retry = False
    try:
        result = execute(case_id)
    except (ExecutionBusy, RetryableServiceFailure):
        retry = True
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
        retry = True
    with closing(connect()) as conn:
        case = get_case(conn, case_id)
    state = case["state"]
    # Completion can win a race with a busy response: reconcile the saved result.
    if state == "COMPLETED" and result is None:
        result = execute(case_id)
    completed = state == "COMPLETED"
    terminal = state in ("FAILED", "REJECTED", "CANCELLED")
    if not (completed or terminal or retry):
        raise PermissionError("Case is not approved for execution")
    flag = case.get("flag") or ""
    code = flag.split(":", 1)[0] if flag.startswith("TOKEN_") else "CASE_TERMINAL"
    return {"case_id": case_id, "state": state,
            "outcome": "completed" if completed else "terminal" if terminal else "retry",
            "retryable": not completed and not terminal,
            "enrollment_id": result.get("enrollment_id") if completed else None,
            "error_code": None if completed else code if terminal else "EXECUTION_RETRY",
            "message": None}

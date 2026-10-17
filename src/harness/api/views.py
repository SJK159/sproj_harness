"""Database, checkpoint and store rows -> the frontend's contract objects (frontend/src/api/types.ts).

Read-only, except for the API's own `sessions` table (chat sessions that have no case yet).
"""

import json
import re
import sqlite3
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.store.base import BaseStore

from harness.memory import read_notes
from harness.mock_zambeel import connect, get_section, get_student_profile
from harness.mock_zambeel.seed_data import SCENARIO_HINTS

# Chat sessions belong to the web client, not to mock Zambeel, so the table is created here (in harness.db).
# session_id = thread_id = the case id the session may create (invariant 6).
SESSIONS_DDL = """CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    title      TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

# Tool calls that are not shown as steps: the plan has its own event, the verdict is the sub-agent's answer.
HIDDEN_TOOLS = frozenset({"write_todos", "EligibilityVerdict"})

_NOTE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) (\S+): force enrollment in (\S+) ([A-Z_]+) \((.*)\)\.$")


def open_db() -> sqlite3.Connection:
    """One connection per request. FastAPI may open it on one worker thread and use it on another."""
    conn = connect(check_same_thread=False)
    conn.execute(SESSIONS_DDL)
    return conn


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------------------------------- records

def case_view(conn: sqlite3.Connection, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    case = dict(row)
    next_action = case.get("next_action")
    if next_action is None:
        if case["state"] == "AWAITING_CONFIRMATION":
            next_action = "Waiting for the student to confirm"
        elif case["state"] == "AWAITING_APPROVAL":
            next_action = f"Waiting for {get_section(conn, case['offering_id'])['instructor_id']} to approve or reject"
        elif case["state"] in ("APPROVED", "EXECUTING"):
            next_action = "Enrolling"
    return {"case_id": case["case_id"], "student_id": case["student_id"], "offering_id": case["offering_id"],
            "state": case["state"], "next_action": next_action, "flag": case["flag"],
            "created_at": case["created_at"], "updated_at": case["updated_at"]}


def audit_view(row: sqlite3.Row) -> dict[str, Any]:
    event = dict(row)
    event["detail"] = json.loads(event["detail"]) if event["detail"] else None
    return event


def notification_view(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def get_case_row(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()


def students(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT student_id, name FROM students ORDER BY student_id").fetchall()
    return sorted(({"student_id": r["student_id"], "name": r["name"], "hint": SCENARIO_HINTS[r["student_id"]]}
                   for r in rows if r["student_id"] in SCENARIO_HINTS), key=lambda s: int(s["student_id"][1:]))


def instructors(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT instructor_id, name FROM instructors ORDER BY instructor_id"):
        sections = [o[0] for o in conn.execute(
            "SELECT offering_id FROM offerings WHERE instructor_id = ? ORDER BY offering_id", (r["instructor_id"],))]
        out.append({"instructor_id": r["instructor_id"], "name": r["name"], "sections": sections})
    return out


def profile(conn: sqlite3.Connection, student_id: str) -> dict[str, Any]:
    return get_student_profile(conn, student_id)  # raises UnknownStudent


def cases_of(conn: sqlite3.Connection, student_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM cases WHERE student_id = ? ORDER BY created_at DESC, case_id", (student_id,))
    return [case_view(conn, r) for r in rows.fetchall()]


def case_detail(conn: sqlite3.Connection, case_id: str) -> dict[str, Any] | None:
    row = get_case_row(conn, case_id)
    if row is None:
        return None
    audit = [audit_view(r) for r in conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? ORDER BY event_id", (case_id,))]
    approval = conn.execute(  # the signed token stays in the database
        "SELECT instructor_id, decision, reason, created_at FROM approvals WHERE case_id = ?"
        " ORDER BY approval_id DESC LIMIT 1", (case_id,)).fetchone()
    enrollment = conn.execute(
        "SELECT enrollment_id, kind FROM enrollments WHERE idempotency_key = ?", (case_id,)).fetchone()
    return {"case": case_view(conn, row), "audit": audit,
            "approval": dict(approval) if approval else None,
            "enrollment": dict(enrollment) if enrollment else None,
            "instructor_id": get_section(conn, row["offering_id"])["instructor_id"]}


def pending_for(conn: sqlite3.Connection, instructor_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT c.* FROM cases c JOIN offerings o ON o.offering_id = c.offering_id
           WHERE o.instructor_id = ? AND c.state = 'AWAITING_APPROVAL' ORDER BY c.updated_at, c.case_id""",
        (instructor_id,))
    return [case_view(conn, r) for r in rows.fetchall()]


def decided_by(conn: sqlite3.Connection, instructor_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT c.* FROM cases c JOIN approvals a ON a.case_id = c.case_id
           WHERE a.instructor_id = ? GROUP BY c.case_id ORDER BY MAX(a.created_at) DESC""",
        (instructor_id,))
    return [case_view(conn, r) for r in rows.fetchall()]


def notifications_for(conn: sqlite3.Connection, recipient_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM notifications WHERE recipient_id = ? ORDER BY notification_id DESC",
                        (recipient_id,))
    return [notification_view(r) for r in rows.fetchall()]


# ---------------------------------------------------------------------------------------------------- memory

def parse_notes(content: str) -> list[dict[str, Any]]:
    """Case notes as written by harness.memory.case_note; any other line is skipped."""
    notes = []
    for line in content.splitlines():
        m = _NOTE.match(line.strip())
        if m:
            date, case_id, offering_id, outcome, detail = m.groups()
            notes.append({"date": date, "case_id": case_id, "offering_id": offering_id, "outcome": outcome,
                          "detail": detail, "raw": line.strip()})
    return notes


def memory(store: BaseStore, student_id: str) -> dict[str, Any]:
    return {"student_id": student_id, "notes": parse_notes(read_notes(store, student_id))}


# ---------------------------------------------------------------------------------------------------- steps

def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def reasoning_text(message: BaseMessage) -> str:
    """Reasoning the model returned with this message or chunk, in any of the shapes providers use."""
    parts = []
    if isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                if isinstance(block.get("reasoning"), str):
                    parts.append(block["reasoning"])
                for item in block.get("summary") or []:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
    extra = message.additional_kwargs.get("reasoning_content")
    if isinstance(extra, str):
        parts.append(extra)
    return "".join(parts)


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def tool_outcome(message: ToolMessage) -> tuple[bool, str]:
    """(ok, one-line summary) of a tool result, for the thinking panel."""
    text = message_text(message.content)
    data = _json(text)
    ok = message.status != "error"
    if isinstance(data, dict):
        if data.get("error"):
            return False, str(data["error"])[:200]
        if "can_submit" in data:
            codes = [b["code"] for b in data.get("blocking", [])]
            if codes:
                return ok, f"{data.get('request')}: blocked by {', '.join(codes)}"
            return ok, f"{data.get('request')}: {'can request force enrollment' if data['can_submit'] else 'no force enrollment needed'}"
        if isinstance(data.get("summary"), str):
            return ok, data["summary"][:200]
        if isinstance(data.get("state"), str):
            return ok, f"{data.get('case_id', 'case')} is {data['state']}"
    flat = " ".join(text.split())
    return ok, flat if len(flat) <= 120 else flat[:119] + "…"


def verdict_of(message: ToolMessage) -> dict[str, Any] | None:
    data = _json(message_text(message.content))
    return data if isinstance(data, dict) and isinstance(data.get("sections"), list) else None


def new_step(call: dict[str, Any], agent: str) -> dict[str, Any]:
    step = {"call_id": call["id"], "name": call["name"], "agent": agent, "args": call.get("args") or {},
            "status": "running"}
    if call["name"] == "task":
        step["children"] = []
    return step


# ---------------------------------------------------------------------------------------------------- sessions

def interrupt_view(conn: sqlite3.Connection, session_id: str, action: dict[str, Any]) -> dict[str, Any]:
    name, args = action["name"], action.get("args") or {}
    description = action.get("description") or ""
    if name == "ask_student":
        return {"kind": "ask_student", "question": str(args.get("question", ""))}
    case = get_case_row(conn, session_id)
    if name == "execute_enrollment" and case is not None:
        return {"kind": "waiting_for_instructor", "case_id": session_id,
                "instructor_id": get_section(conn, case["offering_id"])["instructor_id"], "description": description}
    offering = case["offering_id"] if case else f"{args.get('course_id', '')}-{args.get('section', '')}"
    return {"kind": "confirm_submission", "case_id": session_id, "offering_id": offering, "description": description}


def pending_interrupt(conn: sqlite3.Connection, agent: Any, session_id: str) -> dict[str, Any] | None:
    for interrupt in agent.get_state({"configurable": {"thread_id": session_id}}).interrupts:
        for action in interrupt.value.get("action_requests", []):
            return interrupt_view(conn, session_id, action)
    return None


def session_owner(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute("SELECT student_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:  # a session started from the CLI has a case but no sessions row
        row = get_case_row(conn, session_id)
    return row["student_id"] if row else None


def session_view(conn: sqlite3.Connection, agent: Any, session_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    case = get_case_row(conn, session_id)
    base = dict(row) if row else {"session_id": session_id, "student_id": case["student_id"], "title": None,
                                  "created_at": case["created_at"], "updated_at": case["updated_at"]}
    title = f"{case['offering_id']} force enrollment" if case else (base["title"] or "New chat")
    updated = max(base["updated_at"], case["updated_at"]) if case else base["updated_at"]
    return {"session_id": session_id, "student_id": base["student_id"], "title": title,
            "created_at": base["created_at"], "updated_at": updated,
            "case": case_view(conn, case) if case else None,
            "pending_interrupt": pending_interrupt(conn, agent, session_id)}


def sessions_of(conn: sqlite3.Connection, agent: Any, student_id: str) -> list[dict[str, Any]]:
    ids = [r[0] for r in conn.execute(
        """SELECT session_id FROM sessions WHERE student_id = ?
           UNION SELECT case_id FROM cases WHERE student_id = ?""", (student_id, student_id))]
    return sorted((session_view(conn, agent, i) for i in ids), key=lambda s: s["updated_at"], reverse=True)


def history(conn: sqlite3.Connection, agent: Any, session_id: str) -> list[dict[str, Any]]:
    """The chat rebuilt from the checkpointed messages: the checkpoint is the only transcript."""
    state = agent.get_state({"configurable": {"thread_id": session_id}})
    messages = state.values.get("messages", []) if state.values else []
    when = session_view(conn, agent, session_id)["updated_at"] if session_owner(conn, session_id) else now()
    out: list[dict[str, Any]] = []
    turn: dict[str, Any] | None = None

    def flush() -> None:
        if turn is not None:
            out.append(turn)

    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage):
            if m.name == "harness-nudge":
                continue
            flush()
            out.append({"message_id": m.id or f"{session_id}-{i}", "role": "user", "text": message_text(m.content),
                        "created_at": when})
            turn = None
            continue
        if turn is None:
            turn = {"message_id": m.id or f"{session_id}-{i}", "role": "assistant", "text": "", "created_at": when,
                    "thinking": {"todos": [], "steps": [], "reasoning": "", "duration_ms": 0, "case_states": []}}
        steps = turn["thinking"]["steps"]
        if isinstance(m, AIMessage):
            for call in m.tool_calls:
                if call["name"] == "write_todos":
                    turn["thinking"]["todos"] = (call.get("args") or {}).get("todos", [])
                elif call["name"] not in HIDDEN_TOOLS:
                    steps.append(new_step(call, "main"))
            turn["thinking"]["reasoning"] += reasoning_text(m)
            if message_text(m.content):
                turn["text"] = message_text(m.content)
        elif isinstance(m, ToolMessage):
            step = next((s for s in steps if s["call_id"] == m.tool_call_id), None)
            if step is not None:
                ok, summary = tool_outcome(m)
                step.update(status="done" if ok else "error", summary=summary)
                if m.name == "task" and (verdict := verdict_of(m)):
                    turn["verdict"] = verdict
                    step["summary"] = verdict.get("summary") or summary
    flush()
    pending = pending_interrupt(conn, agent, session_id)
    if pending and out and out[-1]["role"] == "assistant":
        out[-1]["interrupt"] = pending
        for step in out[-1]["thinking"]["steps"]:
            if step["status"] == "running":
                step["status"] = "paused"
    return out

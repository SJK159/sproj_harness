"""HTTP API for the web frontend (frontend/): the endpoints of docs/frontend-design-prompt.md, "API contract".

A third client of the same agent, next to harness.cli (student) and scripts/approve.py (instructor), built from
the same functions in harness.clients. Agent runs are streamed as Server-Sent Events (harness.api.events).

Identity is a demo: the frontend sends the acting student or instructor id with each call and nothing checks
it, exactly like `--student S1` on the CLI. The server binds to 127.0.0.1 only (harness.api.__main__). Inside a
run the agent's student comes from the session's owner, never from a request field (invariant 5).

Streaming endpoints check everything in a dependency first, so a refusal is a plain JSON error (403/404/409)
before any event is sent. The stream itself then only runs the agent.
"""

import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import closing
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langgraph.store.base import BaseStore
from langgraph.types import Command
from pydantic import BaseModel

from harness.api import views
from harness.api.events import RunTranslator, run_events
from harness.approvals import NotCourseOwner
from harness.cases import InvalidTransition
from harness.clients import (
    NotWaitingForInstructor,
    answer_confirmation,
    pending_actions,
    prepare_confirmation,
    record_instructor_decision,
)
from harness.mock_zambeel import UnknownStudent
from harness.workflow import WorkflowRefused

TITLE_CHARS = 60
STALE_RUN_SECONDS = 15 * 60  # a run lock older than this is treated as abandoned


class SendBody(BaseModel):
    student_id: str
    text: str


class ResumeBody(BaseModel):
    student_id: str
    decision: Literal["approve", "reject"] | None = None
    answer: str | None = None


class DecisionBody(BaseModel):
    instructor_id: str
    decision: Literal["approve", "reject"]
    reason: str | None = None


class NewSession(BaseModel):
    student_id: str


class ReadBody(BaseModel):
    ids: list[int]


class Runs:
    """At most one active run per session, and a stop flag for each."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, tuple[float, threading.Event]] = {}

    def start(self, session_id: str) -> threading.Event:
        with self._lock:
            active = self._active.get(session_id)
            if active and time.monotonic() - active[0] < STALE_RUN_SECONDS:
                raise HTTPException(409, f"Session {session_id} is already running.")
            stop = threading.Event()
            self._active[session_id] = (time.monotonic(), stop)
            return stop

    def finish(self, session_id: str) -> None:
        with self._lock:
            self._active.pop(session_id, None)

    def stop(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._active:
                self._active[session_id][1].set()


class Run:
    """Everything a stream needs, prepared (and authorized) before the response starts."""

    def __init__(self, translator: RunTranslator, payload: Any, stop: threading.Event, unattended: bool = False):
        self.translator, self.payload, self.stop, self.unattended = translator, payload, stop, unattended


def create_app(agent: Any = None, store: BaseStore | None = None) -> FastAPI:
    if agent is None:
        from harness.agent import build_agent
        from harness.config import load_env
        from harness.persistence import open_checkpointer, open_store

        load_env()
        store = store or open_store()
        agent = build_agent(checkpointer=open_checkpointer(), store=store)
    if store is None:
        from harness.persistence import open_store

        store = open_store()

    app = FastAPI(title="LUMS force-enrollment harness API")
    origins = os.environ.get("HARNESS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Accept"])
    runs = Runs()

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "; ".join(e["msg"] for e in exc.errors())}, status_code=422)

    def db() -> Iterator[sqlite3.Connection]:
        with closing(views.open_db()) as conn:
            yield conn

    Db = Annotated[sqlite3.Connection, Depends(db)]

    def owned_session(conn: sqlite3.Connection, session_id: str, student_id: str) -> None:
        owner = views.session_owner(conn, session_id)
        if owner is None:
            raise HTTPException(404, f"No session {session_id}.")
        if owner != student_id:
            raise HTTPException(403, f"Session {session_id} belongs to another student.")

    def stream(run: Run, session_id: str) -> Iterator[ServerSentEvent]:
        try:
            for event in run_events(agent, run.translator, run.payload, unattended=run.unattended, stop=run.stop):
                yield ServerSentEvent(data=event, event=event["type"])
        finally:
            runs.finish(session_id)

    # ------------------------------------------------------------------------------------------- people

    @app.get("/api/students")
    def list_students(conn: Db) -> list[dict[str, Any]]:
        return views.students(conn)

    @app.get("/api/instructors")
    def list_instructors(conn: Db) -> list[dict[str, Any]]:
        return views.instructors(conn)

    @app.get("/api/students/{student_id}/profile")
    def get_profile(student_id: str, conn: Db) -> dict[str, Any]:
        try:
            return views.profile(conn, student_id)
        except UnknownStudent as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/students/{student_id}/sessions")
    def list_sessions(student_id: str, conn: Db) -> list[dict[str, Any]]:
        return views.sessions_of(conn, agent, student_id)

    @app.get("/api/students/{student_id}/cases")
    def list_cases(student_id: str, conn: Db) -> list[dict[str, Any]]:
        return views.cases_of(conn, student_id)

    @app.get("/api/students/{student_id}/memory")
    def get_memory(student_id: str) -> dict[str, Any]:
        return views.memory(store, student_id)

    @app.get("/api/students/{recipient_id}/notifications")  # also serves instructor ids
    def list_notifications(recipient_id: str, conn: Db) -> list[dict[str, Any]]:
        return views.notifications_for(conn, recipient_id)

    @app.post("/api/notifications/read", status_code=204)
    def mark_read(body: ReadBody, conn: Db) -> Response:
        with conn:
            conn.executemany("UPDATE notifications SET read_at = ? WHERE notification_id = ? AND read_at IS NULL",
                             [(views.now(), i) for i in body.ids])
        return Response(status_code=204)

    # ------------------------------------------------------------------------------------------- sessions

    @app.post("/api/sessions")
    def create_session(body: NewSession, conn: Db) -> dict[str, Any]:
        if conn.execute("SELECT 1 FROM students WHERE student_id = ?", (body.student_id,)).fetchone() is None:
            raise HTTPException(404, f"No student {body.student_id}.")
        session_id = f"FE-{secrets.token_hex(4)}"
        with conn:
            conn.execute("INSERT INTO sessions VALUES (?, ?, NULL, ?, ?)",
                         (session_id, body.student_id, views.now(), views.now()))
        return views.session_view(conn, agent, session_id)

    @app.get("/api/sessions/{session_id}/messages")
    def get_messages(session_id: str, conn: Db) -> list[dict[str, Any]]:
        if views.session_owner(conn, session_id) is None:
            raise HTTPException(404, f"No session {session_id}.")
        return views.history(conn, agent, session_id)

    def prepare_message(session_id: str, body: SendBody, conn: Db) -> Run:
        owned_session(conn, session_id, body.student_id)
        if not body.text.strip():
            raise HTTPException(422, "The message is empty.")
        if pending_actions(agent, session_id):
            raise HTTPException(409, "This session is waiting for an answer; resume it instead.")
        stop = runs.start(session_id)
        with conn:
            conn.execute("UPDATE sessions SET title = COALESCE(title, ?), updated_at = ? WHERE session_id = ?",
                         (" ".join(body.text.split())[:TITLE_CHARS], views.now(), session_id))
        translator = RunTranslator(store, session_id=session_id, student_id=body.student_id, actor_id=body.student_id)
        return Run(translator, {"messages": [{"role": "user", "content": body.text}]}, stop)

    @app.post("/api/sessions/{session_id}/messages", response_class=EventSourceResponse)
    def send_message(session_id: str, run: Annotated[Run, Depends(prepare_message)]) -> Iterator[ServerSentEvent]:
        yield from stream(run, session_id)

    def prepare_resume(session_id: str, body: ResumeBody, conn: Db) -> Run:
        owned_session(conn, session_id, body.student_id)
        pending = pending_actions(agent, session_id)
        if body.decision is not None and pending == ["submit_case"]:
            args = next(a for i in agent.get_state({"configurable": {"thread_id": session_id}}).interrupts
                        for a in i.value["action_requests"])["args"]
        elif body.answer is not None and pending == ["ask_student"]:
            args = None
        else:
            raise HTTPException(409, f"Session {session_id} is not waiting for this answer.")
        stop = runs.start(session_id)
        try:
            translator = RunTranslator(store, session_id=session_id, student_id=body.student_id,
                                       actor_id=body.student_id)
            if args is None:
                decision = {"type": "respond", "message": body.answer.strip() or "(no answer)"}
            else:
                _, decision = prepare_confirmation(session_id, body.student_id, args)  # idempotent
                if decision is None:
                    decision = answer_confirmation(session_id, body.student_id, body.decision == "approve")
        except (WorkflowRefused, HTTPException) as exc:
            runs.finish(session_id)
            raise HTTPException(409, str(exc)) from exc
        except BaseException:
            runs.finish(session_id)
            raise
        return Run(translator, Command(resume={"decisions": [decision]}), stop)

    @app.post("/api/sessions/{session_id}/resume", response_class=EventSourceResponse)
    def resume(session_id: str, run: Annotated[Run, Depends(prepare_resume)]) -> Iterator[ServerSentEvent]:
        yield from stream(run, session_id)

    @app.post("/api/sessions/{session_id}/stop", status_code=204)
    def stop(session_id: str) -> Response:
        runs.stop(session_id)
        return Response(status_code=204)

    # ------------------------------------------------------------------------------------------- cases

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, conn: Db) -> dict[str, Any]:
        detail = views.case_detail(conn, case_id)
        if detail is None:
            raise HTTPException(404, f"No case {case_id}.")
        return detail

    @app.get("/api/instructors/{instructor_id}/pending")
    def list_pending(instructor_id: str, conn: Db) -> list[dict[str, Any]]:
        return views.pending_for(conn, instructor_id)

    @app.get("/api/instructors/{instructor_id}/decided")
    def list_decided(instructor_id: str, conn: Db) -> list[dict[str, Any]]:
        return views.decided_by(conn, instructor_id)

    def prepare_decision(case_id: str, body: DecisionBody, conn: Db) -> Run:
        case = views.get_case_row(conn, case_id)
        if case is None:
            raise HTTPException(404, f"No case {case_id}.")
        stop = runs.start(case_id)
        try:
            translator = RunTranslator(store, session_id=case_id, student_id=case["student_id"],
                                       actor_id=body.instructor_id)
            _, answer = record_instructor_decision(agent, case_id, body.instructor_id, body.decision, body.reason)
        except NotCourseOwner as exc:
            runs.finish(case_id)
            raise HTTPException(403, str(exc)) from exc
        except (NotWaitingForInstructor, InvalidTransition, WorkflowRefused) as exc:
            runs.finish(case_id)
            raise HTTPException(409, str(exc)) from exc
        except BaseException:
            runs.finish(case_id)
            raise
        # No student is present in this run: a new confirmation is declined, a question goes unanswered.
        return Run(translator, Command(resume={"decisions": [answer]}), stop, unattended=True)

    @app.post("/api/cases/{case_id}/decision", response_class=EventSourceResponse)
    def decision(case_id: str, run: Annotated[Run, Depends(prepare_decision)]) -> Iterator[ServerSentEvent]:
        yield from stream(run, case_id)

    return app

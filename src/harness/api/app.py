"""HTTP API for the web frontend (frontend/): the endpoints of docs/frontend-design-prompt.md, "API contract".

A third client of the same agent, next to harness.cli (student) and scripts/approve.py (instructor), built from
the same functions in harness.clients. Agent runs are streamed as Server-Sent Events (harness.api.events).

HARNESS_AUTH_MODE=demo retains the loopback demo. In entra mode the global dependency verifies the
harness API access token and authorizes every route before its handler runs. Claimed identity fields must
match that verified mapping. Browser login and authenticated downstream MCP acquisition are pending.

Streaming endpoints check everything in a dependency first, so a refusal is a plain JSON error (403/404/409)
before any event is sent. The dependency then starts the run in a worker thread; the SSE response only relays
its events. A run therefore never depends on the browser connection: closing the tab or switching views stops
the relay, not the agent (found live 2026-11-02: a dropped stream cut a run off between submit_case and
execute_enrollment, stranding the case). Only POST /stop ends a run early.
"""

import os
import queue
import secrets
import sqlite3
import threading
import time
import contextvars
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
from harness.api.auth import ApiAuthorization, configured_verifier
from harness.api.bff import configured_bff
from harness.mcp.client import call as mcp_call
from harness.mcp.authenticated import ReauthenticationRequired
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
from harness.mock_zambeel import UnknownStudent, ZambeelError
from harness.workflow import WorkflowRefused
from harness.reconciliation import reconcile_finished

TITLE_CHARS = 60
LOCAL_ORIGIN = r"http://(localhost|127\.0\.0\.1|\[::1\]):\d+"  # matched against the whole Origin header
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

    def idle(self, session_id: str) -> bool:
        with self._lock:
            return session_id not in self._active


class Run:
    """Everything a run needs, prepared (and authorized) before the response starts. `events` is filled by the
    worker thread once the run is launched; None marks the end."""

    def __init__(self, translator: RunTranslator, payload: Any, stop: threading.Event, unattended: bool = False):
        self.translator, self.payload, self.stop, self.unattended = translator, payload, stop, unattended
        self.events: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()


class DeferredAgent:
    """Let sign-in work before model credentials are provisioned. No mock fallback."""
    def __init__(self, factory):
        self.factory, self.value, self.lock = factory, None, threading.Lock()

    def __getattr__(self, name):
        with self.lock:
            if self.value is None:
                try:
                    self.value = self.factory()
                except Exception:
                    raise HTTPException(503, "Agent unavailable; configure the model and backend credentials") from None
        return getattr(self.value, name)


def create_app(agent: Any = None, store: BaseStore | None = None, *, verifier: Any = None, bff: Any = None) -> FastAPI:
    from harness.config import load_env
    load_env()
    bff = bff or configured_bff()
    authorization = ApiAuthorization(verifier if verifier is not None else configured_verifier(), bff)
    if agent is None:
        from harness.agent import build_agent
        from harness.persistence import open_checkpointer, open_store

        store = store or open_store()
        from harness.config import get_chat_model
        factory = lambda:build_agent(model=get_chat_model(), checkpointer=open_checkpointer(), store=store)
        agent = DeferredAgent(factory) if bff else factory()
    if store is None:
        from harness.persistence import open_store

        store = open_store()

    app = FastAPI(title="LUMS force-enrollment harness API", dependencies=[Depends(authorization)])
    app.state.bff = bff
    if bff:
        app.include_router(bff.router())
    else:
        @app.get("/auth/status")
        def demo_status():
            return {"mode":"entra" if authorization.verifier else "demo", "authenticated":False}
    # Any port on this machine (Vite moves to 5174 when 5173 is taken); HARNESS_CORS_ORIGINS adds exact origins.
    extra = [o.strip() for o in os.environ.get("HARNESS_CORS_ORIGINS", "").split(",") if o.strip()]
    if bff and "*" in extra:
        raise ValueError("BFF requires explicit frontend origins")
    app.add_middleware(CORSMiddleware, allow_origins=[*extra, *([bff.settings.frontend.rstrip('/')] if bff else [])],
                       allow_origin_regex=None if bff else LOCAL_ORIGIN, allow_credentials=bool(bff),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Accept", "Authorization", "X-CSRF-Token"])

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        if bff:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response
    runs = Runs()
    app.state.runs = runs  # tests wait on it (idle)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(ZambeelError)
    async def remote_error(request: Request, exc: ZambeelError):
        return JSONResponse({"error":"MCP operation unavailable or refused; retry or sign in again"}, status_code=502)

    @app.exception_handler(ReauthenticationRequired)
    async def reauthenticate(request: Request, exc: ReauthenticationRequired):
        return JSONResponse({"error":"Sign in again to continue; saved case state is retained"}, status_code=401)

    @app.get("/api/me")
    def current_user(request: Request):
        person = getattr(request.state, "principal", None)
        if person is None:
            return {"mode": "demo"}
        return {"mode": "bff" if bff else "entra", "actor_id": person.actor_id, "role": person.role}

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

    def launch(run: Run, session_id: str) -> Run:
        """Start the run in a worker thread. It runs to its own end (answer, pause, error or /stop) and only then
        frees the session's run lock, whether or not anyone is still reading the stream."""
        def work() -> None:
            try:
                for event in run_events(agent, run.translator, run.payload, unattended=run.unattended,
                                        stop=run.stop):
                    run.events.put(event)
            finally:
                runs.finish(session_id)
                run.events.put(None)

        try:
            context = contextvars.copy_context()
            threading.Thread(target=context.run, args=(work,), name=f"run-{session_id}", daemon=True).start()
        except BaseException:
            runs.finish(session_id)
            raise
        return run

    def stream(run: Run) -> Iterator[ServerSentEvent]:
        """Relay the worker's events. If the client goes away this generator is simply abandoned."""
        while (event := run.events.get()) is not None:
            yield ServerSentEvent(data=event, event=event["type"])

    def reconcile_owned(conn, student_id, case_id):
        row = views.get_case_row(conn, case_id)
        if row is None or row["state"] not in ("COMPLETED", "FAILED", "REJECTED", "CANCELLED") or not runs.idle(case_id):
            return
        if bff:
            # Confirm that the separately authenticated FE service agrees before
            # using its shared DB record to close a local graph pause.
            remote = mcp_call("fe", "get_case_status", {"case_id":case_id}, actor=student_id)
            if remote["case"]["state"] != row["state"]:
                raise HTTPException(409, "Case state is still being reconciled")
        reconcile_finished(conn, agent, store, case_id, student_id)

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
            if bff:
                return mcp_call("zambeel", "get_my_profile", actor=student_id)
            return views.profile(conn, student_id)
        except UnknownStudent as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/students/{student_id}/sessions")
    def list_sessions(student_id: str, conn: Db) -> list[dict[str, Any]]:
        if bff:
            for row in conn.execute("SELECT case_id FROM cases WHERE student_id = ?", (student_id,)).fetchall():
                reconcile_owned(conn, student_id, row[0])
        return views.sessions_of(conn, agent, student_id)

    @app.get("/api/students/{student_id}/cases")
    def list_cases(student_id: str, conn: Db) -> list[dict[str, Any]]:
        if bff:
            summaries = mcp_call("fe", "get_my_cases", actor=student_id)["cases"]
            return [views.remote_case_detail(conn, row["case_id"], student_id, "student")["case"] for row in summaries]
        return views.cases_of(conn, student_id)

    @app.get("/api/students/{student_id}/memory")
    def get_memory(student_id: str) -> dict[str, Any]:
        return views.memory(store, student_id)

    @app.get("/api/students/{recipient_id}/notifications")  # also serves instructor ids
    def list_notifications(recipient_id: str, conn: Db) -> list[dict[str, Any]]:
        if bff:
            raise HTTPException(503, "FE notification interface is not available yet")
        return views.notifications_for(conn, recipient_id)

    @app.post("/api/notifications/read", status_code=204)
    def mark_read(body: ReadBody, conn: Db) -> Response:
        if bff:
            raise HTTPException(503, "FE notification interface is not available yet")
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
        if bff:
            reconcile_owned(conn, views.session_owner(conn, session_id), session_id)
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
        return launch(Run(translator, {"messages": [{"role": "user", "content": body.text}]}, stop), session_id)

    @app.post("/api/sessions/{session_id}/messages", response_class=EventSourceResponse)
    def send_message(session_id: str, run: Annotated[Run, Depends(prepare_message)]) -> Iterator[ServerSentEvent]:
        yield from stream(run)

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
        return launch(Run(translator, Command(resume={"decisions": [decision]}), stop), session_id)

    @app.post("/api/sessions/{session_id}/resume", response_class=EventSourceResponse)
    def resume(session_id: str, run: Annotated[Run, Depends(prepare_resume)]) -> Iterator[ServerSentEvent]:
        yield from stream(run)

    @app.post("/api/sessions/{session_id}/stop", status_code=204)
    def stop(session_id: str) -> Response:
        runs.stop(session_id)
        return Response(status_code=204)

    # ------------------------------------------------------------------------------------------- cases

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, conn: Db, request: Request) -> dict[str, Any]:
        if bff:
            p = request.state.principal
            return views.remote_case_detail(conn, case_id, p.actor_id, p.role.lower())
        detail = views.case_detail(conn, case_id)
        if detail is None:
            raise HTTPException(404, f"No case {case_id}.")
        return detail

    @app.get("/api/instructors/{instructor_id}/pending")
    def list_pending(instructor_id: str, conn: Db) -> list[dict[str, Any]]:
        if bff:
            raise HTTPException(503, "FE instructor-list interface is not available yet; open an owned case by ID")
        return views.pending_for(conn, instructor_id)

    @app.get("/api/instructors/{instructor_id}/decided")
    def list_decided(instructor_id: str, conn: Db) -> list[dict[str, Any]]:
        if bff:
            raise HTTPException(503, "FE instructor-list interface is not available yet")
        return views.decided_by(conn, instructor_id)

    def prepare_decision(case_id: str, body: DecisionBody, conn: Db) -> Run:
        case = views.get_case_row(conn, case_id)
        if case is None:
            raise HTTPException(404, f"No case {case_id}.")
        stop = runs.start(case_id)
        if bff:
            try:
                mcp_call("fe", "decide_case", {"case_id":case_id, "decision":body.decision.upper(), "reason":body.reason},
                         actor=body.instructor_id, role="instructor")
                # FE owns atomic approval/outbox. Do not resume the student's
                # graph under instructor credentials or execute locally.
                run = Run(None, None, stop)
                identifier = secrets.token_hex(16)
                run.events.put({"type":"run.started", "run_id":identifier, "session_id":case_id})
                run.events.put({"type":"message.completed", "message":{"message_id":identifier,
                    "role":"assistant", "text":"Decision recorded. Approved enrollment is handled by the durable worker.",
                    "created_at":views.now()}})
                run.events.put({"type":"run.finished", "status":"answered"})
                run.events.put(None)
                return run
            finally:
                runs.finish(case_id)
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
        return launch(Run(translator, Command(resume={"decisions": [answer]}), stop, unattended=True), case_id)

    @app.post("/api/cases/{case_id}/decision", response_class=EventSourceResponse)
    def decision(case_id: str, run: Annotated[Run, Depends(prepare_decision)]) -> Iterator[ServerSentEvent]:
        yield from stream(run)

    return app

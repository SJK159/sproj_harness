"""One agent run -> the frontend's RunEvent stream (frontend/src/api/types.ts).

The agent is streamed with stream_mode="updates" and subgraphs=True:
  updates   one item per finished graph node: whole AI messages (with tool calls), tool results, todos, interrupts.
  subgraphs the eligibility checker runs inside the `task` tool; its events arrive under a ("tools:<id>",) namespace.
Text and reasoning are sent once per model call, not per token. Token streaming ("messages" mode) makes ChatOpenAI
call Databricks in streaming mode, and gpt-oss's streamed reply aggregates into a malformed content list that
Databricks rejects (400) when it is sent back on the next call (decisions.md, M9). Without it the model is called
exactly as the CLI calls it, so the checkpointed conversation is the same whichever client drives it.
Case, notification and memory events are not in the graph: after each tool step the database and the store are
read for rows added since the run started.

A pause ends the run. The HTTP API answers it with a later request (resume or decision), never inside this stream,
except where the answer is already known: a request that cannot be opened is refused at once, and a run with no
student present (the instructor's resume) declines confirmations and has no one to answer questions.
"""

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import closing
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.store.base import BaseStore
from langgraph.types import Command

from harness.api import views
from harness.clients import (
    NO_STUDENT_ANSWER,
    answer_confirmation,
    prepare_confirmation,
    unreviewed,
)
from harness.context import HarnessContext
from harness.memory import read_notes

log = logging.getLogger(__name__)

STREAM_MODE = "updates"  # not "messages": see the module docstring
ONE_AT_A_TIME = {"type": "reject", "message": "Call this tool on its own, not alongside other tool calls."}


class RunTranslator:
    """Folds one run's graph events into RunEvents and remembers what the final ChatMessage needs."""

    def __init__(self, store: BaseStore, *, session_id: str, student_id: str, actor_id: str):
        self.store, self.session_id, self.student_id, self.actor_id = store, session_id, student_id, actor_id
        self.run_id = uuid.uuid4().hex
        self.started = time.monotonic()
        self.steps: list[dict[str, Any]] = []        # top-level steps; sub-agent steps are their children
        self.by_id: dict[str, dict[str, Any]] = {}
        self.namespace_parent: dict[str, str | None] = {}
        self.unbound_tasks: list[str] = []          # task calls whose sub-agent has not streamed yet
        self.todos: list[dict[str, Any]] = []
        self.reasoning = ""
        self.final_text = ""
        self.verdict: dict[str, Any] | None = None
        self.case_states: list[str] = []
        self.limit_reached = False
        with closing(views.open_db()) as conn:
            self.last_event = conn.execute("SELECT COALESCE(MAX(event_id), 0) FROM audit_events WHERE case_id = ?",
                                           (session_id,)).fetchone()[0]
            self.last_notice = conn.execute("SELECT COALESCE(MAX(notification_id), 0) FROM notifications"
                                            " WHERE recipient_id = ?", (actor_id,)).fetchone()[0]
        self.notes = views.parse_notes(read_notes(store, student_id))
        self.known_cases = {n["case_id"] for n in self.notes}

    # ------------------------------------------------------------------------------------------- graph events

    def feed(self, namespace: tuple[str, ...], data: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for node, update in data.items():
            if node == "__interrupt__":
                continue
            for part in update if isinstance(update, list) else [update]:
                if isinstance(part, dict):
                    events += self._update(namespace, node, part)
            if node == "tools":
                events += self.poll()
        return events

    def _update(self, namespace: tuple[str, ...], node: str, update: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not namespace and isinstance(update.get("todos"), list):
            self.todos = update["todos"]
            events.append({"type": "todos.updated", "todos": self.todos})
        messages = update.get("messages")
        if not isinstance(messages, list):
            return events
        if not namespace and node.startswith("ModelCallLimitMiddleware") and messages:
            self.limit_reached = True  # the middleware ended the run with its own message
        for message in messages:
            if isinstance(message, AIMessage):
                events += self._calls(namespace, message)
            elif isinstance(message, ToolMessage):
                events += self._result(message)
        return events

    def _parent(self, namespace: tuple[str, ...]) -> str | None:
        if not namespace:
            return None
        key = namespace[0]
        if key not in self.namespace_parent:  # first event of a sub-agent run: bind it to the oldest open task
            self.namespace_parent[key] = self.unbound_tasks.pop(0) if self.unbound_tasks else None
        return self.namespace_parent[key]

    def _calls(self, namespace: tuple[str, ...], message: AIMessage) -> list[dict[str, Any]]:
        events = []
        if not namespace:  # the main agent's thinking and words, one model call at a time
            if reasoning := views.reasoning_text(message):
                self.reasoning += reasoning
                events.append({"type": "reasoning.delta", "text": reasoning})
            if text := views.message_text(message.content):
                self.final_text = text
                events.append({"type": "message.delta", "text": text})
        parent = self._parent(namespace)
        agent = "main" if not namespace else self.by_id.get(parent or "", {}).get("args", {}).get(
            "subagent_type", "eligibility-checker")
        for call in message.tool_calls:
            if call["name"] in views.HIDDEN_TOOLS or call["id"] in self.by_id:
                continue
            step = views.new_step(call, agent)
            self.by_id[call["id"]] = step
            started = {"type": "tool.started", "call_id": call["id"], "name": call["name"], "args": step["args"],
                       "agent": agent}
            if parent and parent in self.by_id:
                self.by_id[parent].setdefault("children", []).append(step)
                started["parent_call_id"] = parent
            else:
                self.steps.append(step)
            events.append(started)
            if call["name"] == "task":
                self.unbound_tasks.append(call["id"])
                events.append({"type": "subagent.started", "call_id": call["id"],
                               "name": step["args"].get("subagent_type", "eligibility-checker"),
                               "description": str(step["args"].get("description", ""))})
        return events

    def _result(self, message: ToolMessage) -> list[dict[str, Any]]:
        step = self.by_id.get(message.tool_call_id)
        if step is None or step["status"] != "running":
            return []
        ok, summary = views.tool_outcome(message)
        step.update(status="done" if ok else "error", summary=summary)
        events = [{"type": "tool.finished", "call_id": step["call_id"], "name": step["name"], "ok": ok,
                   "summary": summary}]
        if step["name"] == "task":
            if step["call_id"] in self.unbound_tasks:
                self.unbound_tasks.remove(step["call_id"])
            verdict = views.verdict_of(message)
            if verdict:
                self.verdict = verdict
                step["summary"] = verdict.get("summary") or summary
            events.append({"type": "subagent.finished", "call_id": step["call_id"], "verdict": verdict})
        return events

    def reopen(self, agent: Any) -> list[dict[str, Any]]:
        """On a resume: the paused message's tool calls that have no result yet are running again in this run
        (the call that waited, and a `task` whose sub-agent paused), so show them as steps of this turn."""
        state = agent.get_state({"configurable": {"thread_id": self.session_id}})
        messages = state.values.get("messages", []) if state.values else []
        answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
        last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last is None:
            return []
        open_calls = [c for c in last.tool_calls if c["id"] not in answered]
        return self._calls((), AIMessage(content="", tool_calls=open_calls))

    # ------------------------------------------------------------------------------------------- side effects

    def poll(self) -> list[dict[str, Any]]:
        """Audit rows of this case, notices to the acting person and memory notes added since the last poll."""
        events: list[dict[str, Any]] = []
        with closing(views.open_db()) as conn:
            rows = conn.execute("SELECT * FROM audit_events WHERE case_id = ? AND event_id > ? ORDER BY event_id",
                                (self.session_id, self.last_event)).fetchall()
            case = views.get_case_row(conn, self.session_id)
            for row in rows:
                self.last_event = row["event_id"]
                if row["to_state"] is None or row["to_state"] == row["from_state"] or case is None:
                    continue  # refusals and token checks are in the audit trail, not on the case lane
                snapshot = {**views.case_view(conn, case), "state": row["to_state"]}
                self.case_states.append(row["to_state"])
                events.append({"type": "case.updated", "case": snapshot, "event": views.audit_view(row)})
            for row in conn.execute("SELECT * FROM notifications WHERE recipient_id = ? AND notification_id > ?"
                                    " ORDER BY notification_id", (self.actor_id, self.last_notice)).fetchall():
                self.last_notice = row["notification_id"]
                events.append({"type": "notification.created", "notification": views.notification_view(row)})
        notes = views.parse_notes(read_notes(self.store, self.student_id))
        seen = {n["case_id"] for n in self.notes}
        for note in notes:
            if note["case_id"] not in seen:
                events.append({"type": "memory.updated", "student_id": self.student_id, "note": note})
        self.notes = notes
        return events

    # ------------------------------------------------------------------------------------------- end of run

    def completed(self, interrupt: dict[str, Any] | None = None) -> dict[str, Any]:
        steps = self.steps
        if interrupt:
            for step in self.by_id.values():
                if step["status"] == "running":
                    step["status"] = "paused"
        message: dict[str, Any] = {
            "message_id": self.run_id, "role": "assistant", "text": self.final_text, "created_at": views.now(),
            "thinking": {"todos": self.todos, "steps": steps, "reasoning": self.reasoning,
                         "duration_ms": int((time.monotonic() - self.started) * 1000),
                         "case_states": self.case_states},
        }
        if self.verdict:
            message["verdict"] = self.verdict
        if interrupt:
            message["interrupt"] = interrupt
        if any(case_id in self.final_text for case_id in self.known_cases):
            message["used_memory"] = True  # the reply cites a case known only from the student's notes
        return {"type": "message.completed", "message": message}


def run_events(agent: Any, translator: RunTranslator, payload: Any, *, unattended: bool,
               stop: threading.Event) -> Iterator[dict[str, Any]]:
    """Stream one run until it answers, pauses for a person, or fails. Yields RunEvent dicts."""
    t = translator
    config = {"configurable": {"thread_id": t.session_id}}
    context = HarnessContext(student_id=t.student_id)  # the session owner, never a request field (invariant 5)
    yield {"type": "run.started", "run_id": t.run_id, "session_id": t.session_id}
    if isinstance(payload, Command):
        yield from t.reopen(agent)
    yield from t.poll()  # what the request itself recorded (a confirmation, an instructor decision)
    try:
        while True:
            paused = None
            for namespace, data in agent.stream(payload, config=config, context=context,
                                                stream_mode=STREAM_MODE, subgraphs=True):
                if stop.is_set():
                    yield {"type": "run.finished", "status": "error", "error": "Stopped."}
                    return
                yield from t.feed(namespace, data)
                if not namespace and "__interrupt__" in data:
                    paused = data["__interrupt__"]
            if not paused:
                break
            actions = paused[0].value["action_requests"]
            if [a["name"] for a in actions] == ["execute_enrollment"]:
                with closing(views.open_db()) as conn:
                    waiting = views.interrupt_view(conn, t.session_id, actions[0])
                yield {"type": "interrupt", "interrupt": waiting}
                yield t.completed(waiting)
                yield {"type": "run.finished", "status": "waiting_for_instructor"}
                return
            decisions, ask = [], None
            for action in actions:
                decision, needs_person = _answer(t, action, unattended=unattended, alone=len(actions) == 1)
                yield from t.poll()
                if needs_person:
                    ask = action
                else:
                    decisions.append(decision)
            if ask is not None:
                with closing(views.open_db()) as conn:
                    interrupt = views.interrupt_view(conn, t.session_id, ask)
                yield {"type": "interrupt", "interrupt": interrupt}
                yield t.completed(interrupt)
                yield {"type": "run.finished", "status": "interrupted"}
                return
            payload = Command(resume={"decisions": decisions})
    except Exception as exc:  # the stream must end with run.finished; details go to the server log only
        log.exception("run failed on %s", t.session_id)
        yield {"type": "run.finished", "status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
        return
    yield t.completed()
    yield {"type": "run.finished", "status": "limit_reached" if t.limit_reached else "answered"}


def _answer(t: RunTranslator, action: dict[str, Any], *, unattended: bool, alone: bool) -> tuple[dict[str, Any] | None, bool]:
    """(decision, needs a person) for one paused call. A person is asked only for a call paused on its own."""
    name = action["name"]
    if name == "submit_case":
        _, decided = prepare_confirmation(t.session_id, t.student_id, action.get("args") or {})
        if decided is not None:
            return decided, False
        if unattended:
            return answer_confirmation(t.session_id, t.student_id, False), False
        return (None, True) if alone else (ONE_AT_A_TIME, False)
    if name == "ask_student":
        if unattended or not alone:
            return {"type": "respond", "message": NO_STUDENT_ANSWER}, False
        return None, True
    return unreviewed(name), False

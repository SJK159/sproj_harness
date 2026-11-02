"""Agent runs must not depend on the browser connection (found live 2026-11-02, case FE-ae9ec221).

The student confirmed, switched to the instructor view mid-run, and the dropped SSE connection cut the run off
after submit_case and before execute_enrollment: the case sat in AWAITING_APPROVAL with no instructor pause, so
the approval was refused (409). These tests use a real uvicorn server and a real HTTP disconnect, because
TestClient does not deliver one.
"""

import threading
import time
from contextlib import contextmanager

import httpx
import uvicorn
from api_helpers import api, events, lane, of, say, scripted, session
from case_helpers import enrollment_count
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage

from harness.api.app import create_app
from harness.cases import get_case
from harness.clients import pending_actions


class GatedModel(FakeToolCallingModel):
    """Scripted model that waits at a gate before each reply while the gate is closed."""

    def _generate(self, messages, *args, **kwargs):
        assert GATE.wait(10), "gate never opened"
        return super()._generate(messages, *args, **kwargs)


GATE = threading.Event()


@contextmanager
def serve(app):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)


def wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def submit_flow_model():
    return GatedModel(messages=iter([
        call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment"),
        call("notify_student", message="You are now enrolled in CS412-S1."), call("save_case_note"),
        AIMessage(content="done")]))


def test_run_continues_to_the_instructor_pause_after_the_browser_disconnects(flow):
    GATE.set()
    agent = flow.agent(submit_flow_model())
    app = create_app(agent=agent, store=flow.store())
    with serve(app) as base, httpx.Client(base_url=base, timeout=20) as http:
        sid = http.post("/api/sessions", json={"student_id": "S1"}).json()["session_id"]
        first = http.post(f"/api/sessions/{sid}/messages", json={"student_id": "S1", "text": "Submit CS412 S1."})
        assert "confirm_submission" in first.text  # paused for the student's confirmation

        GATE.clear()  # hold the agent at its next model call: after submit_case, before execute_enrollment
        with http.stream("POST", f"/api/sessions/{sid}/resume",
                         json={"student_id": "S1", "decision": "approve"}) as stream:
            next(stream.iter_lines())  # the run has started...
        # ...and the browser is gone (e.g. switched to the instructor view)
        time.sleep(0.5)
        busy = http.post(f"/api/sessions/{sid}/messages", json={"student_id": "S1", "text": "hello?"})
        assert busy.status_code == 409  # no second run starts while this one is unfinished
        GATE.set()

        assert wait_until(lambda: pending_actions(agent, sid) == ["execute_enrollment"]), \
            "the run stopped when the browser disconnected"
        assert get_case(flow.db, sid)["state"] == "AWAITING_APPROVAL"
        assert wait_until(lambda: app.state.runs.idle(sid))

        decided = http.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"})
        assert decided.status_code == 200 and '"COMPLETED"' in decided.text
    assert enrollment_count(flow.db, sid) == 1


def test_a_stranded_case_can_be_continued_by_the_student(flow):
    """Stranded = submitted, but the run ended without reaching execute_enrollment (an explicit Stop, a
    restart, or a model that ends its turn early). A student message continues it to the instructor pause."""
    GATE.set()
    client = api(flow, scripted(
        call("submit_case", course_id="CS412", section="S1"),
        AIMessage(content="Your request has been sent to the instructor."),  # ends without execute_enrollment
        call("execute_enrollment"),
        call("notify_student", message="You are now enrolled in CS412-S1."), call("save_case_note")))
    sid = session(client)
    say(client, sid, "Submit CS412 section S1.")
    events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "decision": "approve"}))
    assert get_case(flow.db, sid)["state"] == "AWAITING_APPROVAL"

    refused = client.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"})
    assert refused.status_code == 409
    assert flow.db.execute("SELECT COUNT(*) FROM approvals WHERE case_id = ?", (sid,)).fetchone()[0] == 0

    resumed = say(client, sid, "Please continue and wait for the instructor's decision.")
    assert of(resumed, "interrupt")[0]["interrupt"]["kind"] == "waiting_for_instructor"
    done = events(client.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"}))
    assert lane(done) == ["APPROVED", "EXECUTING", "COMPLETED"]
    assert enrollment_count(flow.db, sid) == 1

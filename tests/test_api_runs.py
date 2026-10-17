"""M9: agent runs over HTTP, streamed as the frontend's RunEvent contract (frontend/src/api/types.ts)."""

import re

import pytest
from api_helpers import api, events, lane, of, say, scripted, session, types
from case_helpers import FULL_PATH, audit_path, enrollment_count
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage
from test_subagents import VERDICT_S1

from harness.cases import get_case
from harness.integrity import audit_gaps, unauthorized_writes


def checker():
    return FakeToolCallingModel(messages=iter([
        call("check_my_eligibility", course_id="CS412", section="S1"),
        call("EligibilityVerdict", **VERDICT_S1), AIMessage(content="verdict")]))


def submit_flow(flow):
    main = scripted(call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment"),
                    call("notify_student", message="You are now enrolled in CS412-S1."), call("save_case_note"))
    return api(flow, main)


def to_instructor(client):
    """S1 submits CS412-S1 and confirms; the case ends AWAITING_APPROVAL. Returns (session id, both streams)."""
    sid = session(client)
    first = say(client, sid, "Submit CS412 section S1.")
    second = events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "decision": "approve"}))
    return sid, first, second


def decide(client, sid, instructor, decision, reason=None):
    return client.post(f"/api/cases/{sid}/decision",
                       json={"instructor_id": instructor, "decision": decision, "reason": reason})


def test_eligibility_question_streams_plan_subagent_steps_and_verdict(flow):
    main = scripted(call("write_todos", todos=[{"content": "Check eligibility", "status": "in_progress"}]),
                    call("task", description="Check CS412 S1 for S1.", subagent_type="eligibility-checker"),
                    AIMessage(content="You can request force enrollment in CS412-S1."))
    client = api(flow, main, checker())
    sid = session(client)
    evs = say(client, sid, "Can I get force enrolled in CS412?")

    assert types(evs)[0] == "run.started" and evs[0]["session_id"] == sid
    assert evs[-1] == {"type": "run.finished", "status": "answered"}
    assert of(evs, "todos.updated")[0]["todos"] == [{"content": "Check eligibility", "status": "in_progress"}]
    task = of(evs, "subagent.started")[0]
    assert task["name"] == "eligibility-checker" and "CS412" in task["description"]
    inner = [e for e in of(evs, "tool.started") if e["agent"] == "eligibility-checker"]
    assert [e["name"] for e in inner] == ["check_my_eligibility"]
    assert inner[0]["parent_call_id"] == task["call_id"]
    assert all(e["name"] not in ("write_todos", "EligibilityVerdict") for e in of(evs, "tool.started"))
    finished = {e["call_id"]: e for e in of(evs, "tool.finished")}
    assert finished[inner[0]["call_id"]]["ok"] is True
    verdict = of(evs, "subagent.finished")[0]["verdict"]
    assert verdict["sections"][0]["offering_id"] == "CS412-S1" and verdict["sections"][0]["can_submit"] is True
    done = of(evs, "message.completed")[0]["message"]
    assert done["role"] == "assistant" and done["text"] == "You can request force enrollment in CS412-S1."
    assert done["verdict"]["course_id"] == "CS412"
    assert [s["name"] for s in done["thinking"]["steps"]] == ["task"]
    assert [c["name"] for c in done["thinking"]["steps"][0]["children"]] == ["check_my_eligibility"]
    assert of(evs, "case.updated") == []  # a question never creates a case


def test_submit_pauses_for_confirmation_then_for_the_instructor(flow):
    client = submit_flow(flow)
    sid, first, second = to_instructor(client)

    assert lane(first) == ["DRAFT", "AWAITING_CONFIRMATION"]
    pause = of(first, "interrupt")[0]["interrupt"]
    assert pause["kind"] == "confirm_submission" and pause["case_id"] == sid and pause["offering_id"] == "CS412-S1"
    assert pause["description"]
    assert first[-1] == {"type": "run.finished", "status": "interrupted"}

    assert lane(second) == ["SUBMITTED", "AWAITING_APPROVAL"]
    wait = of(second, "interrupt")[0]["interrupt"]
    assert wait == {"kind": "waiting_for_instructor", "case_id": sid, "instructor_id": "I1",
                    "description": wait["description"]}
    assert second[-1] == {"type": "run.finished", "status": "waiting_for_instructor"}
    assert of(second, "notification.created") == []  # I1's notice is not shown to the student
    assert get_case(flow.db, sid)["state"] == "AWAITING_APPROVAL"

    listed = {s["session_id"]: s for s in client.get("/api/students/S1/sessions").json()}
    assert listed[sid]["pending_interrupt"]["kind"] == "waiting_for_instructor"
    assert listed[sid]["case"]["state"] == "AWAITING_APPROVAL"
    assert listed[sid]["title"] == "CS412-S1 force enrollment"


def test_wrong_instructor_is_refused_and_owner_approval_completes_once(flow):
    client = submit_flow(flow)
    sid, _, _ = to_instructor(client)

    refused = decide(client, sid, "I2", "approve")
    assert refused.status_code == 403 and "I2" in refused.json()["error"]
    assert get_case(flow.db, sid)["state"] == "AWAITING_APPROVAL"
    assert flow.db.execute("SELECT COUNT(*) FROM approvals WHERE case_id = ?", (sid,)).fetchone()[0] == 0

    evs = events(decide(client, sid, "I1", "approve"))
    assert lane(evs) == ["APPROVED", "EXECUTING", "COMPLETED"]
    assert evs[-1] == {"type": "run.finished", "status": "answered"}
    assert of(evs, "memory.updated")[0]["note"]["case_id"] == sid
    assert of(evs, "memory.updated")[0]["note"]["outcome"] == "COMPLETED"
    assert {e["notification"]["recipient_id"] for e in of(evs, "notification.created")} <= {"I1"}
    assert audit_path(flow.db, sid) == FULL_PATH
    assert enrollment_count(flow.db, sid) == 1

    again = decide(client, sid, "I1", "approve")  # nothing is waiting any more
    assert again.status_code == 409
    assert enrollment_count(flow.db, sid) == 1
    assert audit_gaps(flow.db) == [] and unauthorized_writes(flow.db) == []


def test_decline_at_confirmation_cancels(flow):
    client = submit_flow(flow)
    sid = session(client)
    say(client, sid, "Submit CS412 section S1.")
    evs = events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "decision": "reject"}))
    assert lane(evs) == ["CANCELLED"]
    assert evs[-1]["status"] == "answered"
    assert get_case(flow.db, sid)["state"] == "CANCELLED"


def test_instructor_rejection_with_reason(flow):
    client = submit_flow(flow)
    sid, _, _ = to_instructor(client)
    evs = events(decide(client, sid, "I1", "reject", "Section is over capacity."))
    assert lane(evs) == ["REJECTED"]
    notice = client.get("/api/students/S1/notifications").json()
    assert any(n["kind"] == "REJECTED" and "Section is over capacity." in n["message"] for n in notice)
    assert enrollment_count(flow.db, sid) == 0


def test_ineligible_request_never_reaches_confirmation(flow):
    main = scripted(call("submit_case", course_id="CS412", section="S1"))
    client = api(flow, main)
    sid = session(client, "S2")  # S2 is missing CS310
    evs = say(client, sid, "Submit CS412 section S1.", student="S2")
    assert of(evs, "interrupt") == [] and of(evs, "case.updated") == []
    assert evs[-1]["status"] == "answered"


def test_checker_question_is_asked_over_http_and_the_answer_resumes(flow):
    main = scripted(call("task", description="Check the ML course for S1.", subagent_type="eligibility-checker"),
                    AIMessage(content="CS412-S1 is open to a force-enrollment request."))
    sub = FakeToolCallingModel(messages=iter([
        call("ask_student", question="Which course code do you mean?"),
        call("check_my_eligibility", course_id="CS412", section="S1"),
        call("EligibilityVerdict", **VERDICT_S1), AIMessage(content="verdict")]))
    client = api(flow, main, sub)
    sid = session(client)
    first = say(client, sid, "Can I get into the machine learning course?")
    assert of(first, "interrupt")[0]["interrupt"] == {"kind": "ask_student", "question": "Which course code do you mean?"}
    assert first[-1]["status"] == "interrupted"

    second = events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "answer": "CS412"}))
    task = of(second, "subagent.started")[0]  # the paused task call is running again in this turn
    inner = [e for e in of(second, "tool.started") if e["agent"] == "eligibility-checker"]
    assert [(e["name"], e["parent_call_id"]) for e in inner] == [
        ("ask_student", task["call_id"]), ("check_my_eligibility", task["call_id"])]
    answered = next(e for e in of(second, "tool.finished") if e["call_id"] == inner[0]["call_id"])
    assert answered["summary"] == "CS412"  # the student's answer is the question's result
    assert of(second, "subagent.finished")[0]["verdict"]["sections"][0]["offering_id"] == "CS412-S1"
    assert second[-1]["status"] == "answered"


def test_run_limit_is_reported(flow, monkeypatch):
    monkeypatch.setattr("harness.agent.MAX_MODEL_CALLS_PER_RUN", 2)
    main = scripted(*[call("get_my_profile") for _ in range(5)])
    client = api(flow, main)
    sid = session(client)
    evs = say(client, sid, "How many credits am I taking?")
    assert evs[-1]["type"] == "run.finished" and evs[-1]["status"] == "limit_reached"


@pytest.mark.parametrize("path, body, status", [
    ("/api/sessions/{sid}/messages", {"student_id": "S2", "text": "hi"}, 403),        # not this session's student
    ("/api/sessions/{sid}/resume", {"student_id": "S1", "decision": "approve"}, 409),  # nothing is paused
    ("/api/sessions/{sid}/resume", {"student_id": "S2", "decision": "approve"}, 403),
    ("/api/sessions/FE-00000000/messages", {"student_id": "S1", "text": "hi"}, 404),
    ("/api/cases/{sid}/decision", {"instructor_id": "I1", "decision": "approve"}, 404),  # no case yet
])
def test_guards(flow, path, body, status):
    client = api(flow, scripted())
    sid = session(client)
    r = client.post(path.format(sid=sid), json=body)
    assert r.status_code == status and r.json()["error"]


def test_decision_on_a_case_not_waiting_is_refused(flow):
    client = submit_flow(flow)
    sid = session(client)
    say(client, sid, "Submit CS412 section S1.")  # paused at confirmation, not at the instructor
    r = decide(client, sid, "I1", "approve")
    assert r.status_code == 409
    assert flow.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


def test_new_session_ids_are_case_ids(flow):
    client = api(flow, scripted())
    sid = session(client)
    assert re.fullmatch(r"FE-[0-9a-f]{8}", sid)
    created = next(s for s in client.get("/api/students/S1/sessions").json() if s["session_id"] == sid)
    assert created["case"] is None and created["pending_interrupt"] is None
    assert client.get("/api/students/S2/sessions").json() == []

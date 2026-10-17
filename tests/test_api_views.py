"""M9: read endpoints of the HTTP API (shapes from frontend/src/api/types.ts)."""

from api_helpers import api, events, say, scripted, session
from fakes import call
from langchain_core.messages import AIMessage

from harness.memory import append_note

CASE_KEYS = {"case_id", "student_id", "offering_id", "state", "next_action", "flag", "created_at", "updated_at"}


def approved_case(flow):
    """S1's CS412-S1 case, approved by I1 and completed, driven through the API."""
    client = api(flow, scripted(call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment")))
    sid = session(client)
    say(client, sid, "Submit CS412 section S1.")
    events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "decision": "approve"}))
    events(client.post(f"/api/cases/{sid}/decision", json={"instructor_id": "I1", "decision": "approve"}))
    return client, sid


def test_people(flow):
    client = api(flow, scripted())
    students = {s["student_id"]: s for s in client.get("/api/students").json()}
    assert set(students) == {f"S{i}" for i in range(1, 10)}  # fillers S90-S93 are not demo users
    assert students["S1"]["name"] and students["S1"]["hint"]
    instructors = {i["instructor_id"]: i for i in client.get("/api/instructors").json()}
    assert set(instructors) == {"I1", "I2", "I3", "I4"}
    assert {"CS412-S1", "CS412-S2"} <= set(instructors["I1"]["sections"])


def test_profile(flow):
    client = api(flow, scripted())
    profile = client.get("/api/students/S6/profile").json()
    assert profile["student_id"] == "S6" and profile["on_probation"] is True
    assert set(profile) == {"student_id", "name", "program", "year", "cgpa", "on_probation", "completed",
                            "enrollments", "credits"}
    assert client.get("/api/students/S404/profile").status_code == 404


def test_case_views_after_a_completed_case(flow):
    client, sid = approved_case(flow)

    cases = client.get("/api/students/S1/cases").json()
    assert [c["case_id"] for c in cases] == [sid] and set(cases[0]) == CASE_KEYS
    assert client.get("/api/students/S2/cases").json() == []

    detail = client.get(f"/api/cases/{sid}").json()
    assert detail["case"]["state"] == "COMPLETED" and detail["instructor_id"] == "I1"
    assert detail["approval"]["instructor_id"] == "I1" and detail["approval"]["decision"] == "APPROVE"
    assert "token" not in detail["approval"]  # the signed token never leaves the server
    assert detail["enrollment"]["kind"] == "FORCE"
    routed = next(e for e in detail["audit"] if e["action"] == "ROUTE_TO_INSTRUCTOR")
    snapshot = routed["detail"]["eligibility"]
    assert snapshot["cgpa"] == profile_cgpa(client) and snapshot["fe_slots"] == "0 of 3 used"
    assert client.get("/api/cases/FE-00000000").status_code == 404

    assert client.get("/api/instructors/I1/pending").json() == []
    assert [c["case_id"] for c in client.get("/api/instructors/I1/decided").json()] == [sid]
    assert client.get("/api/instructors/I2/decided").json() == []

    inbox = client.get("/api/students/I1/notifications").json()  # instructors use the same inbox endpoint
    assert [n["kind"] for n in inbox] == ["APPROVAL_REQUESTED"]
    r = client.post("/api/notifications/read", json={"ids": [inbox[0]["notification_id"]]})
    assert r.status_code == 204
    assert client.get("/api/students/I1/notifications").json()[0]["read_at"]


def profile_cgpa(client):
    return client.get("/api/students/S1/profile").json()["cgpa"]


def test_pending_list_for_the_owner_only(flow):
    client = api(flow, scripted(call("submit_case", course_id="CS412", section="S1"), call("execute_enrollment")))
    sid = session(client)
    say(client, sid, "Submit CS412 section S1.")
    events(client.post(f"/api/sessions/{sid}/resume", json={"student_id": "S1", "decision": "approve"}))
    assert [c["case_id"] for c in client.get("/api/instructors/I1/pending").json()] == [sid]
    assert client.get("/api/instructors/I2/pending").json() == []


def test_memory_notes_are_parsed(flow):
    store = flow.store()
    append_note(store, "S1", "FE-11111111",
                "- 2026-10-01 FE-11111111: force enrollment in CS412-S1 COMPLETED (approved by I1; force enrollment).")
    client = api(flow, scripted())
    memory = client.get("/api/students/S1/memory").json()
    assert memory["student_id"] == "S1"
    assert memory["notes"] == [{"date": "2026-10-01", "case_id": "FE-11111111", "offering_id": "CS412-S1",
                                "outcome": "COMPLETED", "detail": "approved by I1; force enrollment",
                                "raw": "- 2026-10-01 FE-11111111: force enrollment in CS412-S1 COMPLETED "
                                       "(approved by I1; force enrollment)."}]
    assert client.get("/api/students/S2/memory").json() == {"student_id": "S2", "notes": []}


def test_message_history_is_rebuilt_from_the_checkpoint(flow):
    client = api(flow, scripted(call("get_my_profile"), AIMessage(content="You are taking 15 credits.")))
    sid = session(client)
    say(client, sid, "How many credits am I taking?")
    history = client.get(f"/api/sessions/{sid}/messages").json()
    assert [(m["role"], m["text"]) for m in history] == [
        ("user", "How many credits am I taking?"), ("assistant", "You are taking 15 credits.")]
    assert [s["name"] for s in history[1]["thinking"]["steps"]] == ["get_my_profile"]
    assert history[1]["thinking"]["steps"][0]["status"] == "done"
    titled = next(s for s in client.get("/api/students/S1/sessions").json() if s["session_id"] == sid)
    assert titled["title"] == "How many credits am I taking?"


def test_request_connection_can_move_between_threads(seeded):
    """FastAPI runs a request's dependency and its endpoint on different worker threads (found live in M9)."""
    import threading
    from contextlib import closing

    from harness.api.views import open_db

    with closing(open_db()) as conn:
        result = []
        worker = threading.Thread(target=lambda: result.append(conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]))
        worker.start()
        worker.join()
        assert result and result[0] > 0


def test_cors_allows_any_local_dev_port_only(flow):
    """Vite moves to 5174 when 5173 is taken; the browser then blocked every call (found in Safari)."""
    client = api(flow, scripted())
    for origin in ("http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:4173"):
        r = client.get("/api/students", headers={"Origin": origin})
        assert r.headers.get("access-control-allow-origin") == origin
    for origin in ("http://evil.example", "http://localhost.evil.example:5173"):
        r = client.get("/api/students", headers={"Origin": origin})
        assert "access-control-allow-origin" not in r.headers

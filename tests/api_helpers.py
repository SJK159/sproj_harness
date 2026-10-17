"""Helpers for the HTTP API tests: an app around a fake-model agent, and SSE parsing."""

import json

from fakes import FakeToolCallingModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage


def scripted(*messages):
    return FakeToolCallingModel(messages=iter([*messages, AIMessage(content="done")]))


def api(flow, main, sub=None):
    from harness.api.app import create_app

    agent = flow.agent(main, subagent_model=sub) if sub is not None else flow.agent(main)
    return TestClient(create_app(agent=agent, store=flow.store()))


def events(response) -> list[dict]:
    """Parse a text/event-stream body into RunEvent dicts; checks each frame's `event:` matches its type."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    out = []
    for frame in response.text.replace("\r\n", "\n").split("\n\n"):
        lines = frame.split("\n")
        data = "\n".join(line[5:].lstrip(" ") for line in lines if line.startswith("data:"))
        if not data:
            continue
        event = json.loads(data)
        named = [line[6:].strip() for line in lines if line.startswith("event:")]
        assert named == [event["type"]], frame
        out.append(event)
    return out


def types(evs):
    return [e["type"] for e in evs]


def of(evs, kind):
    return [e for e in evs if e["type"] == kind]


def lane(evs):
    return [e["case"]["state"] for e in of(evs, "case.updated")]


def session(client, student="S1"):
    r = client.post("/api/sessions", json={"student_id": student})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def say(client, sid, text, student="S1"):
    return events(client.post(f"/api/sessions/{sid}/messages", json={"student_id": student, "text": text}))

from api_helpers import scripted, session, say, events
from fakes import call

from harness import workflow
from harness.approvals import decide
from harness.clients import pending_actions
from harness.memory import read_notes
from harness.reconciliation import reconcile_finished


def test_worker_result_closes_pause_and_saves_memory_without_model_call(flow):
    model = scripted(call("submit_case",course_id="CS412",section="S1"), call("execute_enrollment"))
    agent = flow.agent(model)
    from fastapi.testclient import TestClient
    from harness.api.app import create_app
    store = flow.store()
    client = TestClient(create_app(agent, store))
    sid = session(client)
    say(client,sid,"Submit CS412 S1")
    events(client.post(f"/api/sessions/{sid}/resume",json={"student_id":"S1","decision":"approve"}))
    assert pending_actions(agent,sid) == ["execute_enrollment"]
    assert not reconcile_finished(flow.db,agent,store,sid,"S1")  # No approval yet.
    decide(flow.db,sid,"I1","APPROVE")
    assert not reconcile_finished(flow.db,agent,store,sid,"S1")  # Approval is not enrollment.
    workflow.execute(flow.db,sid,"S1")  # Simulated FE worker, real deterministic gates.
    assert not reconcile_finished(flow.db,agent,store,sid,"S2")
    assert reconcile_finished(flow.db,agent,store,sid,"S1")
    state = agent.get_state({"configurable":{"thread_id":sid}})
    assert state.interrupts == () and state.next == ()
    assert "COMPLETED" in state.values["messages"][-1].content
    assert read_notes(store,"S1").count(f" {sid}:") == 1
    assert read_notes(store,"S2") == ""
    assert not reconcile_finished(flow.db,agent,store,sid,"S1")
    restarted = flow.agent(scripted())
    assert pending_actions(restarted,sid) == []

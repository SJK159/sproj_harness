from deepagents.middleware.summarization import compute_summarization_defaults
from fakes import FakeToolCallingModel, call
from langchain_core.messages import AIMessage, ToolMessage

from harness.agent import DEMO_TRIGGER_TOKENS
from harness.clients import student_turn
from harness.config import get_chat_model
from harness.context import HarnessContext


def test_databricks_model_declares_its_context_window(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL", "databricks:databricks-gpt-oss-120b")
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    model = get_chat_model()
    assert model.profile["max_input_tokens"] == 128_000
    assert compute_summarization_defaults(model)["trigger"] == ("fraction", 0.85)  # was ("tokens", 170000)


def test_demo_mode_offloads_a_large_tool_result(flow):
    for i in range(15):  # enough rows that get_my_cases returns well over DEMO_EVICT_TOKENS
        flow.db.execute("INSERT INTO cases (case_id, student_id, offering_id, type, state, created_at, updated_at)"
                        " VALUES (?, 'S1', 'CS412-S1', 'FORCE_ENROLLMENT', 'CANCELLED', 'now', 'now')", (f"FE-old{i:02}",))
    flow.db.commit()
    model = FakeToolCallingModel(messages=iter([call("get_my_cases"), AIMessage(content="done")]))
    agent = flow.agent(model, compression="demo")
    result = agent.invoke({"messages": [{"role": "user", "content": "list my cases"}]},
                          config={"configurable": {"thread_id": "FE-c1"}}, context=HarnessContext(student_id="S1"))
    reply = next(m.content for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "get_my_cases")
    assert "/large_tool_results/" in reply and "FE-old14" not in reply  # replaced by a pointer
    files = agent.get_state({"configurable": {"thread_id": "FE-c1"}}).values.get("files", {})
    assert any(path.startswith("/large_tool_results/") for path in files)


def test_demo_mode_summarizes_a_long_conversation(flow):
    long_text = "lorem ipsum " * 300  # about 900 tokens per message
    model = FakeToolCallingModel(messages=iter([AIMessage(content=f"reply {i}: {long_text}") for i in range(30)]))
    summarizer = FakeToolCallingModel(messages=iter([AIMessage(content=f"SUMMARY {i}") for i in range(10)]))
    agent = flow.agent(model, compression="demo", summary_model=summarizer)
    for i in range(10):
        student_turn(agent, "FE-c2", "S1", f"message {i}: {long_text}", confirm=lambda s: False)
    values = agent.get_state({"configurable": {"thread_id": "FE-c2"}}).values
    assert values.get("_summarization_event")
    assert any(path.startswith("/conversation_history/") for path in values.get("files", {}))
    assert any("SUMMARY" in m.text for m in model.seen[-1])  # the model now sees the summary, not the old turns
    assert DEMO_TRIGGER_TOKENS < 128_000

def test_model_call_limit_stops_a_runaway_loop(flow):
    """The M8 bug: the agent re-read the skill 164 times. Any run is now capped."""
    from harness.agent import MAX_MODEL_CALLS_PER_RUN

    loop = [call("read_file", file_path="/skills/force-enrollment/SKILL.md") for _ in range(MAX_MODEL_CALLS_PER_RUN + 20)]
    model = FakeToolCallingModel(messages=iter([*loop, AIMessage(content="never reached")]))
    student_turn(flow.agent(model), "FE-loop", "S1", "can i get into CS412?", confirm=lambda s: False)
    assert len(model.seen) == MAX_MODEL_CALLS_PER_RUN

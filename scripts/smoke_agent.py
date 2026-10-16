"""M0 throwaway: confirm deps, model access, tool calling and LangSmith tracing.

Two runs of a bare deep agent:
1. one plain message;
2. one message that needs a custom tool, to check the model's tool calls work through deepagents.

Replaced by harness.agent in M3.
"""

import os

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from harness.config import get_chat_model, get_model_name, load_env


@tool
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


def main() -> None:
    load_env()
    tracing = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
    print(f"model: {get_model_name()}")
    print(f"langsmith tracing: {'on' if tracing else 'off'} (project: {os.environ.get('LANGSMITH_PROJECT', 'default')})")
    model = get_chat_model()

    agent = create_deep_agent(model=model, system_prompt="You are a smoke-test agent. Answer in one sentence.")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Say hello and name the model provider you run on."}]},
        config={"run_name": "m0-smoke", "tags": ["m0-smoke"]},
    )
    print(f"\n[1] reply: {result['messages'][-1].text}")

    agent = create_deep_agent(
        model=model,
        tools=[add],
        system_prompt="You are a smoke-test agent. Use the add tool for arithmetic. Answer in one sentence.",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "What is 19 + 23? Use the add tool."}]},
        config={"run_name": "m0-smoke-tools", "tags": ["m0-smoke"]},
    )
    calls = [c for m in result["messages"] if isinstance(m, AIMessage) for c in m.tool_calls]
    tool_results = [m.content for m in result["messages"] if isinstance(m, ToolMessage)]
    print(f"\n[2] tool calls: {[(c['name'], c['args']) for c in calls]}")
    print(f"[2] tool results: {tool_results}")
    print(f"[2] reply: {result['messages'][-1].text}")
    if not any(c["name"] == "add" for c in calls):
        raise SystemExit("FAIL: the model did not call the add tool")


if __name__ == "__main__":
    main()

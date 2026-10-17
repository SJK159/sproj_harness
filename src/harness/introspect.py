"""Inspect a built agent: which tools the main agent and each sub-agent can call.

Relies on deepagents internals (pinned 0.7.28): the compiled sub-agent graphs are only reachable
through the `task` tool's closure. Used by tests and scripts/list_agent_tools.py, never at runtime.
"""

import inspect
from typing import Any


def _tools_of(graph: Any) -> list[str]:
    return sorted(graph.get_graph().nodes["tools"].data.tools_by_name)


def subagent_graphs(agent: Any) -> dict[str, Any]:
    tools = agent.get_graph().nodes["tools"].data.tools_by_name
    if "task" not in tools:
        return {}
    return dict(inspect.getclosurevars(tools["task"].func).nonlocals["subagent_graphs"])


def agent_tool_map(agent: Any) -> dict[str, list[str]]:
    return {"main": _tools_of(agent), **{name: _tools_of(g) for name, g in subagent_graphs(agent).items()}}

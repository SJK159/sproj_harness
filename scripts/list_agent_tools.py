"""Print every tool the main agent and each sub-agent can call (CLAUDE.md invariant 9).

Builds the agent for the configured HARNESS_MODEL; makes no model call.

    uv run python scripts/list_agent_tools.py
"""

import sys

from harness.agent import build_agent
from harness.config import load_env
from harness.introspect import agent_tool_map
from harness.tools import FILE_WRITE_TOOL_NAMES, WRITE_TOOL_NAMES


def main() -> int:
    load_env()
    tool_map = agent_tool_map(build_agent())
    failures = []
    for agent_name, tools in tool_map.items():
        print(f"{agent_name}:")
        for name in tools:
            flag = ""
            if agent_name != "main" and name in WRITE_TOOL_NAMES | FILE_WRITE_TOOL_NAMES | {"task"}:
                flag = "   <-- not allowed on a sub-agent"
                failures.append(f"{agent_name}.{name}")
            print(f"  {name}{flag}")
    if "general-purpose" in tool_map:
        failures.append("general-purpose sub-agent is present")
    print("\nOK: no write tools on any sub-agent" if not failures else f"\nFAIL: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

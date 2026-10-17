"""Deterministic guards for two observed gpt-oss / Databricks failure modes (2026-10-17 live runs).

1. A turn that ends with reasoning only: no text and no tool call, e.g. reasoning "Let's call task."
   and nothing else. The agent loop would stop there. `NudgeEmptyTurn` sends the model back once or twice.
2. Structured output written as JSON text instead of the forced `EligibilityVerdict` tool call:
   Databricks receives `tool_choice: required` but does not enforce it for gpt-oss. `StructuredFromText`
   validates that text against the schema; if it doesn't validate, it asks once for the tool call.

Nudges are HumanMessages named "harness-nudge" so they are easy to spot in traces.
"""

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ValidationError

NUDGE_NAME = "harness-nudge"


def _nudges_this_turn(messages: list) -> int:
    count = 0
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            if m.name != NUDGE_NAME:
                break
            count += 1
    return count


def _nudge(text: str) -> dict[str, Any]:
    return {"messages": [HumanMessage(content=text, name=NUDGE_NAME)], "jump_to": "model"}


class NudgeEmptyTurn(AgentMiddleware):
    """Re-prompt when the model ends a turn with neither text nor a tool call."""

    def __init__(self, max_nudges: int = 2) -> None:
        super().__init__()
        self.max_nudges = max_nudges

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or last.tool_calls or last.text.strip():
            return None
        if _nudges_this_turn(state["messages"]) >= self.max_nudges:
            return None
        return _nudge("Your last turn had no message and no tool call. Make the tool call you planned, "
                      "or give your answer.")


def _json_object(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return text[start:end + 1]


class StructuredFromText(AgentMiddleware):
    """Accept a schema-valid JSON reply as the structured response when the model skips the tool call."""

    def __init__(self, schema: type[BaseModel], max_nudges: int = 1) -> None:
        super().__init__()
        self.schema = schema
        self.max_nudges = max_nudges

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        if state.get("structured_response") is not None:
            return None
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or last.tool_calls:
            return None
        try:
            return {"structured_response": self.schema.model_validate_json(_json_object(last.text))}
        except (ValueError, ValidationError):
            if _nudges_this_turn(state["messages"]) >= self.max_nudges:
                return None
            return _nudge(f"Call the `{self.schema.__name__}` tool now with your result. Do not write it as text.")

import json

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import Field


class FakeToolCallingModel(GenericFakeChatModel):
    """Scripted model: replies with the given messages in order and records every input it was sent."""

    seen: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


def call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])


def scripted(*messages):
    return FakeToolCallingModel(messages=iter([*messages, AIMessage(content="done")]))


def tool_results(result):
    return {m.name: m.content for m in result["messages"] if isinstance(m, ToolMessage)}


def tool_json(result, name):
    return json.loads(tool_results(result)[name])
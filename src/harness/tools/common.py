"""Helpers shared by the agent tools: who is calling, which case, and JSON results."""

import json
from collections.abc import Callable
from typing import Any

from langchain.tools import ToolRuntime

from harness.cases import UnknownCase
from harness.context import HarnessContext
from harness.mock_zambeel import ZambeelError


class Refused(Exception):
    pass


def student_id_of(runtime: ToolRuntime[HarnessContext]) -> str:
    """The signed-in student, from the runtime context the caller set (never a model argument)."""
    ctx = runtime.context
    if ctx is None or not getattr(ctx, "student_id", None):
        raise Refused("No signed-in student for this session.")
    if ctx.role != "student":
        raise Refused(f"This tool is for students; the session role is {ctx.role!r}.")
    return ctx.student_id


def case_id_of(runtime: ToolRuntime[HarnessContext]) -> str:
    """This session's case: the LangGraph thread_id (one thread per case, invariant 6)."""
    thread_id = (runtime.config or {}).get("configurable", {}).get("thread_id")
    if not thread_id:
        raise Refused("This session has no case thread.")
    return thread_id


def run_json(fn: Callable[[], dict[str, Any]], *errors: type[Exception]) -> str:
    try:
        return json.dumps(fn())
    except (Refused, ZambeelError, UnknownCase, *errors) as exc:
        return json.dumps({"error": str(exc)})

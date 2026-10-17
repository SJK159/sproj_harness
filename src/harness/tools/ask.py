"""ask_student: the eligibility-checker's way to ask the student one clarifying question.

The tool body never answers: it is paused by the sub-agent's own interrupt_on with the `respond`
decision, so the student's typed answer becomes the tool result (harness.subagents.SUBAGENT_INTERRUPT_ON).
It is read-only and changes nothing, which is why `respond` is acceptable here and nowhere else.
"""

import json

from langchain.tools import tool


@tool
def ask_student(question: str) -> str:
    """Ask the signed-in student one short clarifying question (e.g. which course code they mean) and
    get their answer. Use only when the request is ambiguous; never to ask for permission."""
    return json.dumps({"error": "ask_student must be answered by the student; it has no answer of its own."})

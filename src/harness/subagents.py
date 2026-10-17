"""The eligibility-checker sub-agent.

It runs in its own context (only its system prompt and the task description), uses the read
tools, and returns a structured EligibilityVerdict to the main agent through the `task` tool.
The verdict is for the conversation only: `submit_case` re-runs the deterministic check itself
(CLAUDE.md invariant 10).
"""

from deepagents import SubAgent
from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from harness.guards import StructuredFromText
from harness.tools.read_tools import check_my_eligibility, get_my_profile, list_sections


class Reason(BaseModel):
    code: str = Field(description="Code exactly as returned by check_my_eligibility, e.g. PREREQ_MISSING.")
    rule: str = Field(description='Rule label exactly as returned, e.g. "FE-2 (placeholder v0.1)".')
    reason: str = Field(description="The reason text returned by the tool.")


class SectionVerdict(BaseModel):
    offering_id: str | None = Field(description="Section checked, e.g. CS412-S1; null if not offered.")
    can_submit: bool
    fe_needed: bool
    blocking: list[Reason]
    advisory: list[Reason]
    suggestions: list[str] = Field(description="Offering IDs of suggested open sections.")


class EligibilityVerdict(BaseModel):
    course_id: str
    sections: list[SectionVerdict]
    error: str | None = Field(default=None, description="Tool error message, if a tool returned one.")
    summary: str = Field(description="One sentence for the main agent.")


ELIGIBILITY_PROMPT = """\
You check force-enrollment eligibility for the signed-in student and report a structured verdict.

1. If the task names a course and section, call `check_my_eligibility` for that section.
   If it names only a course, call `list_sections` and then `check_my_eligibility` for every section listed.
2. Finish by calling the `EligibilityVerdict` tool (never write the verdict as text). Fill it from the tool results only. Copy every code, rule label and reason exactly as
   returned, in the same order. Never add, drop, merge or rephrase a code. Use empty lists when there are none.
3. If a tool returns an error, put it in `error` and return the sections you could check.
You cannot submit or change anything. Do not answer the student; the main agent does that.
"""


def eligibility_checker(backend: BackendProtocol, model: BaseChatModel | None = None) -> SubAgent:
    spec: SubAgent = {
        "name": "eligibility-checker",
        "description": (
            "Checks whether the signed-in student may request force enrollment in a course or section "
            "and returns a structured verdict with every failing rule and its label. Give it the course "
            "and, if known, the section."
        ),
        "system_prompt": ELIGIBILITY_PROMPT,
        "tools": [get_my_profile, list_sections, check_my_eligibility],
        # Replaces the default file tools (which include write_file, edit_file, delete, execute).
        # read_file is the minimum: FilesystemMiddleware refuses a tool list without it.
        # StructuredFromText: gpt-oss on Databricks sometimes writes the verdict as JSON text instead of
        # calling the EligibilityVerdict tool (see harness/guards.py).
        "middleware": [FilesystemMiddleware(backend=backend, tools=["read_file"]), StructuredFromText(EligibilityVerdict)],
        "response_format": ToolStrategy(EligibilityVerdict),
    }
    if model is not None:
        spec["model"] = model
    return spec

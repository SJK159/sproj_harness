"""Runtime context: who is using the agent. Set by the caller per run, never by the model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessContext:
    student_id: str
    role: str = "student"

"""Runtime context: who is using the agent. Set by the caller per run, never by the model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessContext:
    student_id: str
    role: str = "student"
    tenant_id: str | None = None
    object_id: str | None = None
    authenticated: bool = False

    @classmethod
    def from_verified_student(cls, principal):
        """Only the trusted application boundary calls this; no credentials stored."""
        if principal.role != "Student":
            raise PermissionError("A student principal is required for a student agent run")
        return cls(principal.actor_id, "student", principal.tenant_id, principal.object_id, True)

"""Loopback demo identity, independent of model-visible tool arguments.

Headers are explicit claims, NOT authentication. The FE service credential only
protects internal academic tools. Replace this middleware with Entra validation
before remote deployment. Identity is scoped per request using ContextVar.
"""
import hmac
import os
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str
    service: bool = False


principal = ContextVar("mcp_demo_principal", default=None)


def caller(role=None):
    value = principal.get()
    if value is None:
        raise PermissionError("A demo identity is required.")
    if role and value.role != role:
        raise PermissionError(f"This operation requires the {role} role.")
    return value


def require_service():
    if not caller().service:
        raise PermissionError("Only the FE service may call this operation.")


def service_secret():
    value = os.environ.get("HARNESS_MCP_SERVICE_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("HARNESS_MCP_SERVICE_SECRET must contain at least 32 characters.")
    return value


class DemoIdentityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        actor = headers.get("x-demo-actor", "")
        role = headers.get("x-demo-role", "")
        supplied = headers.get("x-fe-service-key")
        service = False
        if supplied:
            service = hmac.compare_digest(supplied, service_secret())
        if not actor or role not in ("student", "instructor") or (supplied and not service):
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"error":"Valid local demo headers required"}'})
            return
        token = principal.set(Principal(actor, role, service))
        try:
            await self.app(scope, receive, send)
        finally:
            principal.reset(token)

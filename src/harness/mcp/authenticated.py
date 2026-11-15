"""Per-request transport capability, never a graph field or model tool argument."""
import asyncio
import json
from contextvars import ContextVar
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from harness.mock_zambeel import ZambeelError

current_transport = ContextVar("authenticated_mcp_transport", default=None)


class MCPUnavailable(ZambeelError):
    """Operational failure; never convert it to a student's cancellation/refusal."""


class ReauthenticationRequired(MCPUnavailable):
    pass


class AuthenticatedMCP:
    def __init__(self, person, token_provider, urls, *, allow_local=False):
        self.person, self.tokens, self.urls = person, token_provider, urls
        for url in urls.values():
            p = urlsplit(url)
            local = allow_local and p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1", "::1")
            if (not p.hostname or p.username or p.password or p.query or p.fragment
                    or not (p.scheme == "https" or local)):
                raise ValueError("Authenticated MCP requires HTTPS or explicit loopback development")

    async def call(self, server, name, arguments, *, actor, role="student", service=False):
        if actor != self.person.actor_id or role.lower() != self.person.role.lower() or service:
            raise MCPUnavailable("Authenticated MCP identity cannot be overridden")
        if server not in self.urls:
            raise MCPUnavailable("Requested MCP server is not available")
        try:
            token = await asyncio.to_thread(self.tokens, server)
            async with httpx.AsyncClient(headers={"Authorization":f"Bearer {token}"}, timeout=20,
                                        trust_env=False, follow_redirects=False) as http:
                async with streamable_http_client(self.urls[server], http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(name, arguments or {})
            if result.isError:
                raise MCPUnavailable("MCP tool failed; retry or contact the service owner")
            value = result.structuredContent
            if value is None:
                value = json.loads("".join(c.text for c in result.content if c.type == "text"))
            if not isinstance(value, dict):
                raise MCPUnavailable("MCP returned an unexpected response")
            if value.get("error_type"):
                if value["error_type"] not in {"NotEligible", "DuplicateCase", "WrongState", "NotYourCase", "NotCourseOwner", "InvalidTransition"}:
                    raise MCPUnavailable("MCP service could not complete the operation")
                raise ZambeelError("MCP operation refused: " + str(value["error_type"])[:64])
            return value
        except ZambeelError:
            raise
        except Exception as exc:
            # Do not put HTTP headers, OAuth payloads or transport exception
            # representations into model-visible tool errors or application logs.
            if getattr(exc, "status_code", None) == 401:
                raise ReauthenticationRequired("Sign in again to continue; saved case state is retained") from None
            raise MCPUnavailable("Authenticated MCP call unavailable; retry or sign in again") from None

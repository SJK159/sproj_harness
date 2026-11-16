"""FE-owned application token transport, independent of BFF user capabilities."""
import asyncio
import json
import os
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from harness.worker import ClientCredentials, OperationalFailure, classify_exception
from harness.mock_zambeel import ZambeelError


class RetryableServiceFailure(Exception):
    pass


@lru_cache(maxsize=1)
def credentials():
    return ClientCredentials(os.environ.get("HARNESS_ENTRA_TENANT_ID"),
        os.environ.get("HARNESS_FE_CLIENT_ID"), os.environ.get("HARNESS_FE_CLIENT_SECRET"),
        os.environ.get("HARNESS_FE_ZAMBEEL_SCOPE", ""))


async def acall(name, arguments):
    url = os.environ.get("HARNESS_ZAMBEEL_MCP_URL", "")
    p = urlsplit(url)
    local = (os.environ.get("HARNESS_MCP_ALLOW_LOOPBACK") == "true" and p.scheme == "http"
             and p.hostname in ("localhost", "127.0.0.1", "::1"))
    if (not p.hostname or p.username or p.password or p.query or p.fragment
            or not (p.scheme == "https" or local)):
        raise OperationalFailure("FE academic endpoint requires HTTPS or explicit loopback development")
    try:
        token = await asyncio.to_thread(credentials().get)
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=20,
                                    trust_env=False, follow_redirects=False) as http:
            async with streamable_http_client(url, http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
    except Exception as exc:
        if classify_exception(exc) == "retry":
            raise RetryableServiceFailure("Academic service temporarily unavailable") from None
        raise OperationalFailure("Academic service authentication or transport failed") from None
    if result.isError:
        raise OperationalFailure("Academic tool failed")
    value = result.structuredContent
    if value is None:
        try:
            value = json.loads("".join(c.text for c in result.content if c.type == "text"))
        except (TypeError, ValueError):
            raise OperationalFailure("Invalid academic response") from None
    if not isinstance(value, dict):
        raise OperationalFailure("Invalid academic response")
    if value.get("error_type"):
        if value["error_type"] == "RetryableServiceFailure":
            raise RetryableServiceFailure("Academic service temporarily unavailable")
        if value["error_type"] in {"FeCapReached", "AlreadyEnrolled", "IdempotencyConflict", "UnknownOffering", "UnknownStudent"}:
            raise ZambeelError("Academic operation refused: " + value["error_type"])
        raise OperationalFailure("Academic operation unavailable")
    return value


def call(name, arguments):
    return asyncio.run(acall(name, arguments))

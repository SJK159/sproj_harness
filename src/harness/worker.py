"""Recoverable approved-case worker. Run: python -m harness.worker --once.

Only calls execute_approved_case(case_id). Never invokes the model, impersonates a
student or mints approvals. The remote FE endpoint must implement its own gates.
"""
import argparse
import asyncio
import json
import os
import re
import time
from contextlib import closing
from urllib.parse import urlsplit

import httpx

from harness import jobs
from harness.mock_zambeel import connect


class OperationalFailure(Exception):
    """Requires operator attention; not an academic refusal."""


class ProtocolFailure(OperationalFailure):
    pass


def checked_result(value, case_id):
    required = {"case_id", "state", "outcome", "retryable", "enrollment_id", "error_code", "message"}
    if not isinstance(value, dict) or not required <= value.keys() or value["case_id"] != case_id:
        raise ProtocolFailure("Invalid FE result")
    outcome = value["outcome"]
    states = {"DRAFT", "AWAITING_CONFIRMATION", "SUBMITTED", "AWAITING_APPROVAL", "APPROVED",
              "EXECUTING", "COMPLETED", "FAILED", "REJECTED", "CANCELLED"}
    if (not isinstance(value["state"], str) or value["state"] not in states
            or outcome not in ("completed", "terminal", "retry")
            or type(value["retryable"]) is not bool or value["retryable"] != (outcome == "retry")):
        raise ProtocolFailure("Contradictory FE outcome")
    for field in ("error_code", "message"):
        if value[field] is not None and not isinstance(value[field], str):
            raise ProtocolFailure("Invalid FE error fields")
    if value["enrollment_id"] is not None and (type(value["enrollment_id"]) is not int or value["enrollment_id"] <= 0):
        raise ProtocolFailure("Invalid enrollment identifier")
    if outcome == "completed":
        if value["state"] != "COMPLETED" or value["enrollment_id"] is None or value["error_code"] is not None:
            raise ProtocolFailure("Completion lacks a saved enrollment")
    elif value["state"] == "COMPLETED":
        raise ProtocolFailure("Completed case has contradictory outcome")
    return value


def classify_exception(exc):
    """MCP/AnyIO may wrap HTTP failures in nested exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        categories = [classify_exception(e) for e in exc.exceptions]
        return "retry" if categories and all(c == "retry" for c in categories) else "blocked"
    if isinstance(exc, httpx.HTTPStatusError):
        return "retry" if exc.response.status_code == 429 or exc.response.status_code >= 500 else "blocked"
    if isinstance(exc, (httpx.TransportError, TimeoutError)):
        return "retry"
    return "blocked"


class Worker:
    def __init__(self, conn, execute, *, clock=time.time, lease_seconds=90, deadline=30):
        if deadline <= 0 or lease_seconds <= deadline:
            raise ValueError("Lease must exceed the positive overall call deadline")
        self.conn, self.execute, self.clock = conn, execute, clock
        self.lease_seconds, self.deadline = lease_seconds, deadline

    async def run_once(self):
        job = jobs.claim(self.conn, now=self.clock(), lease_seconds=self.lease_seconds)
        if job is None:
            return False
        try:
            value = await asyncio.wait_for(self.execute(job.case_id), timeout=self.deadline)
            result = checked_result(value, job.case_id)
        except Exception as exc:
            category = classify_exception(exc)
            # Persist only fixed classifications, never raw exceptions, headers,
            # OAuth error bodies, tokens or model-provided text.
            jobs.finish(self.conn, job, now=self.clock(), status="pending" if category == "retry" else "blocked",
                        delay=self.backoff(job.attempts) if category == "retry" else 0,
                        error="TRANSPORT_RETRY" if category == "retry" else "OPERATIONAL_FAILURE")
            return True
        outcome = result["outcome"]
        code = result["error_code"]
        # Bound server-supplied diagnostic identifiers. Message is not persisted.
        code = code if code and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) else None
        jobs.finish(self.conn, job, now=self.clock(),
                    status={"completed": "succeeded", "terminal": "terminal", "retry": "pending"}[outcome],
                    delay=self.backoff(job.attempts) if outcome == "retry" else 0,
                    error=code or ("FE_TERMINAL" if outcome == "terminal" else None),
                    enrollment_id=result["enrollment_id"] if outcome == "completed" else None)
        return True

    @staticmethod
    def backoff(attempt):
        return min(300, 2 ** min(attempt, 9))


class ClientCredentials:
    """In-memory app-token cache; credentials provisioned outside source control."""
    def __init__(self, tenant, client_id, secret, scope):
        if not all((tenant, client_id, secret, scope)) or not scope.endswith("/.default"):
            raise ValueError("Worker tenant, client ID, secret and FE /.default scope are required")
        import msal
        self.scope = scope
        self.application = msal.ConfidentialClientApplication(
            client_id, client_credential=secret, authority=f"https://login.microsoftonline.com/{tenant}", timeout=10)

    def get(self):
        # MSAL uses requests internally (declared by MSAL); normalize only its
        # transient network failures, not invalid_client/consent configuration.
        from requests.exceptions import ConnectionError, Timeout
        try:
            result = self.application.acquire_token_for_client(scopes=[self.scope])
        except (ConnectionError, Timeout):
            raise TimeoutError("Token service temporarily unavailable") from None
        if result.get("error") in ("temporarily_unavailable", "server_error"):
            raise TimeoutError("Token service temporarily unavailable")
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise OperationalFailure("Worker application token unavailable")
        return token


class ServiceExecutor:
    def __init__(self, url, token_provider):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("Worker FE endpoint must be HTTPS without embedded credentials/query/fragment")
        self.url, self.tokens = url, token_provider

    async def __call__(self, case_id):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        token = await asyncio.to_thread(self.tokens.get)
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=20,
                                    trust_env=False, follow_redirects=False) as http:
            async with streamable_http_client(self.url, http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool("execute_approved_case", {"case_id": case_id})
        if response.isError:
            raise OperationalFailure("FE tool error requires reconciliation")
        if response.structuredContent is not None:
            return response.structuredContent
        try:
            return json.loads("".join(c.text for c in response.content if c.type == "text"))
        except (TypeError, ValueError):
            raise ProtocolFailure("FE returned an invalid result") from None


def main():
    from harness.config import load_env
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one ready job")
    args = parser.parse_args()
    executor = ServiceExecutor(os.environ.get("HARNESS_WORKER_FE_URL", ""), ClientCredentials(
        os.environ.get("HARNESS_ENTRA_TENANT_ID"), os.environ.get("HARNESS_WORKER_CLIENT_ID"),
        os.environ.get("HARNESS_WORKER_CLIENT_SECRET"), os.environ.get("HARNESS_WORKER_FE_SCOPE", "")))
    with closing(connect()) as conn:
        jobs.initialize(conn)
        worker = Worker(conn, executor)
        try:
            while True:
                jobs.recover_execution_jobs(conn, now=time.time())
                worked = asyncio.run(worker.run_once())
                if args.once:
                    break
                if not worked:
                    time.sleep(2)
        except KeyboardInterrupt:
            pass  # Unacknowledged leases expire; next process reconciles the same case.


if __name__ == "__main__":
    main()

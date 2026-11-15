"""API authentication boundary. No bearer credentials enter graph state or memory.

The mapping file is operator-managed JSON: [{tenant_id, object_id, actor_id, role}].
Roles must agree with BOTH the mapping and this API's verified role claim.
This module does not configure Entra or authorize app-only MCP execution.
"""
import json
import os
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import jwt
from fastapi import HTTPException, Request

from harness.api import views


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    object_id: str
    actor_id: str
    role: str


class EntraVerifier:
    def __init__(self, tenant_id, audience, scope, mappings, key_provider=None):
        if not tenant_id or not audience or not scope:
            raise ValueError("Entra tenant, harness API audience and scope are required")
        self.tenant_id, self.audience, self.scope = tenant_id, audience, scope
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        self.mappings = {}
        for row in mappings:
            key = (row["tenant_id"], row["object_id"])
            if key in self.mappings or row["role"] not in ("Student", "Instructor") or not row["actor_id"]:
                raise ValueError("Identity mapping must contain unique identities and supported roles")
            self.mappings[key] = row
        self.keys = key_provider or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
            timeout=10, lifespan=300,
        )

    def verify(self, token):
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience,
                                issuer=self.issuer, options={"require": ["exp", "iat", "iss", "aud", "tid", "oid"]})
            if (claims["tid"] != self.tenant_id or claims.get("ver") != "2.0"
                    or not isinstance(claims["oid"], str) or not claims["oid"]):
                raise jwt.InvalidTokenError()
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(503, "Authentication key service unavailable") from None
        except (jwt.PyJWTError, ValueError, TypeError):
            raise HTTPException(401, "Invalid or expired API credentials", headers={"WWW-Authenticate": "Bearer"}) from None
        scopes, roles = claims.get("scp"), claims.get("roles")
        if not isinstance(scopes, str) or self.scope not in scopes.split():
            raise HTTPException(403, "Required API scope is missing")
        row = self.mappings.get((claims["tid"], claims["oid"]))
        if row is None or not isinstance(roles, list) or row["role"] not in roles:
            raise HTTPException(403, "User is not mapped or lacks the assigned API role")
        return Principal(claims["tid"], claims["oid"], row["actor_id"], row["role"])


def configured_verifier():
    mode = os.environ.get("HARNESS_AUTH_MODE", "demo")
    if mode in ("demo", "bff"):
        return None
    if mode != "entra":
        raise ValueError("HARNESS_AUTH_MODE must be demo or entra")
    if os.environ.get("HARNESS_USE_MCP", "").lower() in ("1", "true"):
        raise ValueError("Entra API mode cannot use demo MCP credentials; authenticated MCP transport is pending")
    return EntraVerifier(os.environ.get("HARNESS_ENTRA_TENANT_ID"),
                         os.environ.get("HARNESS_API_AUDIENCE"),
                         os.environ.get("HARNESS_API_SCOPE"),
                         json.loads(Path(os.environ["HARNESS_IDENTITY_MAP"]).read_text(encoding="utf-8")))


class ApiAuthorization:
    def __init__(self, verifier, bff=None):
        self.verifier, self.bff = verifier, bff

    async def __call__(self, request: Request):
        from harness.mcp.authenticated import current_transport, AuthenticatedMCP
        current_transport.set(None)
        if self.bff and request.url.path.startswith("/auth/"):
            return  # Router owns login/callback verification and logout CSRF.
        if self.bff:
            from starlette.concurrency import run_in_threadpool
            reference, data, person = await run_in_threadpool(self.bff.session, request)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                self.bff.check_csrf(request, data)
            if request.method == "POST" and request.url.path.endswith(("/messages", "/resume")):
                # Resolve interaction-required before launching an SSE worker.
                for server in self.bff.settings.scopes:
                    await run_in_threadpool(self.bff.token, reference, server)
            current_transport.set(AuthenticatedMCP(person,
                lambda server:self.bff.token(reference, server),
                {s:os.environ.get(f"HARNESS_{s.upper()}_MCP_URL", f"http://127.0.0.1:{8101 if s == 'fe' else 8102}/mcp")
                 for s in self.bff.settings.scopes}, allow_local=os.environ.get("HARNESS_MCP_ALLOW_LOOPBACK") == "true"))
        elif self.verifier is None:
            return
        else:
            scheme, _, token = request.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not token or " " in token:
                raise HTTPException(401, "Bearer API credentials required", headers={"WWW-Authenticate": "Bearer"})
            from starlette.concurrency import run_in_threadpool
            person = await run_in_threadpool(self.verifier.verify, token)
        request.state.principal = person
        path, params = request.url.path, request.path_params
        def require(actor, role=None):
            if person.actor_id != actor or (role and person.role != role):
                raise HTTPException(403, "Operation is not permitted for this user")

        if path in ("/api/students", "/api/instructors"):
            raise HTTPException(403, "Demo identity enumeration is disabled")
        if "student_id" in params:
            require(params["student_id"], "Student")
        if "recipient_id" in params:
            require(params["recipient_id"])
        if "instructor_id" in params:
            require(params["instructor_id"], "Instructor")
        with closing(views.open_db()) as conn:
            if "session_id" in params:
                require(views.session_owner(conn, params["session_id"]), "Student")
            if "case_id" in params:
                case = views.get_case_row(conn, params["case_id"])
                if case is None:
                    raise HTTPException(404, "Case unavailable")
                if path.endswith("/decision") or person.role == "Instructor":
                    require(views.get_section(conn, case["offering_id"])["instructor_id"], "Instructor")
                else:
                    require(case["student_id"], "Student")
            if request.method == "POST":
                try:
                    body = await request.json() if await request.body() else {}
                except ValueError:
                    raise HTTPException(422, "JSON body required") from None
                if isinstance(body, dict):
                    if "student_id" in body:
                        require(body["student_id"], "Student")
                    if "instructor_id" in body:
                        require(body["instructor_id"], "Instructor")
                    if path == "/api/notifications/read":
                        ids = body.get("ids", [])
                        if not isinstance(ids, list) or any(type(i) is not int for i in ids):
                            raise HTTPException(422, "Notification IDs must be integers")
                        for identifier in ids:
                            row = conn.execute("SELECT recipient_id FROM notifications WHERE notification_id = ?", (identifier,)).fetchone()
                            if row is None or row[0] != person.actor_id:
                                raise HTTPException(403, "Notification unavailable")

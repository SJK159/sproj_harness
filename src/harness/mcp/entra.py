"""Resource-specific Entra bearer authentication for the two MCP services.

The BFF owns user login/cache; this module never acquires user tokens.
"""
import json
import os
from pathlib import Path

import anyio
import jwt

from harness.mcp.security import Principal, principal


def mode():
    value = os.environ.get("HARNESS_MCP_AUTH_MODE", "demo")
    if value not in ("demo", "entra"):
        raise ValueError("HARNESS_MCP_AUTH_MODE must be demo or entra")
    return value


class AuthFailure(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class Verifier:
    def __init__(self, tenant, audience, mappings, *, clients, services, keys=None):
        if not tenant or not audience or not clients:
            raise ValueError("MCP tenant, audience and authorized harness client IDs are required")
        self.tenant, self.audience = tenant, audience
        self.issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        self.clients, self.services = set(clients), services
        self.mappings = {}
        actors = set()
        for row in mappings:
            key = (row["tenant_id"], row["object_id"])
            actor, role = row["actor_id"], row["role"]
            if (key in self.mappings or actor in actors or key[0] != tenant or not key[1]
                    or role not in ("Student", "Instructor") or not actor
                    or not actor.startswith("S" if role == "Student" else "I")):
                raise ValueError("MCP identity mappings must be unique and have consistent roles")
            self.mappings[key] = (actor, role)
            actors.add(actor)
        self.keys = keys or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", timeout=10, lifespan=300)

    def verify(self, token):
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            c = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience,
                           issuer=self.issuer, options={"require": ["exp", "iat", "iss", "aud", "tid", "oid", "azp", "ver"]})
            if (c["tid"] != self.tenant or c["ver"] != "2.0" or not isinstance(c["oid"], str)
                    or not c["oid"] or not isinstance(c["azp"], str)):
                raise jwt.InvalidTokenError()
        except jwt.PyJWKClientConnectionError:
            raise AuthFailure(503, "key_service_unavailable") from None
        except (jwt.PyJWTError, TypeError, ValueError):
            raise AuthFailure(401, "invalid_token") from None
        roles = c.get("roles", [])
        if not isinstance(roles, list) or any(not isinstance(r, str) for r in roles):
            raise AuthFailure(403, "insufficient_permissions")
        if "scp" in c:
            if (c["azp"] not in self.clients or not isinstance(c["scp"], str)
                    or "mcp.access" not in c["scp"].split()):
                raise AuthFailure(403, "insufficient_scope")
            row = self.mappings.get((c["tid"], c["oid"]))
            if row is None or row[1] not in roles:
                raise AuthFailure(403, "unmapped_or_unassigned_user")
            return Principal(row[0], row[1].lower(), tenant_id=c["tid"], object_id=c["oid"], client_id=c["azp"])
        allowed = self.services.get(c["azp"], set())
        permissions = frozenset(roles) & frozenset(allowed)
        if not permissions:
            raise AuthFailure(403, "unauthorized_service")
        return Principal("", "service", True, c["tid"], c["oid"], c["azp"], permissions)


def configured_verifier(server):
    tenant = os.environ.get("HARNESS_ENTRA_TENANT_ID")
    audience = os.environ.get(f"HARNESS_{server.upper()}_AUDIENCE")
    clients = os.environ.get("HARNESS_MCP_DELEGATED_CLIENT_IDS", "").split()
    services = {}
    if server == "fe":
        for app in os.environ.get("HARNESS_MCP_WORKER_CLIENT_IDS", "").split():
            services[app] = {"Cases.ExecuteApproved"}
    else:
        for app in os.environ.get("HARNESS_MCP_FE_CLIENT_IDS", "").split():
            services[app] = {"Academic.Read", "Enrollment.ExecuteApproved"}
    mappings = json.loads(Path(os.environ["HARNESS_IDENTITY_MAP"]).read_text(encoding="utf-8"))
    return Verifier(tenant, audience, mappings, clients=clients, services=services)


class BearerMiddleware:
    def __init__(self, app, verifier):
        self.app, self.verifier = app, verifier

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        scheme, _, token = headers.get("authorization", "").partition(" ")
        try:
            if scheme.lower() != "bearer" or not token or " " in token:
                raise AuthFailure(401, "invalid_token")
            person = await anyio.to_thread.run_sync(self.verifier.verify, token)
        except AuthFailure as exc:
            response_headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
            if exc.status == 401:
                response_headers.append((b"www-authenticate", b'Bearer error="invalid_token"'))
            await send({"type": "http.response.start", "status": exc.status, "headers": response_headers})
            await send({"type": "http.response.body", "body": json.dumps({"error": exc.code}).encode()})
            return
        saved = principal.set(person)
        try:
            await self.app(scope, receive, send)
        finally:
            principal.reset(saved)

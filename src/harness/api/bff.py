"""Backend-managed OIDC login. Browser cookies contain random references only.

MSAL handles auth-code/PKCE/state/nonce and token renewal. SQLite payloads (login
flows, account records, user token caches) are encrypted with an operator key.
No browser-supplied identity, roles, redirect URL or token cache is trusted.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from harness.api.auth import Principal

COOKIE = "harness_session"
FLOW_COOKIE = "harness_login"


@dataclass(frozen=True)
class Settings:
    tenant: str
    client_id: str
    callback: str
    frontend: str
    secure: bool
    scopes: dict[str, str]

    def __post_init__(self):
        for url in (self.callback, self.frontend):
            parsed = urlsplit(url)
            if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or (parsed.scheme != "https" and not (not self.secure and parsed.scheme == "http"
                        and parsed.hostname in ("localhost", "127.0.0.1", "::1")))):
                raise ValueError("Login URLs require HTTPS (explicit local development may use loopback HTTP)")
        if urlsplit(self.frontend).path not in ("", "/") or not self.tenant or not self.client_id:
            raise ValueError("Frontend must be an origin and tenant/client IDs must be configured")
        if not self.scopes or any(not v for v in self.scopes.values()):
            raise ValueError("Configure delegated scopes for the MCP resources")


class SessionStore:
    def __init__(self, path, key, *, clock=time.time):
        self.path, self.cipher, self.clock = Path(path), Fernet(key), clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS browser_sessions (
                digest TEXT PRIMARY KEY, kind TEXT NOT NULL, payload BLOB NOT NULL, expires REAL NOT NULL)""")
            conn.commit()

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def digest(reference):
        if not isinstance(reference, str) or not 32 <= len(reference) <= 256:
            raise HTTPException(401, "Sign in required")
        return hashlib.sha256(reference.encode()).hexdigest()

    def encode(self, data):
        return self.cipher.encrypt(json.dumps(data).encode())

    def decode(self, value):
        try:
            return json.loads(self.cipher.decrypt(value))
        except (InvalidToken, ValueError, TypeError):
            raise HTTPException(401, "Session unavailable; sign in again") from None

    def create(self, kind, data, ttl):
        reference = secrets.token_urlsafe(40)
        with closing(self.connect()) as conn, conn:
            conn.execute("DELETE FROM browser_sessions WHERE expires <= ?", (self.clock(),))
            conn.execute("INSERT INTO browser_sessions VALUES (?, ?, ?, ?)",
                         (self.digest(reference), kind, self.encode(data), self.clock() + ttl))
        return reference

    def read(self, reference, kind="session", *, consume=False):
        digest = self.digest(reference)
        with closing(self.connect()) as conn, conn:
            if consume:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload, expires FROM browser_sessions WHERE digest = ? AND kind = ?",
                               (digest, kind)).fetchone()
            if row is None or row[1] <= self.clock():
                raise HTTPException(401, "Session expired; sign in again")
            if consume:
                conn.execute("DELETE FROM browser_sessions WHERE digest = ?", (digest,))
            return self.decode(row[0])

    def delete(self, reference):
        if not reference:
            return
        with closing(self.connect()) as conn, conn:
            conn.execute("DELETE FROM browser_sessions WHERE digest = ?", (self.digest(reference),))

    def change(self, reference, update):
        """Serialize cache updates across workers; never lose refreshed credentials.

        Network work has a bounded MSAL timeout. Suitable for the single-VM demo;
        this is not a horizontally scaled token-cache service.
        """
        digest = self.digest(reference)
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload, expires FROM browser_sessions WHERE digest = ? AND kind = 'session'", (digest,)).fetchone()
            if row is None or row[1] <= self.clock():
                raise HTTPException(401, "Session expired; sign in again")
            data = self.decode(row[0])
            result = update(data)
            conn.execute("UPDATE browser_sessions SET payload = ? WHERE digest = ?", (self.encode(data), digest))
            return result


class BFF:
    def __init__(self, settings, store, mappings, application):
        self.settings, self.store, self.application = settings, store, application
        self.identities = {}
        for row in mappings:
            key = (row["tenant_id"], row["object_id"])
            if key in self.identities or row["role"] not in ("Student", "Instructor") or not row["actor_id"]:
                raise ValueError("Mappings require unique identities and supported application roles")
            self.identities[key] = Principal(*key, row["actor_id"], row["role"])

    def principal(self, data):
        person = self.identities.get((data["principal"]["tenant_id"], data["principal"]["object_id"]))
        if person is None or asdict(person) != data["principal"]:
            raise HTTPException(403, "Identity mapping changed; sign in again")
        return person

    def session(self, request):
        reference = request.cookies.get(COOKIE)
        data = self.store.read(reference)
        return reference, data, self.principal(data)

    def check_csrf(self, request, data):
        origins = {self.settings.frontend.rstrip("/"), origin(self.settings.callback)}
        supplied = request.headers.get("X-CSRF-Token", "")
        if (request.headers.get("Origin") not in origins or not supplied
                or not hmac.compare_digest(supplied, data["csrf"])):
            raise HTTPException(403, "Request verification failed; reload and try again")

    def token(self, reference, server):
        if server not in self.settings.scopes:
            raise HTTPException(503, "Requested MCP resource is not configured")
        def acquire(data):
            self.principal(data)
            app, cache = self.application(data["cache"])
            accounts = [a for a in app.get_accounts() if a.get("home_account_id") == data["account"]]
            if not accounts:
                raise HTTPException(401, "Sign in again to continue")
            try:
                result = app.acquire_token_silent([self.settings.scopes[server]], account=accounts[0])
            except Exception:
                raise HTTPException(503, "Microsoft token service unavailable") from None
            data["cache"] = cache.serialize()
            if not result or not isinstance(result.get("access_token"), str):
                raise HTTPException(401, "Sign in again to continue")
            return result["access_token"]
        return self.store.change(reference, acquire)

    def cookie(self, response, name, value, max_age):
        response.set_cookie(name, value, max_age=max_age, httponly=True, secure=self.settings.secure,
                            samesite="lax", path="/")

    def router(self):
        router = APIRouter(prefix="/auth")

        @router.get("/status")
        def status(request: Request):
            try:
                _, data, person = self.session(request)
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise
                return JSONResponse({"mode":"bff", "authenticated":False}, headers={"Cache-Control":"no-store"})
            return JSONResponse({"mode":"bff", "authenticated":True, "actor_id":person.actor_id,
                                 "role":person.role, "csrf_token":data["csrf"]}, headers={"Cache-Control":"no-store"})

        @router.get("/login")
        def login():
            app, cache = self.application(None)
            # One resource per token request; other resources use the server cache.
            try:
                flow = app.initiate_auth_code_flow([self.settings.scopes["fe"]], redirect_uri=self.settings.callback)
            except Exception:
                raise HTTPException(503, "Microsoft sign-in unavailable") from None
            if "auth_uri" not in flow:
                raise HTTPException(503, "Microsoft sign-in unavailable")
            reference = self.store.create("flow", {"flow":flow, "cache":cache.serialize()}, 600)
            response = RedirectResponse(flow["auth_uri"], status_code=302, headers={"Cache-Control":"no-store"})
            self.cookie(response, FLOW_COOKIE, reference, 600)
            return response

        @router.get("/callback")
        def callback(request: Request):
            # Cookie-bound, single-use server state prevents login CSRF/replay.
            saved = self.store.read(request.cookies.get(FLOW_COOKIE), "flow", consume=True)
            app, cache = self.application(saved["cache"])
            try:
                result = app.acquire_token_by_auth_code_flow(saved["flow"], dict(request.query_params))
            except Exception:
                raise HTTPException(401, "Sign-in verification failed; try again") from None
            claims = result.get("id_token_claims", {})
            if (not isinstance(claims, dict) or result.get("error") or claims.get("tid") != self.settings.tenant
                    or claims.get("aud") != self.settings.client_id
                    or claims.get("iss") != f"https://login.microsoftonline.com/{self.settings.tenant}/v2.0"
                    or not isinstance(claims.get("oid"), str) or type(claims.get("exp")) not in (int, float)
                    or claims["exp"] <= self.store.clock()):
                raise HTTPException(401, "Sign-in verification failed; try again")
            person = self.identities.get((claims["tid"], claims["oid"]))
            if person is None:
                raise HTTPException(403, "This Microsoft account has no project identity mapping")
            accounts = [a for a in app.get_accounts() if a.get("local_account_id") == person.object_id
                        and a.get("realm") == person.tenant_id]
            if len(accounts) != 1:
                raise HTTPException(401, "Sign-in account could not be verified")
            reference = self.store.create("session", {"principal":asdict(person), "csrf":secrets.token_urlsafe(32),
                "account":accounts[0]["home_account_id"], "cache":cache.serialize()}, 8 * 3600)
            self.store.delete(request.cookies.get(COOKIE))  # rotate rather than fixate an existing session
            response = RedirectResponse(self.settings.frontend, status_code=302, headers={"Cache-Control":"no-store"})
            response.delete_cookie(FLOW_COOKIE, path="/")
            self.cookie(response, COOKIE, reference, 8 * 3600)
            return response

        @router.post("/logout")
        def logout(request: Request):
            reference, data, _ = self.session(request)
            self.check_csrf(request, data)
            self.store.delete(reference)
            response = JSONResponse({"signed_out":True}, headers={"Cache-Control":"no-store"})
            response.delete_cookie(COOKIE, path="/")
            return response
        return router


def origin(url):
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def configured_bff():
    if os.environ.get("HARNESS_AUTH_MODE", "demo") != "bff":
        return None
    import msal
    secure = os.environ.get("HARNESS_COOKIE_SECURE", "true")
    if secure not in ("true", "false"):
        raise ValueError("HARNESS_COOKIE_SECURE must be true or false")
    settings = Settings(os.environ["HARNESS_ENTRA_TENANT_ID"], os.environ["HARNESS_CLIENT_ID"],
        os.environ["HARNESS_CALLBACK_URL"], os.environ["HARNESS_FRONTEND_ORIGIN"],
        secure == "true",
        {server:os.environ[f"HARNESS_{server.upper()}_SCOPE"] for server in ("fe", "zambeel")})
    secret = os.environ.get("HARNESS_CLIENT_SECRET")
    if not secret:
        raise ValueError("HARNESS_CLIENT_SECRET must be provisioned in private backend configuration")
    key = os.environ.get("HARNESS_SESSION_KEY", "").encode()
    if not key:
        keyfile = Path(os.environ.get("HARNESS_SESSION_KEY_FILE", "data/auth.key"))
        if not keyfile.exists() and not settings.secure:
            keyfile.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    output.write(Fernet.generate_key())
            except FileExistsError:
                pass
        if not keyfile.exists():
            raise ValueError("Provision a persistent protected HARNESS_SESSION_KEY or key file")
        key = keyfile.read_bytes()
    store = SessionStore(os.environ.get("HARNESS_AUTH_DB", "data/auth.db"), key)
    mappings = json.loads(Path(os.environ["HARNESS_IDENTITY_MAP"]).read_text(encoding="utf-8"))
    def application(serialized):
        cache = msal.SerializableTokenCache()
        if serialized:
            cache.deserialize(serialized)
        app = msal.ConfidentialClientApplication(settings.client_id, client_credential=secret,
            authority=f"https://login.microsoftonline.com/{settings.tenant}", token_cache=cache, timeout=10)
        return app, cache
    return BFF(settings, store, mappings, application)

# LUMS Process Orchestrator - `ammar` branch

A senior-year project for LUMS SProj 2026-27, Group 4, supervised by Dr. Ali
Khawaja. The application helps a student request force enrollment: check academic
eligibility, confirm submission, obtain the owning instructor's approval, execute
an authorized enrollment, and retain the case history and audit trail.

**All academic data is synthetic. FE rules are team placeholders, not official
LUMS policy. This branch is not a live integration with the university's systems.**

This README is the entry point for **Ammar's Agent/Orchestrator branch**. It
explains the repository, additions relative to `main`, execution, and what remains.
The comparison baseline is `main` at `8e234b8`; implementation commits are
`e49e065`, `a4329db`, and `13eeaac` (16 November 2026). Later upstream changes
should be reviewed before assuming this comparison still describes `main`.

## Contents

- [What the repository does](#what-the-repository-does)
- [What this branch adds to main](#what-this-branch-adds-to-main)
- [What can run today](#what-can-run-today)
- [Installation and execution](#installation-and-execution)
- [Tests and verification](#tests-and-verification)
- [What's left](#whats-left)
- [Files added or changed relative to main](#files-added-or-changed-relative-to-main)
- [Further documentation](#further-documentation)

## What the repository does

The original `main` already provides:

1. A Deep Agents/LangGraph student orchestrator with planning and a force-enrollment skill.
2. A restricted eligibility-checker sub-agent with read tools and structured verdicts.
3. A mock Zambeel academic system in SQLite, including students, offerings and eligibility rules.
4. Student confirmation and instructor approval through human-in-the-loop pauses.
5. Deterministic instructor ownership, signed approval, expiry and single-use checks.
6. Execution-time academic checks, case-ID enrollment idempotency and audited state transitions.
7. Persistent graph checkpoints, per-student memory and case-derived notes.
8. FastAPI/SSE and a React/TypeScript frontend, plus student/instructor CLI clients.
9. Optional **local demo** FE and Zambeel MCP servers, with tools, an FE prompt and completions.
10. Agent runs that survive browser disconnects, with saved history/recovery support.

Those are existing team contributions. This branch extends their identity,
integration and recovery boundaries rather than replacing the workflow engine.

### Components

| Component | Responsibility |
|---|---|
| React frontend | Chat, confirmation, cases, profile, memory and instructor screens |
| FastAPI | API ownership checks, browser login/session boundary and SSE relay |
| Deep Agents / LangGraph | Planning, tools, eligibility sub-agent, HITL and persistent execution |
| Zambeel MCP | Academic-system adapter over the mock; real PeopleSoft is later work |
| FE MCP | Case workflow, instructor decision, deterministic approval/enrollment gates |
| Durable worker | Leased execution jobs; calls the agreed service-only FE operation |
| SQLite | Academic/case data, audits/jobs, checkpoints, long-term notes and separate encrypted auth storage |
| Entra | Project account sign-in and resource-specific access tokens |

## What this branch adds to main

### 1. API authentication and authorization foundation

- Optional Entra bearer-token verification using RS256/JWKS, exact issuer and
  audience, lifetime, tenant, delegated scope and mapped application role.
- Operator-controlled `(tenant ID, user Object ID)` mapping to internal actors.
- Ownership guards for profile, memory, cases, sessions/history, notifications,
  stop/resume and instructor actions. Conflicting browser IDs are refused.
- `/api/me`, Bearer challenges and checks before streaming begins.
- Explicit modes: `demo`, selected browser mode `bff`, and legacy isolated
  bearer-verifier mode `entra`. Unknown modes fail configuration.

The bearer verifier is a useful isolated foundation/test surface. **It is not
the chosen browser sign-in flow; the later BFF agreement supersedes browser OBO.**

### 2. Backend-managed Microsoft sign-in (BFF)

- `/auth/login`, `/auth/callback`, `/auth/status` and POST `/auth/logout`.
- MSAL confidential-client authorization-code flow with its PKCE/state/nonce handling.
- Cookie-bound, encrypted, expiring, single-use login-flow state and session rotation.
- Opaque HttpOnly browser cookies; Entra tokens stay on the backend.
- Fernet-encrypted SQLite sessions/account/token caches, hashed cookie references,
  persistent encryption key and serialized cache updates across requests.
- CSRF token plus exact Origin checks for writes; explicit credentialed CORS,
  no-store responses, secure hosted cookies and explicit loopback HTTP development.
- Callback access-log suppression in the API launcher and no-referrer responses.
- Confirmed S1 mapping in the non-secret example mapping file. No email-prefix inference.
- Lazy agent initialization: sign-in can start before model configuration; agent
  use without model settings returns an operational error rather than a fake model.
- Private configuration selection through `HARNESS_ENV_FILE`.

### 3. Authenticated agent-to-MCP client

- Separate delegated token acquisition for FE and Zambeel using the server-side cache.
- An authenticated transport capability scoped to the request and copied into
  detached agent execution. Non-secret verified identity reaches `HarnessContext`.
- No tokens/session references in model arguments, graph messages, checkpoints or memory.
- Actor/role overrides, demo service-key use and fallback to demo authentication are refused.
- Explicit HTTPS enforcement, with an opt-in for loopback development only.
- Existing tool names/allowlists retained, including the original HITL names.
- Operational transport/protocol failures distinguished from deterministic refusals.
  Confirmation stays resumable after an outage; expiry triggers reauthentication.
- Sanitized API/stream errors instead of exposing OAuth/HTTP payloads.

### 4. Durable approved-case worker

- Additive `execution_jobs` outbox schema; one unique execution job per case.
- Transaction-safe enqueue helper for FE to call inside its approval transaction.
- Short database claims, expiring leases, stale-worker acknowledgement fencing,
  recovery scans and capped exponential retry backoff.
- Strict handling of `completed`, `terminal` and `retry` service outcomes.
- HTTP/auth/protocol failures remain operational jobs; they are not academic rejections.
- App-token acquisition via MSAL client credentials, independent of student sessions.
- A service-only client for `execute_approved_case(case_id)`; never model-visible.
- Same-case reconciliation after lost responses, plus explicit retry of repaired
  blocked jobs. Existing approval expiry is never silently renewed or bypassed.
- A submitted-case recovery hook for FE's trusted routing context.

**Worker primitives/client are implemented. FE's service endpoint, application
permissions and atomic approval/enqueue wiring are still integration dependencies.**

### 5. Frontend and dashboard changes

- Microsoft sign-in gate, mapped account display and local sign-out.
- Cookies/CSRF on JSON and streaming requests; 401/stream reauthentication clears
  mounted user state. Stale status responses cannot restore a logged-out UI.
- Demo identity switching/reset hidden in authenticated mode; demo mode is preserved.
- Zambeel profile and FE student cases/details use the existing MCP contracts.
- Non-overlapping session polling and recovered terminal chat display.
- Missing notification/instructor-list contracts are explicitly unavailable in BFF
  mode rather than being replaced with invented live data or personal SQL bypasses.

### 6. Terminal graph and memory reconciliation

After a worker finishes independently, an authorized session/history read can
reconcile the stale instructor pause using the saved terminal case/enrollment.
The system records a deterministic tool result/final message and one case-derived
memory note without another model call, new approval or enrollment attempt.
APPROVED alone is never treated as COMPLETED. This currently assumes shared FE
case storage and the single-VM deployment described in the handoff.

### 7. Tests, configuration and documentation

- Synthetic RSA/auth tests, mocked MSAL flows, encrypted-cache restart/concurrency,
  CSRF/replay/impersonation tests, resource-token/transport tests and stream expiry tests.
- Real local workflow/checkpoint reconciliation and worker lease/concurrency/
  lost-response tests; optional headless browser authentication smoke test.
- Explicit MSAL, PyJWT crypto and cryptography dependencies in the locked environment.
- Expanded non-secret configuration examples and ignored `.env.*.local` files.
- Engineering guide, worker handoff, decisions and M0-M9/WP0-WP9 integration crosswalk.

## What can run today

| Mode | What runs | Requirements / limits |
|---|---|---|
| Browser-only simulation | Existing scripted frontend demo | Node/npm only; no Python/model/Entra |
| Local agent demo | Real agent against the mock workflow | Model configuration and local approval secret |
| Local demo MCP | Existing FE/Zambeel demo transport | Local secrets; demo identity headers, loopback only |
| BFF login/client | Implemented login, session and authenticated-client code | Registered Entra app, private credential, mapping and consent; authenticated MCP servers needed for downstream calls |
| Service worker | Implemented queue/retry/service client | FE service endpoint, granted worker permission and shared case/outbox DB; not supplied by the current demo servers |

Only offline/mocked integration and Microsoft discovery/redirect have been
verified here. **A redirect is not a completed live sign-in or full enrollment.**

## Installation and execution

Commands below use **PowerShell**, starting at the repository root unless noted.
Use Python 3.11+, `uv`, and Node.js/npm compatible with the frontend's Vite setup.
The repository is already cloned; select `ammar` without discarding local work.
Use fresh terminals when switching modes so environment-file/authentication
overrides from a previous mode do not carry into the next one.

### 1. Install dependencies

```powershell
git switch ammar
uv sync --frozen
cd frontend
npm ci
cd ..
```

### 2. Preserve existing data and provision private configuration

For the local agent/demo, create `.env` from the example **only if absent**, then
edit it privately. Provision a model/provider and an approval secret of at least
32 characters. Do not put credentials in README, git, VITE variables or chat logs.

```powershell
if (-not (Test-Path '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
# Only initialize a NEW simulator; preserve any existing database.
if (-not (Test-Path 'data/harness.db')) {
    uv run python scripts/seed.py --db data/harness.db
}
```

Never use `scripts/seed.py --reset` on cases, audit or memory that must survive.
The explicit `--db` first-run command also avoids the seed script's default
memory-store cleanup. Existing records are not migrated/reset by these instructions.

Supported model examples (choose/provision one; these are not credentials):

| Provider | Required private settings |
|---|---|
| Databricks | `HARNESS_MODEL=databricks:<endpoint>`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN` |
| Azure OpenAI v1 | `HARNESS_MODEL=azure_v1:<deployment>`, HTTPS `AZURE_OPENAI_ENDPOINT` ending `/openai/v1/`, `AZURE_OPENAI_API_KEY` |

`HARNESS_MODEL` is authoritative. No model credentials are included in the branch.

### 3. Run just the browser simulation

```powershell
cd frontend
$env:VITE_USE_MOCK = 'true'
npm run dev -- --host localhost
```

Open **http://localhost:5173**. The frontend displays synthetic/demo data.
Stop with Ctrl+C. This mode does not test the real agent or Entra.

### 4. Run the existing real-agent local demo

Backend terminal, after provisioning `.env`:

```powershell
$env:HARNESS_AUTH_MODE = 'demo'
$env:HARNESS_USE_MCP = 'false'
uv run python -m harness.api
```

Frontend terminal:

```powershell
cd frontend
$env:VITE_USE_MOCK = 'false'
$env:VITE_API_BASE_URL = 'http://localhost:8000'
npm run dev -- --host localhost
```

At localhost:5173, use demo student S1 to request CS412 section S1 and confirm.
Switch to demo instructor I1 and approve; switch back to S1 to inspect the outcome,
audit and memory. Wrong instructor I2 must be refused. This is a model-backed
**synthetic local demo**, not authenticated university enrollment.

### 5. Optionally run the existing local MCP demo

Provision `HARNESS_MCP_SERVICE_SECRET` separately from `APPROVAL_SECRET`; each
must be at least 32 characters. Use the same intended simulator DB in each process.
Start each service in its own terminal with demo configuration:

```powershell
$env:HARNESS_AUTH_MODE = 'demo'
uv run python -m harness.mcp zambeel
```

```powershell
$env:HARNESS_AUTH_MODE = 'demo'
uv run python -m harness.mcp fe
```

Then start the API in another terminal:

```powershell
$env:HARNESS_AUTH_MODE = 'demo'
$env:HARNESS_USE_MCP = 'true'
uv run python -m harness.api
```

Default MCP endpoints are `http://127.0.0.1:8101/mcp` (FE) and port 8102 (Zambeel).
These servers use spoofable demo identity headers and must remain local. They
**do not accept Entra bearer tokens merely because the client supports them**.

### 6. Run backend-managed Entra login

Use a separate ignored `.env.bff.local`. On another machine it must be provisioned
privately; it is not distributed by git. `HARNESS_ENV_FILE` selects that file;
it does not automatically merge model settings from `.env`. Shell variables take
precedence, so start a fresh terminal rather than retaining demo overrides.

Required local settings (public values/placeholders only):

```dotenv
HARNESS_AUTH_MODE=bff
HARNESS_ENTRA_TENANT_ID=305b003b-4966-4335-ae28-1c377e906143
HARNESS_CLIENT_ID=a7baa7d9-576c-4be3-9bfe-ec5fedfd316c
HARNESS_CLIENT_SECRET=<provision privately>
HARNESS_CALLBACK_URL=http://localhost:8000/auth/callback
HARNESS_FRONTEND_ORIGIN=http://localhost:5173
HARNESS_COOKIE_SECURE=false
HARNESS_IDENTITY_MAP=seed/entra-users.example.json
HARNESS_AUTH_DB=data/auth.db
HARNESS_SESSION_KEY_FILE=data/auth.key
HARNESS_FE_SCOPE=api://04ce3e46-2e44-4c4c-949f-09ce52e2a17b/mcp.access
HARNESS_ZAMBEEL_SCOPE=api://9fd72d08-229f-4b7e-9733-7a23689c4cfa/mcp.access
HARNESS_FE_MCP_URL=<authenticated FE MCP endpoint>
HARNESS_ZAMBEEL_MCP_URL=<authenticated Zambeel MCP endpoint>
HARNESS_MCP_ALLOW_LOOPBACK=true
```

Set loopback allowance only for authenticated **local** HTTP services; use HTTPS
URLs and disable this allowance when hosted. Hosted cookies must be Secure and
URLs/origins/callbacks must match their registrations. Provision a persistent,
protected session key in hosted mode. Never delete the key/cache casually: the
key is needed to decrypt sessions across restarts, although cases persist separately.

The sample maps the confirmed project S1 tenant/Object ID to internal S1. Only
that external test account currently exists. Add further accounts through the
approved mapping/role process, not browser identity fields or email prefixes.

Backend:

```powershell
$env:HARNESS_ENV_FILE = '.env.bff.local'
uv run python -m harness.api
```

Frontend, separate terminal:

```powershell
cd frontend
$env:VITE_USE_MOCK = 'false'
$env:VITE_API_BASE_URL = 'http://localhost:8000'
npm run dev -- --host localhost
```

Open localhost:5173 and choose **Sign in with Microsoft**. Use localhost
consistently with the saved callback. The API exposes status at
`http://localhost:8000/auth/status`. Model settings are not needed just to start
login, but are required for agent requests. Provision them in the selected private
file or environment. Current demo MCPs cannot complete authenticated downstream calls.

### 7. Run the durable service worker, after FE is ready

First confirm FE implements `execute_approved_case`, grants `Cases.ExecuteApproved`
to the explicitly authorized worker app, and atomically inserts its approval/job.
The worker must share the FE case/outbox database under the agreed deployment.
Do not point it at the demo FE server or reuse a user token as a service credential.

Provision a separate ignored `.env.worker.local` containing:

```dotenv
HARNESS_DB=data/harness.db
HARNESS_ENTRA_TENANT_ID=305b003b-4966-4335-ae28-1c377e906143
HARNESS_WORKER_CLIENT_ID=<authorized worker application ID>
HARNESS_WORKER_CLIENT_SECRET=<provision privately>
HARNESS_WORKER_FE_SCOPE=api://04ce3e46-2e44-4c4c-949f-09ce52e2a17b/.default
HARNESS_WORKER_FE_URL=https://<authenticated FE hostname>/mcp
```

```powershell
$env:HARNESS_ENV_FILE = '.env.worker.local'
uv run python -m harness.worker --once
# Continuous operation, after configuration and one-attempt validation:
uv run python -m harness.worker
```

`--once` scans for missing execution jobs and attempts at most one ready job.
Continuous mode claims/retries work; Ctrl+C leaves unacknowledged leases recoverable.
The worker does not need student sessions, model credentials or APPROVAL_SECRET.
See [the worker handoff](docs/worker-handoff.md) for the exact FE transaction hook,
response contract, blocked-job retry and submission-recovery responsibilities.

## Tests and verification

```powershell
uv sync --frozen
uv run pytest -q -m "not live"
uv run pytest -q tests/test_api_auth.py tests/test_bff.py tests/test_authenticated_mcp.py tests/test_worker.py tests/test_reconciliation.py
# Run only after a simulator exists; this checks that particular database.
uv run python scripts/check_integrity.py --db data/harness.db
cd frontend
npm run typecheck
npm run build
```

Recorded implementation verification (16 November 2026):

| Check | Result / interpretation |
|---|---|
| Full offline suite | **315 passed, 11 live tests deselected** |
| Frontend typecheck/build | Passed |
| Browser auth smoke | Passed with explicitly fake auth/API responses |
| Real Microsoft discovery/redirect | BFF status 200 and Microsoft redirect 302; not a completed sign-in |
| Real Entra callback/token exchange | Not completed/verified |
| Live authenticated FE/Zambeel and worker enrollment | Pending external server/permission integration |
| Live model / Sakai / hosted acceptance | Not performed |

Tests exercise synthetic signatures, scope/role/identity refusal, callback replay,
CSRF, cache restart/concurrency, pre-stream/mid-stream expiry, tool isolation,
leases and competing claims, response-loss reconciliation, audit, idempotency and
terminal graph/memory repair. A lost-response test performs a real **local mock**
enrollment before raising a timeout, then verifies one saved enrollment on retry.

Optional browser check: build with `VITE_USE_MOCK=false`, make the Playwright Node
package/browser available (or set `NODE_PATH` to the bundled package directory),
then run from the repository root:

```powershell
# Optional when using an installed Edge browser:
$env:PLAYWRIGHT_CHANNEL = 'msedge'
node tests/browser-auth.cjs
```

The script starts/stops its own preview on port 4173 and intercepts fake backend
responses; it never validates real Microsoft credentials. Live tests require
explicitly provisioned services/model settings and should not be confused with this.

## What's left

**The branch is not fully live-integrated yet.** These are concrete remaining
items, with ownership and acceptance criteria rather than an unqualified TODO.

| Remaining item | Owner/dependency | Done when |
|---|---|---|
| Authenticated FE/Zambeel server validation | Nausherwan: issuer/JWKS, configured token version/audience, scopes, roles and identity mappings | Valid resource tokens work; wrong/expired/missing tokens fail before tools run |
| Service-only FE operation | Nausherwan: `execute_approved_case(case_id)`, `Cases.ExecuteApproved`, worker app allowlist | Approved case completes with app auth; delegated callers cannot use it |
| Atomic approval/job handoff | Coordinated FE change by Nausherwan using `jobs.enqueue_execution` | Approval and unique job commit/roll back together; no lost handoff on crash |
| Confirmed SUBMITTED recovery wiring | FE owner calls the supplied trusted recovery hook | A saved confirmation routes after restart without asking the student again |
| FE -> Zambeel service authorization/concurrency | Nausherwan: restricted FE app permission and saved-case/consumed-approval checks | Duplicate/concurrent/lost-response execution creates one authorized enrollment |
| Worker app/deployment configuration | Nausherwan + infrastructure owner | Permission/credential/URL and shared persistent DB are securely provisioned; worker survives restart |
| Instructor and additional test users | Nausherwan: account Object IDs, roles and mappings | Actual instructor ownership and cross-user refusals pass live tests |
| Model configuration | Private provider settings from the team | Model-backed agent runs work; no fake model substituted |
| Notification and instructor-list contracts | Nausherwan supplies agreed MCP operations; Ammar connects client/UI once supplied | Authenticated dashboard works through FE rather than personal SQL bypasses |
| Expired approval review/reapproval | Coordinated FE/workflow policy | Case is retained and explicitly reviewed after 24-hour approval expiry; no bypass/automatic renewal |
| Sakai integration | Hussain's verified per-user REST/SSO data + Nausherwan's Sakai MCP contract, then Ammar's client/UI work | Authenticated student sees their real project Sakai sites/due work, with isolation tests |
| Hosted deployment | Yahya: HTTPS, exact origins/callback, proxy streaming/log settings, restricted persistent files | Cookie/login/streams and worker recovery pass on the target host |
| Full live acceptance | Team, with Ammar verifying agent flow | Real S1 login -> eligibility -> confirmation -> real instructor approval -> student offline/backend restart -> one enrollment, complete audit and memory |

The current browser flow uses a query callback for registered loopback development.
MSAL recommends form_post; any hosted switch needs coordinated callback/login-cookie
handling. Current application run locks and shared SQLite assumptions target a
single API process/VM; multi-host or multi-process deployment needs review.
Real PeopleSoft/Registrar integration is separate project work, not a requirement
to pretend the current mock is a live university system.

## Files added or changed relative to main

The following inventory covers the implementation diff against `8e234b8`. Links
are the authoritative place to inspect each addition; this README is an additional
documentation-only change on `ammar`.

| Files | Branch contribution |
|---|---|
| [api/auth.py](src/harness/api/auth.py) | New bearer-verifier foundation, mapping and API ownership checks |
| [api/bff.py](src/harness/api/bff.py) | New backend login/session/encrypted token-cache implementation |
| [api/app.py](src/harness/api/app.py), [api/__main__.py](src/harness/api/__main__.py) | Auth routes/guards, credentialed CORS, lazy model startup, scoped execution, service-backed views and safe launcher logging |
| [api/events.py](src/harness/api/events.py), [context.py](src/harness/context.py) | Verified runtime context and sanitized stream reauthentication/error behavior |
| [api/views.py](src/harness/api/views.py) | Existing FE case/audit result projected into the current UI contract |
| [mcp/authenticated.py](src/harness/mcp/authenticated.py), [mcp/client.py](src/harness/mcp/client.py) | New authenticated capability/client dispatch; demo transport preserved explicitly |
| [clients.py](src/harness/clients.py), [tools/common.py](src/harness/tools/common.py) | Preserve pauses on operational failure and propagate reauthentication |
| [jobs.py](src/harness/jobs.py), [worker.py](src/harness/worker.py) | New outbox, leases, recovery, app-token transport and service worker CLI |
| [reconciliation.py](src/harness/reconciliation.py) | New deterministic terminal checkpoint/memory repair |
| [config.py](src/harness/config.py) | Explicit selection of private environment file |
| [frontend App](frontend/src/App.tsx), [frontend auth client](frontend/src/api/auth.ts) | Sign-in gate, stable mapped identity and stale-status protection |
| [httpApi.ts](frontend/src/api/httpApi.ts), [types.ts](frontend/src/api/types.ts) | Cookie/CSRF requests and stream reauthentication signal |
| [AppContext.tsx](frontend/src/state/AppContext.tsx), [Sidebar.tsx](frontend/src/components/layout/Sidebar.tsx), [ChatView.tsx](frontend/src/components/chat/ChatView.tsx) | Authenticated identity controls, unavailable-feature labels, serial polling and recovered outcome display |
| [S1 mapping example](seed/entra-users.example.json) | Non-secret confirmed project identity mapping |
| [.env.example](.env.example), [.gitignore](.gitignore) | Configuration surface and ignored private env files; no supplied secret is committed |
| [pyproject.toml](pyproject.toml), [uv.lock](uv.lock) | Explicit locked MSAL/PyJWT crypto/cryptography dependencies |
| [test_api_auth.py](tests/test_api_auth.py), [test_bff.py](tests/test_bff.py) | New credential, ownership, login/cache/CSRF/stream tests |
| [test_authenticated_mcp.py](tests/test_authenticated_mcp.py), [test_worker.py](tests/test_worker.py), [test_reconciliation.py](tests/test_reconciliation.py) | New transport, recovery/concurrency and terminal-result tests |
| [browser-auth.cjs](tests/browser-auth.cjs) | New optional Playwright smoke test against the built UI |
| [Engineering guide](docs/ammar-agent-integration.md), [worker handoff](docs/worker-handoff.md), [infrastructure crosswalk](docs/infrastructure-crosswalk.md) | New explanation, integration contract and milestone status |
| [CLAUDE.md](CLAUDE.md), [build plan](docs/build-plan.md), [decision log](docs/decisions.md), [frontend README](frontend/README.md) | Updated scope, decisions and execution guidance |

MCP server internals and the core approval/workflow implementation are not silently
rewritten by this branch. Their pending integration points are identified above.

## Further documentation

- [Ammar engineering guide](docs/ammar-agent-integration.md): before/after design,
  exact mechanisms, supervisor Q&A, contributions and limitations.
- [Worker handoff](docs/worker-handoff.md): transaction hook, service contract,
  lease/error behavior, permissions and operational commands.
- [Infrastructure crosswalk](docs/infrastructure-crosswalk.md): agent milestones
  mapped to WP0-WP9 and the three integration milestones.
- [Local MCP guide](docs/local-mcp.md): existing demo server/tool contracts.
- [Frontend guide](frontend/README.md): UI structure and original demonstration.
- [Test scenarios](docs/test-scenarios.md) and [decision log](docs/decisions.md):
  preserved workflow cases and engineering choices.

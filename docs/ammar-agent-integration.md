# Ammar: agent integration engineering record

Status: API authentication/authorization foundation plus durable worker components;
full integration pending. Worker protocol/runbook: [worker-handoff.md](worker-handoff.md).
Branch: `ammar`. Working date: 2026-11-16.
Baseline: `8e234b8ed627923c7715be856077d865fbe3bc8b`.

## 1. Context and scope

The baseline already implements a force-enrollment deep agent, eligibility checker,
student confirmation, instructor approval, deterministic execution, checkpointing,
student memory, audits, and a React/FastAPI application. These are existing team
contributions, not newly implemented in this branch.

Ammar owns agent/orchestrator integration. Nausherwan owns MCP server internals
and currently Entra administration while Saad is away. Hussain owns Sakai;
Yahya owns infrastructure. This branch does not configure their external systems.

The first increment protects the FastAPI boundary with verified credentials and
ownership checks. The second adds the execution outbox, lease/recovery primitives,
MSAL application-token provider and service-only MCP worker client. It does not
implement browser sign-in or server-side MCP permissions/endpoints.

## 2. Initial and current architecture

Baseline: browser supplies IDs -> FastAPI -> agent -> local tools or demo MCP.
SQLite stores sessions, cases, approvals, audit, checkpoints and long-term memory.

Current optional boundary:

```text
Bearer token for harness API
  -> ApiAuthorization
  -> EntraVerifier: RS256/JWKS, issuer, audience, lifetime, tenant, scope, role
  -> operator-managed (tid, oid) mapping
  -> route/resource ownership checks
  -> existing API handlers -> existing agent/workflow
```

This foundation supports testing API authentication against the local workflow.
It is not the target authenticated MCP deployment. `entra` mode refuses
`HARNESS_USE_MCP=true` while that would send spoofable demo headers downstream.
No silent authentication fallback occurs. Default `demo` preserves local operation.

The October infrastructure plan's Azure/placeholder hostnames are superseded by
the November Oracle/revsoft.net assignment. Actual endpoints remain external config.
Existing M0-M9 behavior is preserved; WP7 authentication is only partially addressed.

## 3. Identity and authentication

`src/harness/api/auth.py:EntraVerifier.verify` accepts a harness API access token.
An ID token is for sign-in; this API requires a delegated scope in `scp` and an
assigned role in `roles`, in addition to the correct API audience. A token issued
for FE or Zambeel is not accepted merely because Entra signed it.

The verifier fixes the algorithm to RS256 and uses tenant-specific public JWKS,
cached by PyJWT. It verifies signature, exact issuer, audience, expiry and issued-at
claims, checks tenant and v2 token version, and requires an object ID. Synthetic
tests replace only key retrieval, exercising actual RSA signature verification.

The scope is configured independently from the role. Scope authorizes delegated
API access; a role grants an application capability. Both are required. The
operator mapping must also agree with the role; an Instructor token cannot turn
a mapped Student into an instructor. Unknown identities are refused.

Mapping format (operator-managed file, synthetic values):

```json
[{"tenant_id":"tenant-guid","object_id":"object-guid","actor_id":"S1","role":"Student"}]
```

The stable key is `(tid, oid)`, not an email prefix. Duplicate identity entries
and unsupported roles fail configuration. The mapping currently permits one
role per identity; dual-role support is not inferred.

The compatibility API still includes actor IDs in paths/bodies. They are checked
against verified identity before execution, so they are not an authority source.
`/api/me` returns only mode, mapped actor ID and role. Credentials are not copied
into `HarnessContext`, LangGraph messages, SQLite checkpoints, memory or SSE.

Configured mode is chosen at startup. Missing settings, unknown modes and unsafe
demo-MCP combinations fail startup. Missing/invalid credentials receive 401 with
a Bearer challenge; missing scope/role/mapping or resource access receives 403.

## 4. MCP boundary and pending token acquisition

Existing read/write tool wrappers use `mcp/client.py` when enabled. They explicitly
select FE/Zambeel tools; no blind tool discovery grants model permissions. Each
call opens its own transport session with a timeout. Ambiguous writes are not
automatically retried by the transport. Existing workflow logic reconciles an
already-created enrollment by case ID.

No MCP contracts are changed here. Local headers are still demo claims; they
must be replaced by Nausherwan's validation and the agreed client token provider.
The updated agreed flow is FastAPI-managed authorization-code sign-in, an opaque
browser session cookie and protected server-side user token cache. FastAPI acquires
resource-specific user tokens directly through that cache; OBO is not needed for
this browser flow. Browser session/CSRF integration remains pending. The initial
bearer-verifier tests remain useful, but browser-facing API authentication must
be adapted to the verified server session rather than requiring browser tokens.

Dashboard views currently read shared SQLite directly. They must be adapted to
agreed MCP operations before claiming integrated service isolation. The current
contract lacks full instructor/notification dashboard coverage. No Sakai schema
or synthetic substitute is introduced in this branch.

## 5. LangGraph, sub-agents and HITL

`agent.py:build_agent` uses `create_deep_agent`. The eligibility checker has a
restricted read tool set and returns a structured verdict. Write tools remain
on the main agent; the generic sub-agent is disabled. Model instructions do not
override deterministic workflow authorization.

Installed HITL middleware matches registered tool names. Existing wrappers use
`submit_case` and `execute_enrollment`, matching FE names, so this increment does
not rename them. Submission pauses for student confirmation; execution pauses
for the owning instructor. Write decisions permit approve/reject, not argument
editing. The checkpointer persists pending tool calls. Resume supplies context
again, since runtime context is not the stored authorization credential.

The global API dependency runs before streaming handlers/dependencies launch a
worker. Invalid credentials therefore produce JSON errors before SSE begins.
The worker/relay separation remains unchanged: browser disconnect does not stop
an admitted run. Every later request must authenticate again. Mid-run token
expiry/revocation and downstream renewal policy remain integration work.

## 6. Persistence, idempotency and audit

Session ID = graph thread ID = associated case ID in the current application.
`persistence.py` uses SqliteSaver for execution state and SqliteStore for long-term
notes. Memory namespaces derive from the session's student. Authenticated API
requests cannot read a different student's memory/history or resume their session.
Protected rules/skills/memory routes retain read-only filesystem permissions.

The existing state machine advances DRAFT -> AWAITING_CONFIRMATION -> SUBMITTED
-> AWAITING_APPROVAL -> APPROVED -> EXECUTING -> COMPLETED, with refusal/failure
and cancellation paths. Existing transitions record audits transactionally.

Existing HMAC approval tokens are case-bound, owner-issued, expire after 24 hours,
and are consumed once. Enrollment uses case ID as its idempotency key. Execution
rechecks academic rules and reconciles an already-completed write. This branch
does not alter those safeguards or reset any database.

Durable state does not itself schedule work after a restart. `jobs.py` and
`worker.py` now implement leased jobs and recovery with a service-only FE operation
accepting case ID. Nausher must wire atomic enqueue into the approval transaction
and implement that endpoint. Student/section are resolved by FE from saved state.
No student/instructor token is relabelled. Expired approval requires review while
retaining the case. See the worker handoff for exact transaction and retry behavior.

## 7. Code changes

| File | Change and purpose | Verification |
|---|---|---|
| `api/auth.py` | Signed-token verification, mapping and global resource guards | Synthetic RSA and API ownership tests |
| `api/app.py` | Global authorization, `/api/me`, Bearer CORS/challenges | API regression suite |
| `api/__main__.py` | Accurate mode/loopback description | Review |
| `pyproject.toml`, `uv.lock` | Explicit PyJWT crypto dependency (previously transitive) | Frozen dependency sync |
| `.env.example` | Non-secret API-boundary settings and limitations | Review/configuration tests |
| `tests/test_api_auth.py` | Invalid credentials, roles, identity conflicts and route guards | Pytest |
| This document | Actual contributions, operation and pending integration | Code cross-check |
| `jobs.py`, `worker.py` | Durable outbox, fenced leases, recoverable service execution client | Worker failure/concurrency tests |
| `tests/test_worker.py`, `docs/worker-handoff.md` | Worker contract tests and exact FE integration handoff | Focused pytest/review |

Global authorization was chosen to cover all existing routes, including reads,
stop, notification writes and resume. Protecting only message endpoints would
leave memory/history and other direct-object references exposed. Existing route
contracts remain compatible, with mismatched IDs refused rather than trusted.

## 8. Execution trace

Locally tested API-boundary example: a synthetic RS256 harness token maps to S1.
ApiAuthorization verifies it, compares request IDs to S1, and admits session
creation. A request for S2's profile/memory is refused. A teacher token can list
I1's pending cases but cannot read/stop S1's chat session. Missing/expired
credentials fail before message streaming starts.

The baseline tested FE path still runs confirmation -> deterministic submission
-> instructor owner decision -> signed approval consumption -> one enrollment
-> audit/notification/case note. This increment has not demonstrated that entire
path through live Entra or authenticated MCP. Synthetic signatures are labelled
test credentials, not proof of portal configuration.

## 9. Tests and correctness

Baseline previously executed: 240 passed, 11 live tests deselected.
Full offline regression: 253 passed, 11 live tests deselected (131.48 seconds).
Two additional security tests were then added. The final focused run of
`test_api_auth.py`, `test_api_runs.py`, `test_api_views.py` and
`test_api_disconnect.py` passed all 40 tests; the authentication module alone
passed 15 tests. Live Entra/MCP/Sakai acceptance remains pending.
Frontend `npm run typecheck` and `npm run build` passed. `npm ci` reported three
existing development dependency advisories; `npm audit --omit=dev` reported zero.
No dependency upgrades were applied to the frontend.

Security tests catch wrong issuer/audience/tenant/version, expired credentials,
missing scope, incompatible role, unknown mapping, forged signatures, algorithm
substitution, malformed tokens, conflicting browser IDs, student instructor-route
access, cross-user memory/history/stop access and pre-stream authentication failure.
Mode tests prevent typo fallback and Entra API -> demo MCP credential propagation.
Existing tests cover approval integrity, eligibility races, checkpoints, enrollment
idempotency, sub-agent isolation and disconnect behavior.

## 10. Supervisor questions

- Why MCP? It provides a separately authenticated system/process contract; direct
  shared database access is still a migration gap in current dashboard views.
- Can the LLM choose another student? Model tool arguments do not select identity;
  API requests must match the server mapping before existing context is built.
- Is HITL enough? No. Approval ownership, signature, expiry, single-use consumption
  and academic rechecks remain deterministic workflow conditions.
- What if a token expires? The next bearer request fails verification. Browser
  session/user-cache renewal remains pending. Worker application tokens are
  acquired independently through MSAL; no demo fallback occurs.
- What if the process crashes? Checkpoints/cases survive; worker leases expire and
  approved/in-flight jobs are rediscovered. Full automatic completion still needs
  FE's atomic enqueue and service endpoint, plus graph/UI reconciliation.
- Why no async persistence rewrite? Current worker-based MCP integration already
  works; no evidence requires replacing the workflow engine for this increment.
- What protects memory? Verified route ownership plus existing context-selected
  student namespace and write-protected virtual filesystem.
- What is outside this branch? Tenant provisioning, server-side MCP authorization,
  Sakai installation, Oracle/DNS/proxy administration, real PeopleSoft integration.

## 11. Running and demonstrating

From repository root, PowerShell:

```powershell
uv sync --frozen
uv run pytest -q -m "not live"
uv run pytest -q tests/test_api_auth.py
# Existing demo only; configure model + approval secret in ignored .env first.
$env:HARNESS_AUTH_MODE = 'demo'
uv run python -m harness.api
# Optional existing demo MCP services, separate terminals:
uv run python -m harness.mcp zambeel
uv run python -m harness.mcp fe
# Frontend, separate terminal:
cd frontend
npm ci
npm run typecheck
npm run build
$env:VITE_USE_MOCK = 'false'
npm run dev
```

Use the existing synthetic S1/CS412-S1 confirmation and I1 approval demo. MCP
services require the existing local service secret; enable HARNESS_USE_MCP only
in demo mode. Never use demo identity on a public deployment.

For isolated Entra API-boundary validation set `HARNESS_AUTH_MODE=entra`, tenant,
harness API audience/scope and `HARNESS_IDENTITY_MAP`; leave demo MCP disabled.
Use a correctly scoped harness access token from the eventual agreed client.
The current React application still has demo account selection and no MSAL login,
so it cannot yet serve as an authenticated demonstration. Synthetic API tests
are the reproducible boundary demonstration without external credentials.

## 12. Submission and remaining dependencies

Partial branch increment only; no claim of full WP7 completion. See Git history
for this increment's SHA (a commit cannot contain its own final SHA).
Completed: optional API credential verification and ownership boundary, preserved
demo mode, isolated security tests. Pending: real registration/mapping provisioning,
backend-managed browser sessions/user MCP tokens, dashboard MCP coverage, live FE
service endpoint/atomic enqueue wiring, graph reconciliation, Sakai integration
and live acceptance. Worker implementation and tests are now available; live
unattended completion is not yet verified.

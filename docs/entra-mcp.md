# Entra MCP integration: nausher

Implemented against Ammar's BFF/worker branch (`74bf873`). This adds the MCP
receiving side, not a second browser login implementation. React keeps an opaque
cookie; FastAPI/MSAL keeps the user cache; each MCP receives its own access token.
No OBO flow or browser token storage was introduced.

## Portal prerequisites for live acceptance

Existing tenant: `305b003b-4966-4335-ae28-1c377e906143`.
Harness: `a7baa7d9-576c-4be3-9bfe-ec5fedfd316c`.
FE: `04ce3e46-2e44-4c4c-949f-09ce52e2a17b`.
Zambeel: `9fd72d08-229f-4b7e-9733-7a23689c4cfa`.

1. Both MCP API manifests must issue v2 access tokens
   (`api.requestedAccessTokenVersion = 2`). The validators intentionally reject v1.
   V2 `aud` must equal the receiving API's client ID.
2. Harness has delegated `mcp.access` on both APIs, with admin consent.
   Students have Student assigned on both APIs; instructors have Instructor on FE.
3. Create a dedicated worker registration/credential. On FE create an app role
   `Cases.ExecuteApproved`, allowed member type **Applications**. Grant it to the
   worker through API permissions/Application permissions and admin consent.
4. On Zambeel create two app roles, allowed member type **Applications**:
   `Academic.Read` and `Enrollment.ExecuteApproved`. Grant both to the FE
   application and admin-consent them. Create a private FE credential, separate
   from the harness and worker credentials.
5. Configure explicit worker and FE caller allowlists below. Service permissions
   alone never authorize an arbitrary application. Do not assign application-only
   execution roles to student/instructor users.

No portal permissions, credentials or manifests were changed by this code task.
The shared example mapping now contains S1/S2/I1/I2. The operator mapping used
by BFF and MCPs must point to that same four-account mapping; Sakai IDs remain
pending. No passwords or secrets belong in the mapping.

## MCP process configuration

Use separate private process environment files (HARNESS_ENV_FILE selects one).
Do not copy all credentials into every process.

```dotenv
HARNESS_MCP_AUTH_MODE=entra
HARNESS_ENTRA_TENANT_ID=305b003b-4966-4335-ae28-1c377e906143
HARNESS_FE_AUDIENCE=04ce3e46-2e44-4c4c-949f-09ce52e2a17b
HARNESS_ZAMBEEL_AUDIENCE=9fd72d08-229f-4b7e-9733-7a23689c4cfa
HARNESS_MCP_DELEGATED_CLIENT_IDS=a7baa7d9-576c-4be3-9bfe-ec5fedfd316c
HARNESS_IDENTITY_MAP=<absolute path to operator JSON mapping>
HARNESS_DB=<absolute path to existing shared case/academic database>
HARNESS_MCP_WORKER_CLIENT_IDS=<dedicated worker client ID>
HARNESS_MCP_FE_CLIENT_IDS=04ce3e46-2e44-4c4c-949f-09ce52e2a17b
```

FE process additionally requires:

```dotenv
APPROVAL_SECRET=<existing approval signing secret; preserve it>
HARNESS_FE_CLIENT_ID=04ce3e46-2e44-4c4c-949f-09ce52e2a17b
HARNESS_FE_CLIENT_SECRET=<FE credential, not harness credential>
HARNESS_FE_ZAMBEEL_SCOPE=api://9fd72d08-229f-4b7e-9733-7a23689c4cfa/.default
HARNESS_ZAMBEEL_MCP_URL=https://<academic MCP endpoint>/mcp
```

Zambeel needs public signing keys/configuration, not the FE private credential,
worker credential or approval signing secret. FE's application token is acquired
using MSAL client credentials. It never forwards a user token to another audience.

Launch `uv run --frozen python -m harness.mcp zambeel` and the equivalent `fe`.
Listeners remain loopback for this increment. Use a trusted HTTPS reverse proxy
for hosting. For local HTTP only, explicitly set HARNESS_MCP_ALLOW_LOOPBACK=true
on the API, FE and worker. The worker's ServiceExecutor now accepts this explicit
loopback option while retaining HTTPS by default.

MCP server mode is independent of HARNESS_AUTH_MODE=bff on FastAPI. Set
HARNESS_MCP_AUTH_MODE=entra explicitly on the servers. Demo mode retains old
loopback headers/stdio behavior; Entra HTTP ignores those headers, requires bearer
credentials and forbids stdio actor authentication. This integration supports the
preconfigured BFF/worker clients; generic OAuth discovery/Inspector automatic
registration is not claimed.

## Authorization and tool compatibility

Delegated calls require RS256 signature, tenant-specific issuer, v2 version,
audience, valid lifetime, oid, allowed azp, mcp.access, and mapped app role.
User mapping uses (tid, oid); role assignment must agree with the mapping.
Signing keys are fetched from a fixed trusted Entra key endpoint and cached.
Invalid credentials return 401; insufficient claims return 403; unavailable keys
return 503. Errors/logs do not include bearer values or OAuth payloads.

Public student/instructor tool names remain stable. Worker execution is new:
`execute_approved_case(case_id)` requires an app-only worker principal with
Cases.ExecuteApproved. It is never in the agent/subagent allowlists.

FE internal reads require Academic.Read on an allowed FE application. Internal
get_student_record(subject_id), academic_catalogue(), and eligibility_record's
optional subject_id are service contracts, not model-facing identity overrides.
The service may read academics needed for routing; it cannot act as a delegated
student. Enrollment takes saved case_id/offering_id and derives the student from
the database, checking consumed owner approval, case state and audit evidence.
Enrollment additionally requires Enrollment.ExecuteApproved.

FE public domain refusals retain error/error_type; authenticated messages are
sanitized. Academic domain refusals are distinct from operational failures.
Temporary transport failures leave approved/in-flight cases retryable rather
than marking a potentially successful enrollment as academically failed.

## Durable handoff and concurrency

Approval now initializes the additive job schema before its transaction and calls
jobs.enqueue_execution after APPROVED inside that SAME transaction. Failure rolls
back both approval and job. Job payloads have no user tokens.

FE lifespan runs a periodic trusted recovery scan (5 seconds), routing confirmed
SUBMITTED cases and recovering missing APPROVED/EXECUTING jobs. Recovery requires
FE service credentials, never a user's cookie. Failures remain for reconciliation.

execute_approved_case returns Ammar's exact fields:
case_id, state, outcome (completed/terminal/retry), retryable, enrollment_id,
error_code, message. Unknown cases/operational configuration errors are MCP errors
and become blocked worker jobs. Temporary academic-service outages and busy cases
return retry. Expired unconsumed approval returns terminal TOKEN_EXPIRED; there is
no silent renewal. Academic eligibility/cap checks still apply after approval.

All MCP FE execution paths share an OS advisory file lock per case. Submission,
decision and routing paths use the same lock to avoid racing recovery. Locks are
on the shared database's local filesystem, released by the OS when a process dies;
files must not be deleted while services run. This is deliberately a **single VM,
shared database/local filesystem** design. It is not distributed locking across
separate hosts. Zambeel independently retains SQLite BEGIN IMMEDIATE + unique
case idempotency keys. No database write transaction is held across HTTP calls.

The worker still owns durable job leases and graph/memory reconciliation stays
with Ammar's implementation. The worker does not run a student agent or mint
approval tokens. The existing 24-hour approval expiry remains enforced.

## Tests and acceptance boundary

Run with explicit settings to keep local .env networking flags out of offline tests:

```powershell
$env:HARNESS_AUTH_MODE='demo'
$env:HARNESS_MCP_AUTH_MODE='demo'
$env:HARNESS_USE_MCP='false'
uv run --frozen pytest -q -m 'not live'
```

tests/test_mcp_entra.py uses production validation with generated RSA keys and
real local HTTP FE/Zambeel servers. It covers invalid claims/signatures, separate
audiences, roles, service allowlists, impersonation denial, ownership, atomic job
rollback, concurrent execution, process-death lock release, expired approval,
confirmed-submission recovery, BFF client compatibility, worker HTTP execution,
and response-loss recovery with one enrollment and intact audit.

This is not live Microsoft sign-in acceptance. After portal service provisioning,
test a real BFF callback, student read/confirmation, I1 approval, worker completion
with student offline, and restart recovery. No real PeopleSoft/Sakai integration
or hosted deployment is included. Missing instructor/notification dashboard
contracts identified by Ammar remain separate work; this change does not invent
those responses.

Validation on Windows (2026-11-17): full offline regression 349 passed, 11 live
tests deselected. After the final terminal-rejection handling change, all 35
Entra-focused tests passed. The suite emits one existing SDK/Pydantic settings
annotation warning. No real Entra token issuance or hosted acceptance was run.

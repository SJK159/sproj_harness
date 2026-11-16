# Approved-case worker: FE handoff

Integration update (nausher, 2026-11-17): the MCP endpoint, token validation,
atomic approval hook and FE recovery below are implemented on nausher.
See [entra-mcp.md](entra-mcp.md) for the current runbook and remaining portal/live
acceptance prerequisites. The original handoff below records the baseline contract.

Implementation date: 2026-11-16. Branch: `ammar`.
This implements Ammar's side of the agreed recovery contract. Nausher's service
endpoint, permission checks and atomic approval integration are still required.
The executable refuses demo HTTP transport and does not call the language model.

## Owners and transaction boundary

- Ammar: `harness.jobs`, `harness.worker`, worker tests/runbook.
- Nausher: FE `execute_approved_case(case_id)`, application authentication,
  `Cases.ExecuteApproved` + explicit worker app allowlist, FE -> Zambeel
  `Enrollment.ExecuteApproved` authorization and concurrency/idempotency gates.
- Shared approval boundary: Nausher must insert the enqueue call below INSIDE
  the existing approval transaction. No shared workflow/approval/server file
  has been modified by this increment.

At FE startup, before serving decisions, on the case database connection:

```python
from harness import jobs
jobs.initialize(conn)
```

Inside `approvals.record_decision`, AFTER its APPROVED transition and BEFORE
its existing `with conn:` block exits:

```python
if decision == "APPROVE":
    jobs.enqueue_execution(conn, case_id, now=time.time())
```

Initialize the schema before this transaction; import `time` as needed. Do not
call enqueue after `decide` returns: the existing implementation already commits
inside `record_decision`, so an outer `with conn:` does not make that atomic.
The helper requires an active transaction and deliberately never commits it.
Approval rollback rolls back the inserted job too. Case ID is the unique job key;
metadata contains scheduling/lease/result fields, not tokens or student/section.

The worker's recovery scan backfills missing APPROVED/EXECUTING jobs, but this
is a migration/reconciliation safety net, not a replacement for atomic enqueue.
It never resets succeeded, terminal or blocked jobs.

## Confirmed SUBMITTED cases

`jobs.recover_submitted(conn, route_case)` scans saved SUBMITTED cases and invokes
a trusted FE-side deterministic routing callback. It never asks the student to
confirm again. It must run in FE's authorized academic-service context, e.g. a
callback that resolves the student from the saved case and calls `workflow.submit`.
Do not expose a general worker impersonation header or store delegated tokens.

This hook is tested against the existing local workflow. It is not automatically
run by the external worker: the agreement does not yet define an authenticated
service operation for routing submissions, and that worker's permission only
authorizes approved-case execution. FE should wire the hook at startup/periodically
with its own service context. Failed routing returns `needs_reconciliation`.

## Lease and retry protocol

`claim` uses BEGIN IMMEDIATE then commits before any network call. A new random
lease token fences each claim. Expired running jobs are claimable by another
worker; acknowledgements require the matching unexpired lease token. A stale
process cannot overwrite a later worker's result. Leases coordinate jobs only;
FE/Zambeel must independently make concurrent enrollment retries safe.

Each attempt has a 30-second total deadline and a 90-second lease. Crash or
cancellation leaves a lease that expires naturally. Transport timeouts and lost
responses retry with the same case ID, with exponential delay capped at 300 seconds.
There is no retry limit that silently discards unfinished work. Enrollment safety
comes from FE's case-bound authorization and idempotency, not assuming a timeout
means no write occurred. Significant clock skew across worker hosts is unsupported;
use the agreed single-VM synchronized-clock deployment.

Result handling validates case binding, required fields, field types, known case
states, outcome/retryable consistency and completed enrollment ID. `completed`
becomes succeeded; `terminal` is retained for review; `retry` is rescheduled.
The worker stores bounded error identifiers, never raw remote messages, exceptions,
OAuth responses or tokens. Academic decisions remain exclusively FE's responsibility.

HTTP 401/403 and other non-retryable HTTP errors, unknown MCP tool errors, invalid
results and token acquisition failures become **blocked operational jobs**, not
academic rejection. HTTP 429/5xx and transport failures retry. Nested transport
exception groups are inspected without losing this distinction. A key/credential
or schema configuration error requires an explicit operator retry after repair:

```python
jobs.retry_blocked(conn, case_id, now=time.time())
```

This does not retry terminal academic/approval outcomes. An expired unconsumed
24-hour approval must be returned as terminal with an error code such as
TOKEN_EXPIRED. It is not silently renewed. Existing APIs do not yet implement
the renewed-approval workflow; that remains a coordinated integration item.

## Transport and credentials

`ServiceExecutor` opens an HTTPS MCP session, sends only an FE-audience bearer
token, and calls exactly `execute_approved_case` with `{case_id}`. It never sends
X-Demo-Actor, X-Demo-Role, student IDs, section overrides, or the local service key.
It is not registered in any agent/sub-agent tool list.

`ClientCredentials` uses MSAL ConfidentialClientApplication and
acquire_token_for_client with the FE resource's `/.default` scope. MSAL maintains
the app-token cache in memory and obtains replacement tokens. Application
permissions and explicit caller-app restrictions are checked by FE. Secrets
are supplied in the process environment from protected provisioning, never the
job database, command-line arguments, model context or source control.

Browser/backend-managed user sessions are separate work; this worker does not
depend on browser cookies or student/instructor delegated tokens. The updated
agreed browser architecture uses backend auth-code sign-in and server-side cache,
replacing the earlier proposed browser-bearer/OBO flow.

## Running

Required settings (non-secret placeholders only):

```text
HARNESS_DB=<the FE case/outbox SQLite file>
HARNESS_ENTRA_TENANT_ID=<tenant ID>
HARNESS_WORKER_CLIENT_ID=<authorized worker app ID>
HARNESS_WORKER_CLIENT_SECRET=<securely injected>
HARNESS_WORKER_FE_SCOPE=api://<FE app ID>/.default
HARNESS_WORKER_FE_URL=https://<FE hostname>/mcp
```

The worker needs access to the agreed shared case/outbox SQLite file; it does not
require APPROVAL_SECRET or Zambeel credentials. If FE and worker do not share
that file, a separate job-access contract is required rather than copying databases.

```powershell
uv sync --frozen
uv run pytest -q tests/test_worker.py
uv run python -m harness.worker --once
# Supervised long-running process, once the live endpoint is available:
uv run python -m harness.worker
```

`--once` scans for missing execution jobs then attempts at most one ready job.
Continuous operation scans between attempts and sleeps when idle. Stop with
Ctrl+C or the process supervisor; an unacknowledged job is reclaimed after expiry.
Do not start against the current demo server; it has no service-only operation.

## Verification and pending integration

32 focused offline tests passed. They exercise transaction rollback,
unique jobs, missing-job recovery, separate-connection competing claims, lease
expiry/stale acknowledgements, timeout/cancellation, classification, explicit
operator retries, expired-approval result handling, and confirmed-submission
routing. A lost-response test calls the REAL LOCAL deterministic enrollment then
raises a timeout: retry returns the saved enrollment with one row and intact audit.
The service adapter test uses fake MCP transport to inspect token/arguments.
No real Entra, FE service endpoint or hosted worker acceptance has been performed.
Full offline regression also passed: 286 tests, 11 live tests deselected, in
134.89 seconds. One final MSAL-provider test was added during review and the
complete focused worker suite subsequently passed all 32 tests. `uv sync --frozen`
and the worker CLI help check also passed. Frontend files were not changed.

Pending cross-lane acceptance:
1. Atomic approval/outbox insertion by FE and FE-side SUBMITTED recovery wiring.
2. FE application-token validation and execute_approved_case response contract.
3. Safe concurrent execution and transient-error handling inside FE/Zambeel.
4. App registrations, granted service permissions and secure deployment config.
5. Terminal graph/memory/UI reconciliation is now implemented in Ammar's BFF
   increment (`reconciliation.py` and API session/history reads), tested against
   real local workflow/checkpoints. Live shared-DB/server validation remains.
   The worker never drives an LLM under a fake student identity.
6. Explicit renewed-approval handling after terminal expiry, plus live tests.

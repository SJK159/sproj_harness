# Local MCP servers on mock Zambeel

This is a local development mode, not university authentication. The servers bind
to `127.0.0.1`. `X-Demo-Actor` and `X-Demo-Role` are explicit demo identity claims;
any local caller can claim them. Do not expose these servers to a network.
Entra, Azure, Sakai and real PeopleSoft integration are not included.

## Install and seed

From the repository root in PowerShell:

```powershell
uv sync --frozen
# Run only for a fresh database, or when intentionally resetting demo records:
uv run python scripts/seed.py
```

Keep the project's existing model configuration for agent runs. Direct MCP calls
and offline tests do not require a model account.

Generate two DIFFERENT secrets and put them in the git-ignored `.env` (never in
source code). Each must be at least 32 characters:

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```dotenv
APPROVAL_SECRET=<approval signing secret, FE server only>
HARNESS_MCP_SERVICE_SECRET=<different local service credential>
```

The Zambeel server does not use `APPROVAL_SECRET`. For process-level separation,
give it an environment file without that secret. Both servers and the agent must
use the same absolute `HARNESS_DB` path in this first local version. Checkpoints,
case-note storage, and API read views remain local to the existing application.
Physical database separation is deferred.

## Start servers

In separate terminals, from the repository root:

```powershell
uv run python -m harness.mcp zambeel
```

```powershell
uv run python -m harness.mcp fe
```

Endpoints are `http://127.0.0.1:8102/mcp` (Zambeel) and
`http://127.0.0.1:8101/mcp` (FE), using MCP Streamable HTTP. `--port` overrides
the listener; set `HARNESS_ZAMBEEL_MCP_URL` / `HARNESS_FE_MCP_URL` on callers
accordingly. FE must know the Zambeel endpoint.

Both also support local stdio discovery, e.g.:

```powershell
uv run python -m harness.mcp zambeel --transport stdio --actor S1
```

FE still calls the HTTP Zambeel service. Stdio callers cannot access internal
service-only academic tools.

## Connect existing agent and UI

In the application terminal:

```powershell
$env:HARNESS_USE_MCP = 'true'
uv run python -m harness.cli --student S1
# Or use the existing FastAPI / React application:
uv run python -m harness.api
```

The existing tool schemas, sub-agent allowlist, confirmation cards and instructor
approval pauses remain. Tools are explicitly wrapped, not blindly imported from
server discovery: the student agent cannot call `confirm_case`, `decide_case`,
or raw `enroll`. Set the same MCP flag for `scripts/approve.py` when using it to
resume a paused agent. Instructor decisions still resume the existing LangGraph
thread via the normal client; a standalone `decide_case` records the decision
but does not itself drive a graph.

Unset `HARNESS_USE_MCP` to retain the original in-process mode. This preserves
the original offline tests and offers a controlled migration path.

## Direct MCP clients / Inspector

Configure these HTTP headers in the MCP client (not in tool arguments):

```text
X-Demo-Actor: S1
X-Demo-Role: student
```

For instructor operations use `I1` / `instructor`. Only the FE service receives
`X-FE-Service-Key` when making internal academic calls. The key does not replace
an approval: raw enrollment also requires the matching case, a consumed owner
approval and its audit row. Missing demo headers and invalid supplied service
keys are refused before tool execution.

Zambeel public reads: `get_my_profile`, `get_my_enrollments`, `list_offerings`,
`list_sections`, `check_my_eligibility`, `scan_my_fe_options`.
Service-only: `get_section`, `course_details`, `eligibility_record`,
`enrollment_result`, `enroll`.

FE tools: `prepare_case`, `confirm_case`, `submit_case`, `execute_enrollment`,
`decide_case`, `get_my_cases`, `get_case_status`, `notify_student`.
Domain refusals from FE are structured as `error` / `error_type`; the client
turns them back into exceptions. MCP clients must check this envelope as well as
protocol `isError` results.

The `force_enroll(school, course, section)` prompt supports argument completions
from the catalogue. It is a request template, never permission to execute.
The React frontend has not been changed to render a `/fe` dropdown.

## Lifecycle and safety

1. Check eligibility on Zambeel MCP.
2. Prepare a case on FE MCP (eligibility is checked again).
3. Student client records confirmation, then the agent submits it.
4. FE rechecks eligibility and routes to the instructor.
5. Instructor client records the owner decision; approval token stays on FE.
6. Resume the agent. FE verifies/consumes approval, rechecks student rules, then
   calls Zambeel enrollment with the case ID as its idempotency key.
7. FE records completion/failure and the system notice. Existing agent tools
   write the case-derived long-term memory note.

An ambiguous transport failure must leave execution retryable: retry using the
same case ID, never create another enrollment key. If the backend already wrote
the enrollment, the retry discovers it and finishes the case without consuming
another approval or enrollment slot. Logical refusal (invalid approval, rule
failure, exhausted cap) follows the existing terminal failure path.

## Tests

```powershell
uv run pytest -q -m 'not live'
uv run pytest -q tests/test_mcp.py
```

MCP tests launch two real loopback server subprocesses with temporary databases
and test credentials. They require no running demo servers, model, or external
service, and terminate their subprocesses after each test.

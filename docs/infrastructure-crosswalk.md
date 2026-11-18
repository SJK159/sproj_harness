# Agent milestones and infrastructure work packages

Updated 2026-11-19. M0-M9 record the original mock agent build. Ammar owns
Agent/Orchestrator; Nausherwan currently covers MCP and Entra while Saad is away.
November's Oracle/revsoft.net plan supersedes October's Azure/placeholder hosting.
The original PDFs are not overwritten.

The user's latest instruction limits active automation work to **force enrollment**.
Sakai and other planned automations are outside this increment, regardless of the
broader November plan. Nausher's published `e7e3ad6` is integrated into `ammar`.

| Work package / numbered milestone | Current evidence | Remaining acceptance / owner |
|---|---|---|
| WP0-WP3 prerequisites/identity | Tenant, harness app, callback, scopes, consent and S1/S2/I1/I2 mappings supplied | Live role/v2-token checks and separate FE/worker service provisioning; Nausher |
| WP4, milestone 1: Sakai via Entra | Teammate reports completion; not independently validated here | Outside active force-enrollment scope |
| WP5 Sakai REST | Not needed for force enrollment | Outside current scope |
| WP6a local mock MCP | Existing tools/prompts/completions and offline tests work | Preserve contracts during migration; Nausher |
| WP6b, milestone 2: MCP via Entra | Nausher's JWT/scope/role checks, worker-only operation, FE-to-Zambeel app calls, atomic outbox and periodic recovery integrated/tested locally | Actual Entra service grants/credentials and issued-token acceptance; Nausher |
| WP7, milestone 3: agent via Entra | BFF/cache/CSRF, verified context, sign-in, MCP client, worker/reconciliation and four full-stack scenarios tested | Real callback/model/instructor/worker acceptance and hosted test |
| WP8 PeopleSoft | Mock remains explicitly synthetic | Registrar/PeopleSoft outside Ammar's scope |
| WP9 docs | Engineering guide, worker handoff, decisions and tests updated | Add actual live/deployment evidence when available |

## M10: authenticated integration and durable recovery

Implemented locally: backend-managed code flow/session cookie, encrypted cache,
stable identity mapping, per-resource tokens, detached-thread propagation,
preserved HITL names/permissions, leased worker and terminal checkpoint/memory
reconciliation. M0-M9 demo behavior remains available explicitly.

Server integration implemented: atomic approval/enqueue, service endpoint and
FE SUBMITTED recovery. The new full-stack test uses the BFF/graph/subagent and
real HTTP MCP validators/workflow/worker, with synthetic token issuance and model
replies. It covers approval/offline/restart, rejection, ineligibility and cancellation.

Missing notification/instructor-list contracts remain a UI gap; instructors can
open owned cases by ID. Live evidence pending: real callback, role grants, model,
instructor approval and service-worker enrollment after restart. Sakai is outside
active scope. See [the acceptance report](force-enrollment-acceptance.md).

Code implementation, mocked tests, a Microsoft redirect and full live acceptance
are separate statuses. Existing sync graph execution is preserved; BFF supersedes
the older browser-bearer/OBO proposal.

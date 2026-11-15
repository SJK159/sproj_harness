# Agent milestones and infrastructure work packages

Updated 2026-11-16. M0-M9 record the original mock agent build. Ammar owns
Agent/Orchestrator; Nausherwan currently covers MCP and Entra while Saad is away.
November's Oracle/revsoft.net plan supersedes October's Azure/placeholder hosting.
The original PDFs are not overwritten.

| Work package / numbered milestone | Current evidence | Remaining acceptance / owner |
|---|---|---|
| WP0-WP3 prerequisites/identity | Tenant, harness app, callback, scopes, S1 OID and consent supplied | Instructor/additional users, worker permissions and token-version agreement; Nausher |
| WP4, milestone 1: Sakai via Entra | Not verified by this branch | SSO/mapped-user evidence; Hussain/identity owner |
| WP5 Sakai REST | No verified table/fixtures supplied | Per-user REST contract; Hussain |
| WP6a local mock MCP | Existing tools/prompts/completions and offline tests work | Preserve contracts during migration; Nausher |
| WP6b, milestone 2: MCP via Entra | Client sends resource-specific user tokens; worker sends FE app token | Server JWT/scope/role checks, service endpoint/permissions, Sakai MCP; Nausher |
| WP7, milestone 3: agent via Entra | BFF sessions/cache/CSRF, verified context, frontend sign-in, MCP client, worker/reconciliation implemented/tested | Live callback/tokens/services, instructor, model configuration and hosted end-to-end test |
| WP8 PeopleSoft | Mock remains explicitly synthetic | Registrar/PeopleSoft outside Ammar's scope |
| WP9 docs | Engineering guide, worker handoff, decisions and tests updated | Add actual live/deployment evidence when available |

## M10: authenticated integration and durable recovery

Implemented locally: backend-managed code flow/session cookie, encrypted cache,
stable identity mapping, per-resource tokens, detached-thread propagation,
preserved HITL names/permissions, leased worker and terminal checkpoint/memory
reconciliation. M0-M9 demo behavior remains available explicitly.

Server integration pending: atomic approval/enqueue hook and service endpoint,
FE-side SUBMITTED recovery, missing notification/instructor-list contracts.
Live evidence pending: S1 callback, instructor approval, service-worker enrollment
after restart and Sakai due work.

Code implementation, mocked tests, a Microsoft redirect and full live acceptance
are separate statuses. Existing sync graph execution is preserved; BFF supersedes
the older browser-bearer/OBO proposal.

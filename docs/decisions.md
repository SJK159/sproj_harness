# Decision log

Format: date, decision, why, alternatives considered.

## 2026-09 (proposal stage)

**Single orchestrator, bounded tools, not a multi-specialist-agent swarm.**
Why: fewer independent reasoning surfaces to secure and audit.
Alternative: the earlier design with ~11 domain agents (finance, hostel, CCA, ...) plus approval/notification/audit agents.

**Mock Zambeel with synthetic data.**
Why: no confirmed PeopleSoft Integration Broker / REST access yet; the browserless login found during investigation is web-session automation, not a supported API.

**Signed, single-use approval token required for every write.**
Why: no write should proceed on LLM judgment alone (BRD FR-06, NFR-01).

## 2026-10-17 (build start)

**Use the `deepagents` harness for the orchestrator.**
Why: the goal of this phase is to exercise deep agent concepts (planning, sub-agents, HITL, memory, skills) on a real workflow.
Alternative: plain LangGraph `StateGraph` with checkpointer + `interrupt()` (the primer's lean option). Still a valid fallback for the fixed workflow; revisit after M7.

**Enforce the write gate inside `execute_enrollment`, not in a separate graph.**
Why: lets the agent own the full flow (including HITL via `interrupt_on`) while keeping "zero unauthorized writes" provable: the tool refuses without a valid token, whatever the LLM does.
Alternative: keep the write path in a deterministic workflow graph the agent can only start.

**One thread per case (`thread_id = case_id`).**
Why: the instructor resumes days later from a different session; the student's normal chat is not blocked by a paused approval.

**Hand-written skill file instead of RAG for now.**
Why: RAG is owned separately and out of scope for this phase; a skill file also demonstrates on-demand context loading.

**SQLite checkpointer, not MemorySaver.**
Why: the demo must survive a process restart between pause and instructor approval.

## 2026-10-17 (findings from reading deepagents 0.7.28 source)

**Long-term store is `SqliteStore`; Postgres fallback dropped.**
Why: `langgraph.store.sqlite.SqliteStore` ships with `langgraph-checkpoint-sqlite`, so checkpoints and long-term memory both live in local SQLite files with no extra server.
Alternative: `PostgresStore`. Only needed for a multi-process deployment (Phase 2).

**HITL on `submit_case` and `execute_enrollment` allows only approve / reject.**
Why: `interrupt_on={"tool": True}` allows four decisions: approve, edit, reject, respond. `edit` lets whoever resumes rewrite the tool args (e.g. case_id); `respond` skips the tool and returns a fake success message to the model. Neither is wanted on a governed write path. The token check in `execute_enrollment` stays the real gate either way.
Alternative: `True` (all four). Rejected for the reasons above.

**Write tools only on the main agent; `general-purpose` sub-agent disabled by default.**
Why: deepagents adds a `general-purpose` sub-agent automatically, and a declarative sub-agent without a `tools` list inherits the main agent's tools. That would put `submit_case` / `execute_enrollment` on a second reasoning surface. Disabling it keeps one agent holding write authority, matching the single-orchestrator decision. Revisit in M4 if there is a concrete need.
Alternative: keep it and rely on the token gate alone. Safe for enrollment writes, but `submit_case` has no token, so a sub-agent could still create cases.

**Backend routing: `/skills/` on disk, `/memories/` in the store per student.**
Why: deepagents reads skills and memory files through the backend, not the local disk. With the default `StateBackend`, `skills/` would be invisible unless passed into every invoke. Routing `/skills/` to a `FilesystemBackend` on the repo folder keeps the skill file editable in git. `/memories/` goes to a `StoreBackend` whose namespace comes from `rt.context.student_id`, so one student's notes are unreachable from another student's run (NFR-06). `seed/agent_rules.md` is copied into the store as `/memories/AGENTS.md` at startup because the memory loader reads it from the backend.
Alternative: put rules and skill text in the system prompt. Loses on-demand loading and the per-student isolation.

**Skill rules carry citable labels, e.g. `FE-1 (placeholder v0.1)`.**
Why: BRD FR-03 / NFR-07 require citing the policy section and version. Without RAG, a labelled hand-written rule is the smallest thing that keeps that requirement testable. The `placeholder` tag makes clear it is not official LUMS policy.
Alternative: drop citations until RAG exists. Rejected: the acceptance criteria would silently lose a Must requirement.

**Eligibility verdict uses `response_format` (structured output).**
Why: the main agent gets a fixed schema (eligible, failing_check, reason) instead of free text, so the "only the verdict comes back" claim in M4 is checkable and the main agent cannot misread it.
Alternative: free-text verdict parsed by the prompt. Less reliable, harder to test.

## Open

- deepagents package vs plain LangGraph for the final system: take evidence from M5 to M7 to the supervisor.
- Whether the LangGraph checkpointer can replace the `WORKFLOW_CASE` table. Current answer: no, checkpoints are opaque and not queryable for status (UC-02) or RBAC, so the cases table stays the source of truth.

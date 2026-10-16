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

## Open

- deepagents package vs plain LangGraph for the final system: take evidence from M5 to M7 to the supervisor.
- Whether the LangGraph checkpointer can replace the `WORKFLOW_CASE` table. Current answer: no, checkpoints are opaque and not queryable for status (UC-02) or RBAC, so the cases table stays the source of truth.

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

**Dev model: Databricks Free Edition, endpoint `databricks-gpt-oss-120b`.**
Why: no-cost access to an open-weights reasoning model with working tool calling. Checked on 2026-10-17: plain call, tool call, and a full tool round trip (model -> tool -> model) all succeed. `databricks-gpt-oss-20b` is the fallback.
Limits: Free Edition is under a fair-usage policy whose quotas are not published. Going over shuts the workspace's compute down for the rest of the day (in extreme cases the month). Non-commercial use only. So automated tests stay offline (no LLM in M1/M2, fake models where possible later) and live runs are kept to demo scripts. A paid model is possible for M7 and the supervisor demo; switching is an `HARNESS_MODEL` change.
Alternative: a paid provider (Anthropic / OpenAI / Google) from the start. Costs money per run during development.

**Call Databricks through `ChatOpenAI` on `<host>/serving-endpoints`, Chat Completions only.**
Why: Databricks Model Serving exposes an OpenAI-compatible Chat Completions API. `langchain-openai` is a small client library already needed, and it handled gpt-oss's `[reasoning, text]` content blocks and tool calls in our tests. `use_responses_api=False` because Databricks does not serve the Responses API. `config.get_chat_model()` maps `HARNESS_MODEL=databricks:<endpoint>` to it; the installed `init_chat_model` has no `databricks` provider, so this mapping is needed either way. Nothing is sent to OpenAI.
Alternative: `databricks-langchain`'s `ChatDatabricks`. Officially supported, but pulls in mlflow, unitycatalog-langchain, databricks-mcp and databricks-sdk, and resolves credentials through the SDK's own config lookup. Not tested.
Note: `langchain-anthropic` and `langchain-google-genai` were dropped from our deps but stay installed, because deepagents itself requires them.

**`write_todos` is opt-in in deepagents 0.7.28: add `TodoListMiddleware` explicitly.**
Why: a bare `create_deep_agent` in 0.7.28 gives `ls, read_file, write_file, edit_file, delete, glob, grep, execute, task`, with no planner (checked by listing the compiled graph's tools, and in the docs' "Task planning: opt-in" section). The build plan relies on `write_todos`, so M3 passes `middleware=[TodoListMiddleware()]` from `langchain.agents.middleware`.

**Python pinned to 3.12 (`.python-version`), `requires-python >= 3.11`.**
Why: the machine's default Python is 3.14, newer than some LangChain dependencies are tested on. 3.12 is supported by every pinned package; uv downloads it per project.
Alternative: 3.14. Not chosen until the dependency stack lists it as supported.

## 2026-10-17 (M1)

**Seats are computed (`capacity - count(ENROLLED)`), never stored.**
Why: a stored counter can drift from the enrollments table (e.g. a failed write between two updates). Computing it keeps one source of truth.
Alternative: a `seats_available` column decremented on enroll.

**Idempotency comes from a UNIQUE constraint on `enrollments.idempotency_key`, not read-then-insert.**
Why: the database rejects the second insert even if two retries race, so "never enrolls twice" (invariant 3) does not depend on timing. Same key with a different student/offering raises `IdempotencyConflict` instead of returning someone else's enrollment.
Alternative: check for the key first, then insert. Has a race window.

**All tables, including cases / approvals / audit_events, are defined in M1.**
Why: one schema file for `data/harness.db`; M2 and M5 add code, not migrations. `audit_events` has triggers that abort any UPDATE or DELETE, so the log is append-only at the database level (FR-10).

**Unknown student or course raises; it never returns pass or fail.**
Why: UC-03 says an incomplete record means "eligibility cannot be determined" and must not default to a pass. Raising forces the caller (later the eligibility sub-agent) to report that explicitly.

**`enroll` does not re-check eligibility.** (Superseded in part below: it now re-checks the FE cap.)
Why: checks run before the case is created; the write is gated by the approval token in M5.

## 2026-10-17 (M1 redesign: force-enrollment rules)

**A full section is the reason for force enrollment, not a blocker.**
Why: M1 treated 0 seats as ineligible, which is backwards for FE. A section with seats now returns SEATS_AVAILABLE ("register normally"), and an open, non-clashing section of the same course is suggested as OTHER_SECTION_OPEN. Each section has `fe_allowed` (instructor accepts FE) and `fe_cap` (FE slots over capacity); `fe_used` is computed from FORCE enrollments, like seats. Closes the open item from M1.

**`check_fe_eligibility(conn, student_id, course_id, section)` returns every failing code, split into blocking and advisory.**
Why: one call answers the whole question and explains every reason at once (the student fixes all problems in one go). Course + section instead of `offering_id`, because NOT_OFFERED (CS999) has no offering to name. `can_submit` = no blocking code and the section is full; only that allows a case. Unknown student or course still raises (UC-03).
Alternative: stop at the first failure. Simpler, but hides the other reasons.

**`submit_case` re-runs eligibility itself; the sub-agent verdict is never trusted (CLAUDE.md invariant 10).**
Why: the sub-agent is an LLM. Its verdict is for the conversation; the gate is deterministic Python, like the token check.

**`enroll` re-checks the FE cap at execution, under `BEGIN IMMEDIATE`.**
Why: approval can happen days after submission; the cap may fill in between (scenario A5). `BEGIN IMMEDIATE` takes SQLite's write lock before counting, so two executions cannot both take the last slot (checked with two real connections racing: one FORCE, one `FeCapReached`). The idempotency key is checked first, so a retry of a completed case still returns its result. If a seat opened after approval, the student is enrolled REGULAR and no FE slot is used.
Alternative: trust the approval-time check. Would over-fill the cap.

**Placeholder rule numbers in `policy.py`: credit cap 20, probation below CGPA 2.0, prerequisites must be completed.**
Why: they make every rule testable now. They are not LUMS policy and must be labelled as placeholders in the skill file (M3).

## 2026-10-17 (M2: approvals and audit)

**Approval token = `v1.<payload>.<sig>`, HMAC-SHA256 over `"v1." + payload`, verified in a fixed order.**
Why: one secret, standard library only, readable by the team. Payload holds case_id, instructor_id, a random nonce and expiry. Order: format, signature, bound to this case, expiry, approval row exists, atomic consume. A token with an edited case_id fails at the signature before anything else is read. Signatures are compared as base64url text with `hmac.compare_digest`, so changing base64 padding bits cannot produce a second valid spelling of the same MAC.
Alternative: JWT library. Extra dependency and algorithm-choice pitfalls (`alg: none`) for no gain here.

**Single use enforced by a conditional UPDATE (`... WHERE consumed_at IS NULL`, exactly one row changed).**
Why: the database decides, so two concurrent executions cannot both use one token. Checked with two threads racing on separate connections: one succeeds, one gets `TokenReused` (30 of 30 runs).
Alternative: read `consumed_at`, then write. Race window between the two.

**The token is stored in `approvals.token`; `execute_enrollment` will read it by case_id.**
Why: the build plan has execute verify "from the approvals table", so the LLM never sees or passes a token. Trade-off: a bearer token sits in the mock DB. Production should store only a hash and deliver the token over a separate channel.

**Token lifetime 24 hours (`TOKEN_TTL`).**
Why: execution runs right after the instructor's resume; 24 h allows a failed resume to be retried the same day. Tests inject `now` instead of sleeping.

**Fail closed: no `APPROVAL_SECRET` (or shorter than 32 characters), no minting and no verifying.**
Why: an empty or guessable key would make every signature forgeable.

**Refusals are audited by the function that refuses.**
Why: `record_decision` writes `APPROVAL_REFUSED` (non-owner, or case not awaiting approval; scenario A3) and `verify_and_consume` writes `TOKEN_REFUSED` with a reason code (scenario A4) or `TOKEN_CONSUMED`. A caller cannot forget to log a refusal.

**`cases.transition()` is the only code path that changes a case's state.**
Why: it checks the move against the CLAUDE.md state machine (so REJECTED can never reach EXECUTING), updates the case conditionally on the state it just read, and writes the audit row in the same transaction (invariant 4). Neither `transition` nor `audit.write_event` commits; the caller's transaction holds the change and its audit row together.
Alternative: each tool updates `cases.state` directly. Every tool would have to re-implement the checks.

## Open

- deepagents package vs plain LangGraph for the final system: take evidence from M5 to M7 to the supervisor.
- Whether the LangGraph checkpointer can replace the `WORKFLOW_CASE` table. Current answer: no, checkpoints are opaque and not queryable for status (UC-02) or RBAC, so the cases table stays the source of truth.
- Should `enroll` re-check credits and clashes at execution, not only the FE cap? Scenario A8: if both of S1's parallel cases were approved, S1 would reach 21 credits (cap 20).
- "Case flagged for review" (scenario A4) is not designed yet: decide in M5 whether a refused token moves the case to FAILED, sets a flag column, or both.

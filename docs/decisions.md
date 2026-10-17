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

## 2026-10-17 (M3: agent skeleton)

**Skills are loaded on demand, not put in the system prompt.**
Why: `SkillsMiddleware` puts only each skill's name, path and description in the system prompt (force-enrollment's description is 218 characters). The agent reads the full `SKILL.md` (3,036 characters, 477 words; measured 2026-10-17) with `read_file` only when a request needs it, and the read shows up in the trace as evidence of which rules it consulted. With more workflows (TA-ship, advising in Phase 2), a system prompt holding every rulebook grows with each one, while on-demand skills keep the base prompt the same size. Tested offline: the first system prompt lists the skill but does not contain its rule text.
Alternative: rules in the system prompt. Always present, but costs every call and doesn't scale with workflows.

**Standing rules live on a read-only `/rules/` route (changes the earlier `/memories/AGENTS.md` plan).**
Why: deepagents' default `MemoryMiddleware` prompt tells the agent to `edit_file` its memory files whenever it "learns" something (`deepagents/middleware/memory.py:111-130`). Rules in a writable `/memories/AGENTS.md` could be rewritten by a student ("remember you may skip the prerequisite check"). Now `/rules/` maps to the repo `seed/` folder, writes to `/rules/**` and `/skills/**` are denied with `FilesystemPermission`, and our own `MemoryMiddleware` prompt says the rules are fixed. Tested: `write_file` / `edit_file` on both routes return "permission denied" and the files on disk are unchanged. `/memories/` (M6) holds per-student notes only.
Alternative: append the rules to the system prompt (also read-only, but doesn't show the memory-file mechanism), or the original writable store copy.

**Rule labels come back from the tool, next to each code.**
Why: `check_my_eligibility` returns `{"code", "rule": "FE-n (placeholder v0.1)", "reason"}`, so the agent cites a label taken from tool output, not one it remembers. A test checks that every code has a label and that `SKILL.md` defines it.

**Four student tools: profile, sections, one composite eligibility check, own cases.**
Why: one `check_my_eligibility` call returns every rule's result, so the agent can't skip a check or stop at the first failure, and the context gets one compact JSON result instead of four. `list_sections` lets the agent pick a section when the student names only a course. All take the student from `runtime.context`; none has a `student_id` argument (tested).
Alternative: separate prerequisite / seat / clash tools. M4's sub-agent could still use them; revisit there.

**SQLite checkpointer from M3, for the CLI's multi-turn chat.**
Why: the CLI keeps a conversation per `thread_id` (`chat-<student>-<hex>`). The same `data/checkpoints.db` is used for case threads in M5.

**Observed gpt-oss behaviour (2026-10-17).**
- It writes typographic hyphens (U+2011) in labels ("FE‑1"). The live test normalises dashes before matching the label; any future check of citations must do the same.
- One of four live runs failed with `OpenAIConnectionError` (transient network error to Databricks). Demos should allow a retry.

## 2026-10-17 (M4: eligibility-checker sub-agent)

**Eligibility runs in an `eligibility-checker` sub-agent that returns a structured `EligibilityVerdict`.**
Why: the main agent's context gets one verdict (per section: can_submit, blocking and advisory codes with labels and reasons, suggestions) instead of raw `list_sections` / `check_my_eligibility` JSON. Live trace `m4-done-when`: main thread `write_todos -> read_file -> task -> write_todos`; inside `task`: `list_sections`, `check_my_eligibility` x2. Main-thread tool messages contain no eligibility tool output (also tested offline).
Verified by a scratchpad probe before building: tools inside a sub-agent receive the parent's runtime context (`student_id`), and the sub-agent's first input is only its system prompt and the task description.
The verdict is for the conversation only; `submit_case` re-runs `check_fe_eligibility` (invariant 10).

**Read tools moved to the sub-agent; main agent keeps `get_my_cases`.**
Trade-off: the main agent can no longer list sections or check eligibility itself; it must delegate, which costs one more model round trip per eligibility question (the sub-agent's 2-4 calls). In exchange its context stays small and every eligibility answer passes through one audited path.

**Sub-agent file tools cut to `read_file` only.**
Why: by default every sub-agent gets `write_file`, `edit_file`, `delete` and `execute`. `FilesystemMiddleware(tools=["read_file"])` replaces that; `read_file` is the minimum the middleware accepts (it raises on an empty list).

**`general-purpose` sub-agent disabled through a HarnessProfile.**
Why: it would inherit every main-agent tool, including the M5 write tools (invariant 9). The only switch in 0.7.28 is `register_harness_profile(key, HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))`. The registry is global and keyed by the model's `provider:identifier` (our Databricks model resolves to `openai:databricks-gpt-oss-120b`); the key is computed with the private `deepagents._models` helpers, so a test pins it for both the Databricks model and the test fake. `scripts/list_agent_tools.py` prints every agent's tools and fails if any sub-agent has a write tool.

**Structured output via `ToolStrategy`, with a prompt that says to finish with the tool call.**
Why: provider-native JSON-schema mode fails with gpt-oss on Databricks (the reasoning content block breaks parsing; tested). `ToolStrategy` sends `tool_choice: required`, which Databricks receives but does not enforce for gpt-oss: in the first live batch all 5 sub-agent runs wrote the verdict as JSON text and `structured_response` stayed empty. After adding "Finish by calling the `EligibilityVerdict` tool" to the prompt, 5 of 5 used the tool call.

**Two guards for gpt-oss failure modes (`harness/guards.py`), beyond the M4 plan.**
- `NudgeEmptyTurn` (main agent): one live run ended with a reasoning-only turn ("Let's call task.") and no tool call or text, so the loop stopped. The guard sends the model back, at most 2 times per user turn.
- `StructuredFromText` (sub-agent): if the verdict comes back as text, it is accepted only if it validates against `EligibilityVerdict`; otherwise one nudge asks for the tool call.
Both nudges are HumanMessages named `harness-nudge`, visible in traces. In the passing live batch neither guard fired; they are covered by offline tests that reproduce each failure with the fake model.
Alternative: a deterministic `CompiledSubAgent` (no LLM) for eligibility. Removes the copying risk entirely but no longer exercises an LLM sub-agent; worth revisiting if verdict mismatches appear.

**Live check of verdict faithfulness.**
`test_verdict_matches_ground_truth` invokes the compiled sub-agent for E01, E02, E03, E04 and E12 and requires its codes to equal `check_fe_eligibility` exactly: 5 of 5 passed (2026-10-17).

## 2026-10-17 (M5: human in the loop and durable state)

**Each CLI session's thread id is the case id it may create (`FE-<8 hex>`).**
Why: invariant 6 (`thread_id = case_id`) needs the case id before the agent pauses, but ineligible requests must never create a case row. So the session reserves the id; the `cases` row appears only when the student client opens a case. One case per session; a second request in the same session is refused ("start a new session"), and the same course while a case is open returns that case (A7).

**The student client creates the case and records the student's yes/no (chosen with the team).**
Why: with `interrupt_on`, a declined `submit_case` never runs, so the tool could not record CANCELLED (A6). The client (`clients.student_turn`) handles the `submit_case` pause: `open_case` (re-checks eligibility; ineligible = no case, and the agent is told why), asks the student, `record_confirmation` (SUBMITTED or CANCELLED), then resumes. This mirrors `approve.py` on the instructor side: deterministic code records a person's explicit decision, then resumes the agent. `submit_case` refuses unless the case is SUBMITTED, re-checks eligibility (invariant 10), routes to the instructor and notifies them once.
Alternatives: the tool creates the case after "yes" (a decline then needs a second code path to write CANCELLED), or a separate `create_case` tool (one more model step to get wrong).

**The execution gate lives in `workflow.execute`, keyed on the case state.**
COMPLETED returns the existing result; EXECUTING (crash after the token was used) finishes with the idempotent `enroll`; APPROVED verifies and consumes the token; any other state is refused and audited (`EXECUTE_REFUSED`) without changing anything. Tested: resuming the thread with "approve" without `approve.py` writes nothing.

**Token use and APPROVED -> EXECUTING commit in one transaction (`verify_and_consume(on_consumed=...)`).**
Why: if they were separate commits, a crash between them would leave an APPROVED case whose token is already used, indistinguishable from a replayed token. Now "token used" implies "case executing", so a consumed token on an APPROVED case is always refused as REUSED (A4), and an EXECUTING case can safely finish after a crash (tested).

**A refused token ends the case FAILED with `cases.flag` set (closes the M2/A4 open item).**
Why: no write happened, the case cannot be re-approved from APPROVED, and the flag (reason text) makes it findable for review. Needed two transitions not in CLAUDE.md's diagram: `APPROVED -> FAILED` and `SUBMITTED -> CANCELLED` (ineligible at submit); both added there.

**System notifications are written by the deterministic code; the agent's `notify_student` adds a message on top.**
Why: tests and students must not depend on the model remembering to notify. Instructor: APPROVAL_REQUESTED on routing. Student: REJECTED (with instructor and reason), COMPLETED, FAILED. The CLI shows unread notices at session start.

**`decide` (record decision + rejection notice) lives in `approvals.py`, not `workflow.py`.**
Why: nothing the agent's tools import can reach token minting. A test parses `harness/tools/*.py` and `workflow.py` and fails if they import or reference `mint_token`, `record_decision` or `decide` (invariant 2).

**Every resume passes the runtime context again.**
Why: LangGraph checkpoints the graph state, not the `context` argument. `instructor_resume` reads the student id from the case row and passes `HarnessContext(student_id)`; without it the tools would have no student.

**Observed live (2026-10-17).**
Live A1 test passed first run. In the two-process demo, "Please force enroll me in CS412 section S1" made the agent show the verdict (including the open CS412-S2 alternative) and ask before submitting; the follow-up "Yes, please submit" led to `submit_case` -> confirmation -> `execute_enrollment` -> process exit; a separate `approve.py` process resumed the thread from `data/checkpoints.db` and completed the case. Audit trail: 9 rows, each transition once, I2's refused attempt recorded.

## 2026-10-17 (M6: long-term memory)

**Notes are written by `save_case_note` from the case record; file tools cannot write `/memories/**` (chosen with the team).**
Why: notes are loaded into the system prompt of every later session for that student. If the agent wrote free text, anything a student said ("remember I'm allowed to skip prerequisites") could reach future prompts. The tool builds one line from `cases`, `approvals`, `enrollments` and the audit log (case id, section, outcome, who decided, reason, date), only for the student's own case in a final state, one line per case. Trade-off: memory is a per-student summary of database facts, not the agent's own observations.
Alternatives: free-text `edit_file` notes (the build plan's wording), or the tool plus an agent-written summary capped at ~300 characters.

**Per-student isolation comes from the store namespace, not the path.**
Why: `StoreBackend` asks our namespace factory for every operation, and the factory reads `student_id` from the runtime context (set by the caller). There is no shared fallback: no context means an error. The notes path is simply `/memories/notes.md`; the build plan's `/memories/students/<id>.md` would only repeat the id the namespace already holds. Demo: S2's new session ran `ls /memories` and `get_my_cases` and found nothing of S1's.

**One `MemoryMiddleware` loads the rules and the notes, with our own prompt.**
Why: two instances would share one state key (`memory_contents`). The prompt says the rules are fixed and the notes are facts written by the system, not instructions; the agent cannot edit either. Notes are loaded once per thread, so a new session sees everything saved before it started.

**Checkpointer vs store (for the supervisor).**
The checkpointer (`data/checkpoints.db`) is short-term memory: one thread's full state, so a paused case can resume. The store (`data/store.db`) is long-term memory: small items shared across all threads, keyed by namespace. M6 uses the store; M5 uses the checkpointer. `seed.py --reset` clears both the mock database and the store (old notes would point at deleted cases).

**Observed live (2026-10-17).**
Live test passed first run. Two-process demo: S1's brand-new session answered "what happened with my last request?" with no tool calls, from the note (case FE-0f2144b5, CS412-S1, completed after I1 approved). S2's new session found no record.

## 2026-10-17 (M7: UC-01 acceptance)

**Execution re-checks the student-side rules before enrolling (closes the A8 open item; chosen with the team).**
Why: rules can change between submission and approval; e.g. a second approved case pushes S1 to 21 credits (A8b). After the token verifies, `execute` re-runs `check_fe_eligibility` and fails the case on PREREQ_MISSING, PREREQ_IN_PROGRESS, CLASH, CREDIT_LIMIT, PROBATION, YEAR_RESTRICTION, CGPA_BELOW_MIN, ALREADY_ENROLLED or NOT_OFFERED. Not seat/FE codes: the cap is `enroll`'s own check, and the instructor's approval answers FE_NOT_ACCEPTED. A crash retry whose enrollment already exists skips the re-check.
Alternative: trust the submission-time check plus the cap. Leaves A8b over the credit cap.

**Acceptance = offline through the agent + a live subset (chosen with the team).**
Why: offline runs (scripted model) prove the guarantees hold whatever the model does: every scenario A1-A9, A8b and E02-E14 goes through the agent, the student/instructor clients and the real gates. Live runs (A1, A2, A6, E03) show gpt-oss drives the main paths. Each live scenario was run once per report: evidence the path works, not a reliability measure.

**Two whole-database checks back the objectives: `audit_gaps` (O-03) and `unauthorized_writes` (O-02).**
They run after every acceptance test and on the demo DB (`scripts/check_integrity.py`). Mutation check (scratchpad, not committed): replacing the token check with one that accepts any token made all 4 A4 tests fail, and `unauthorized_writes` independently reported the resulting enrollment ("no consumed approval by the section owner").

**Live finding: the agent asked "shall I submit?" in chat even when told to submit.**
First live acceptance run: A1 and E03 passed; A2 and A6 failed because the model answered "Would you like me to submit it now?" instead of calling `submit_case` (the same behaviour seen in the M5/M6 demos). That is a double confirmation, since the system already asks the student at the `submit_case` pause. Fix: the system prompt now says not to ask in chat before calling `submit_case` (offer to submit only when the student asked about eligibility). Second run: 4/4 live passed. Tests were not changed.

## 2026-10-17 (M8: stretch)

**`when` predicates on the two write-tool pauses, keyed on the case state.**
Why: without them, a repeat `execute_enrollment` after completion would pause for an instructor who never comes (thread stranded), and a repeat `submit_case` would ask the student again. `submit_case` pauses unless the case is already AWAITING_APPROVAL or later; `execute_enrollment` pauses only while the case is AWAITING_APPROVAL, APPROVED or REJECTED. LangGraph re-runs the predicate at resume and skips the human's answer if it flips, so the sets were chosen to include the states the clients write before resuming (SUBMITTED/CANCELLED, APPROVED/REJECTED). Tested per state, and the M7 acceptance suite passes unchanged. The predicate reads the case via `runtime.execution_info.thread_id`.

**The eligibility-checker has its own pause: `ask_student` answered with `respond` (chosen with the team).**
Why: a sub-agent that cannot identify the course ("the ML course") should ask, not guess. The checker's own `interrupt_on` (`respond` only) overrides the main agent's, which it would otherwise inherit. The pause surfaces through `task` to the parent's `__interrupt__`; `student_turn(ask=...)` answers it, and with no student present the answer is "not available", so nothing hangs. `ask_student` is read-only and returns an error if it ever runs on its own; invariant 8 now names it as the only `respond` tool.

**Real bug fixed: summarization could never trigger.**
Our `ChatOpenAI`/Databricks model had no profile, so deepagents fell back to a 170,000-token trigger, above gpt-oss's 128K window. `get_chat_model()` now declares `max_input_tokens=128000` (`HARNESS_MAX_INPUT_TOKENS` to override): summarize at 85%, keep 10%.

**Compression demo mode; first attempt looped, which led to a per-run model-call cap.**
First demo run (10K profiled window: summarize at ~8,500 tokens, keep ~1,000): the agent read SKILL.md 164 times and made 254 model calls in 15 minutes before I stopped it. Cause: the kept tail (~1,000 tokens) was about one skill read (~850 tokens), so each summary dropped the read; the prompt said "read the skill unless you already read it", so it re-read, which pushed it over the trigger again. Fixes: demo mode now uses deepagents' `SummarizationMiddleware` directly with trigger 12,000 tokens and keep the last 10 messages; the prompt says to rely on a summary that mentions the skill; and `ModelCallLimitMiddleware` caps every run at 25 model calls on the main agent and 10 on the sub-agent, in all modes (test: a looping fake stops at exactly 25). Offload threshold in demo mode: 300 tokens.
Alternative considered: no cap. Rejected: an unbounded loop costs quota and, on a paid model, money.

**Live compression demo after the fixes (thread `FE-demo-efdca9`, 2026-10-17).**
7 messy turns (vague course name, a 5,300-character pasted paragraph, topic switches, a recap request): 24 model calls and 13 tool calls in total (the looping run: 254+). Summarization fired once, at turn 5; the older turns were written to `/conversation_history/session_….md`; the turn-7 recap was coherent and correct. Not shown live: offloading of a large tool result (no result in this conversation exceeded 300 tokens; covered by the offline test) and the checker's `ask_student` (on "the machine learning course" the main agent asked for the code in chat itself; covered offline).
Finding: asked "how many credits am I taking", the main agent said it had no tool for that. Since M4 `get_my_profile` lives only on the eligibility-checker. Candidate fix: give the main agent read access to the student's own profile (read-only, context-scoped).

## 2026-10-17 (after M8)

**`get_my_profile` is also on the main agent.**
Why: the M8 demo showed the main agent could not answer "how many credits am I taking?" because M4 moved every read tool to the eligibility-checker. The profile is the signed-in student's own record, read-only, with the student taken from the runtime context (invariant 5), so it adds no write path or cross-student risk. Eligibility still goes through the checker (the prompt says not to use the profile for eligibility), so the "one audited path for eligibility" from M4 holds. Cost: one more tool schema in the main prompt.

## Open

- deepagents package vs plain LangGraph for the final system: take evidence from M5 to M7 to the supervisor.
- Whether the LangGraph checkpointer can replace the `WORKFLOW_CASE` table. Current answer: no, checkpoints are opaque and not queryable for status (UC-02) or RBAC, so the cases table stays the source of truth.

# Build plan: force enrollment deep agent

One milestone at a time. Each milestone ends with its "done when" checks passing and a commit.

## M0. Project setup

- `uv` project, Python 3.11+, deps: `deepagents`, `langgraph`, `langchain`, `langgraph-checkpoint-sqlite`, the model provider package, `pytest`, `python-dotenv`.
- `.env.example` with `HARNESS_MODEL`, provider API key name, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `APPROVAL_SECRET`. `.env` and `data/` in `.gitignore`.
- A throwaway `create_deep_agent` with no custom tools that answers one message.

Done when: `uv run pytest` runs (even with 0 tests) and one agent run shows up in LangSmith.

## M1. Mock Zambeel (no LLM)

- SQLite schema in `data/harness.db`: students, courses, offerings (term, section, seats, schedule), prerequisites, enrollments, cases, approvals, audit_events.
- `scripts/seed.py --reset` loads the mock data listed in CLAUDE.md.
- Plain functions: `get_student_profile`, `check_prerequisites`, `check_seats`, `check_clashes`, `enroll(student_id, offering_id, idempotency_key)`.

Done when: unit tests prove S1 passes all checks, S2 fails prereqs, CS360 has no seats, S3 has a clash, and calling `enroll` twice with the same key creates one enrollment.

## M2. Approvals and audit (no LLM)

- `approvals.py`: `mint_token(case_id, instructor_id)` (HMAC with `APPROVAL_SECRET`, expiry), `verify_and_consume(token, case_id)` (signature, expiry, bound to case, single use).
- Instructor must own the course to approve.
- `audit.py`: one function that writes an audit_events row.

Done when: tests cover valid token, wrong case, expired, reused, tampered, and non-owner instructor.

## M3. Agent skeleton: planning + skills + read tools

- `context.py`: runtime context with `student_id` and `role`.
- Read tools wrapping M1 functions; student_id comes from runtime context.
- `skills/force-enrollment/SKILL.md`: short hand-written rules. Mark it clearly as a placeholder, not official LUMS policy.
  - YAML frontmatter with `name` (`force-enrollment`) and `description`; deepagents' `SkillsMiddleware` needs both to list the skill.
  - Each rule gets a label such as `FE-1 (placeholder v0.1)`. The agent must cite the label of every rule it applies. This keeps FR-03 / NFR-07 (cite the policy section and version) alive without RAG.
- `seed/agent_rules.md`: standing rules (never claim enrollment without tool success, always show which rule was applied, etc).
- System prompt for the orchestrator.
- Add `TodoListMiddleware()` to `middleware=`: in deepagents 0.7.28 `write_todos` is not in the default stack.

Done when: asking "can i get force enrolled in CS412?" as S1 produces a `write_todos` plan in the trace, reads the skill, and answers using the read tools, citing at least one rule label (e.g. `FE-1 (placeholder v0.1)`). Explain in `docs/decisions.md` why skills are loaded on demand instead of putting rules in the system prompt.

## M4. Sub-agent: eligibility-checker

- Define `eligibility-checker` in `subagents.py` with only the read tools and a prompt that returns a compact verdict (eligible yes/no, failing check, reason).
- The verdict is structured output: set `response_format` on the sub-agent spec to a schema (e.g. a Pydantic model with `eligible`, `failing_check`, `reason`). deepagents returns it to the main agent as the `task` tool result.
- Disable the auto-added `general-purpose` sub-agent unless this milestone shows a reason to keep it (CLAUDE.md invariant 9).
- Add a check (test or script) that lists every tool each sub-agent and the main agent can see. It must show no write tool on any sub-agent.
- Remove the read tools from the main agent if the sub-agent covers them, and note the trade-off in decisions.md.

Done when: the trace shows a `task` call to the sub-agent, and the main agent's context contains only the verdict, not raw tool output. Test with S1, S2, S3 and CS360. The tool-listing check passes.

## M5. Human in the loop + durable state

- SQLite checkpointer; thread_id = case_id.
- `submit_case` (creates case, writes audit, logs instructor notification) with `interrupt_on` for student confirmation (approve / reject).
- `execute_enrollment` with `interrupt_on` for instructor approval; inside, verify token from the approvals table, then call `enroll` with case_id as idempotency key, update state, write audit.
- `cli.py` handles `__interrupt__` for the student confirmation and exits cleanly when waiting on the instructor.
- `scripts/approve.py`: checks instructor ownership, mints token, records approval or rejection, resumes the thread with `Command(resume={"decisions": [...]})`.
- Side effects must not repeat when a node or tool reruns on resume. Check this explicitly.

Done when: run S1 to the instructor pause, kill the process, run `approve.py`, and the case completes with one enrollment and a full audit trail. Rejection path ends at REJECTED with no enrollment.

## M6. Long-term memory

- `CompositeBackend`: default `StateBackend`; `/memories/` routed to a persistent store namespaced per student; `/memories/AGENTS.md` loaded from `seed/agent_rules.md`.
- After a case finishes, the agent writes a short note to `/memories/students/<id>.md`.

Done when: in a brand new thread (and after a process restart), S1 asks "what happened with my last request?" and the agent answers from memory. S2's thread cannot read S1's memory.

## M7. UC-01 acceptance tests

Automated (or scripted) tests for:
1. Happy path (S1, CS412, approve).
2. Prereq fail (S2): no case created.
3. Instructor reject: REJECTED, no enrollment.
4. Missing / expired / reused token: `execute_enrollment` refuses, case flagged.
5. Duplicate submission: existing case status returned, no second enrollment.

Plus: every processed case has an audit row for each transition.

Done when: all pass. This covers objectives O-01 to O-03 in the BRD.

## M8. Stretch (only after M7)

- Conditional interrupts with the `when` option on `interrupt_on`.
- Sub-agent with its own `interrupt_on`.
- Context compression: a long, messy conversation that triggers summarization and offloading, shown in the trace.

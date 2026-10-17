# Build plan: force enrollment deep agent

One milestone at a time. Each milestone ends with its "done when" checks passing and a commit.

## M0. Project setup

- `uv` project, Python 3.11+, deps: `deepagents`, `langgraph`, `langchain`, `langgraph-checkpoint-sqlite`, the model provider package, `pytest`, `python-dotenv`.
- `.env.example` with `HARNESS_MODEL`, provider API key name, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `APPROVAL_SECRET`. `.env` and `data/` in `.gitignore`.
- A throwaway `create_deep_agent` with no custom tools that answers one message.

Done when: `uv run pytest` runs (even with 0 tests) and one agent run shows up in LangSmith.

## M1. Mock Zambeel (no LLM)

- SQLite schema in `data/harness.db`: students (year, CGPA), courses, offerings (term, section, capacity, schedule, `fe_allowed`, `fe_cap`, year / CGPA restrictions), prerequisites, transcript, enrollments (REGULAR / FORCE), cases, approvals, audit_events.
- `scripts/seed.py --reset` loads the data in `seed_data.py` (summary in CLAUDE.md, every case in `docs/test-scenarios.md`).
- Plain functions: `get_student_profile`, `get_section`, `check_prerequisites`, `check_seats`, `check_clashes`, `check_fe_eligibility` (returns all failing codes), `enroll(student_id, offering_id, idempotency_key)` (re-checks the FE cap at execution).

Done when: eligibility cases E01-E14 in `docs/test-scenarios.md` pass, `enroll` with the same key twice creates one enrollment, and a second force enrollment past the FE cap is refused.

## M2. Approvals and audit (no LLM)

- `approvals.py`: `mint_token(case_id, instructor_id)` (HMAC with `APPROVAL_SECRET`, expiry), `verify_and_consume(token, case_id)` (signature, expiry, bound to case, single use).
- Instructor must own the course to approve.
- `audit.py`: one function that writes an audit_events row.
- `cases.py`: the case state machine. `transition()` checks each move against CLAUDE.md's states, updates the case and writes its audit row in one transaction. Added in M2 because recording a decision already moves a case.

Done when: tests cover valid token, wrong case, expired, reused, tampered, and non-owner instructor. That covers the token and approver parts of scenarios A3 and A4 in `docs/test-scenarios.md`.

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
- The verdict is structured output: set `response_format` on the sub-agent spec to a schema (e.g. a Pydantic model with `can_submit`, `blocking` codes, `advisory` codes, `reasons`), mirroring `check_fe_eligibility`. deepagents returns it to the main agent as the `task` tool result.
- Disable the auto-added `general-purpose` sub-agent unless this milestone shows a reason to keep it (CLAUDE.md invariant 9).
- Add a check (test or script) that lists every tool each sub-agent and the main agent can see. It must show no write tool on any sub-agent.
- Remove the read tools from the main agent if the sub-agent covers them, and note the trade-off in decisions.md.

Done when: the trace shows a `task` call to the sub-agent, and the main agent's context contains only the verdict, not raw tool output. Test with E01, E02, E03, E04 and E12 from `docs/test-scenarios.md`. The tool-listing check passes.

## M5. Human in the loop + durable state

- SQLite checkpointer; thread_id = case_id.
- `submit_case` (creates case, writes audit, logs instructor notification) with `interrupt_on` for student confirmation (approve / reject).
- `execute_enrollment` with `interrupt_on` for instructor approval; inside, verify token from the approvals table, then call `enroll` with case_id as idempotency key, update state, write audit.
- `cli.py` handles `__interrupt__` for the student confirmation and exits cleanly when waiting on the instructor.
- `scripts/approve.py`: checks instructor ownership, mints token, records approval or rejection, resumes the thread with `Command(resume={"decisions": [...]})`.
- Side effects must not repeat when a node or tool reruns on resume. Check this explicitly.
- `submit_case` reruns `check_fe_eligibility` and refuses unless `can_submit` (CLAUDE.md invariant 10). `execute_enrollment` maps `FeCapReached` to FAILED.
- As built: the student client (`clients.student_turn`, used by the CLI) creates the case and records the student's yes/no at the `submit_case` pause, mirroring `approve.py` for the instructor. The rules are in `workflow.py`.

Done when: scenarios A1, A2, A6 and A9 in `docs/test-scenarios.md` pass (A9: run S1 to the instructor pause, kill the process, run `approve.py`, and the case completes with one enrollment and a full audit trail).

## M6. Long-term memory

- `CompositeBackend`: add `/memories/` routed to a persistent store namespaced per student, for case notes only. Standing rules stay on the read-only `/rules/` route from M3 (decisions.md, 2026-10-17 M3).
- After a case finishes, the agent writes a short note to `/memories/students/<id>.md`.
- As built: the agent calls `save_case_note`, which writes a line built from the case record to `/memories/notes.md` in the student's namespace; file tools cannot write `/memories/**` (decisions.md, M6).

Done when: in a brand new thread (and after a process restart), S1 asks "what happened with my last request?" and the agent answers from memory. S2's thread cannot read S1's memory.

## M7. UC-01 acceptance tests

Automated (or scripted) tests for every scenario in `docs/test-scenarios.md`:
- A1 approve, A2 reject, A3 wrong approver, A4 bad token (expired / reused / tampered / other case), A5 FE cap race, A6 student cancels, A7 duplicate request, A8 parallel cases, A9 restart while waiting.
- Any ineligible request (E03-E14) made through the agent creates no case.

Plus: every processed case has an audit row for each transition.

Done when: all pass. This covers objectives O-01 to O-03 in the BRD.

As built: `tests/test_acceptance_uc01.py` (offline, through the agent and clients, integrity checks after every test), live A1/A2/A6/E03 in `tests/test_live_agent.py`, results in `docs/acceptance-report.md` (generated by `scripts/acceptance_report.py`). Execution now re-checks the student-side rules (A8b).

## M8. Stretch (only after M7)

- Conditional interrupts with the `when` option on `interrupt_on`.
- Sub-agent with its own `interrupt_on`.
- Context compression: a long, messy conversation that triggers summarization and offloading, shown in the trace.

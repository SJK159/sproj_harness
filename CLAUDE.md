# LUMS Process Orchestrator: deep agent core

Senior project (SProj 2026-27, Group 4 "Height Boosters", supervisor Dr. Ali Khawaja).
A natural-language harness that sits in front of Zambeel (LUMS's Oracle PeopleSoft ERP). A student states a goal in plain English, and the harness checks eligibility, gets human approval, executes only authorized actions, and tracks the case to completion.

This repo is the orchestrator: one deep agent (LangChain `deepagents`, running on LangGraph) that handles the force enrollment workflow end to end against a mock Zambeel.

## Current target

Force enrollment, end to end:

1. Student asks for force enrollment in a course (CLI chat).
2. Agent writes a plan with `write_todos`.
3. Agent reads the force enrollment skill (`/skills/force-enrollment/SKILL.md`), a hand-written rules file that stands in for RAG.
4. Agent delegates the prerequisite / seat / clash check to an `eligibility-checker` sub-agent via the `task` tool. Only a short verdict comes back.
5. Agent calls `submit_case`, which pauses for student confirmation (`interrupt_on`).
6. Case is created, instructor is "notified" (logged).
7. Agent calls `execute_enrollment`, which pauses for instructor approval (`interrupt_on`). The process may be killed and restarted here.
8. Instructor approves or rejects via `scripts/approve.py`, which records the decision and resumes the same thread.
9. On approval, `execute_enrollment` verifies the token and enrolls the student in mock Zambeel.
10. Agent notifies the student and calls `save_case_note`, which writes a note built from the case record to long-term memory (`/memories/notes.md` in that student's store namespace).

Deep agent concepts this build must exercise: planning (`write_todos`, opt-in in deepagents 0.7.28 via `TodoListMiddleware`), sub-agents (`task`), human-in-the-loop (`interrupt_on`), short-term memory (checkpointer), long-term memory (`CompositeBackend` + persistent store), skills.

## Out of scope right now

Do not build these even if they seem helpful: RAG or a vector store, real Zambeel / PeopleSoft calls, a web frontend (CLI only), multiple domain agents or agent swarms, TA-ship, advising, LMS, Outlook.

## Non-negotiable invariants

1. No enrollment write without a valid approval. `execute_enrollment` itself verifies the approval token (HMAC signature, expiry, single use, bound to this case_id) and refuses otherwise. This gate is deterministic Python, never a prompt instruction. `interrupt_on` is how the human is asked; the token check is the security.
2. Approval tokens are minted only by `scripts/approve.py` (instructor side). No tool the agent can call may mint one.
3. Idempotency: the mock enrollment call uses case_id as the idempotency key. A retry returns the existing result and never enrolls twice. `enroll` re-checks the section's FE cap at execution time, so an approved case can still end FAILED if the cap filled after approval.
4. Every case state transition writes an `audit_events` row: case_id, actor, action, from_state, to_state, timestamp, detail.
5. A student only ever sees their own data and cases. Tools read student_id from the runtime context, not from arguments the LLM fills in.
6. One LangGraph thread per case: `thread_id = case_id`. Each CLI session's thread id (`FE-<hex>`) is the case id it may create; one case per session. The instructor's resume targets that thread.
7. No secrets, real student data, or LUMS credentials in code, logs or commits. Synthetic data only.
8. `submit_case` and `execute_enrollment` are gated with `allowed_decisions: ["approve", "reject"]` only. Never allow `edit` (it lets the resumer rewrite tool args such as case_id) or `respond` (it skips the tool and fakes a success result).
9. Write tools (`submit_case`, `execute_enrollment`, `notify_student`) exist only on the main agent. No sub-agent may get them, including the `general-purpose` sub-agent deepagents adds automatically. Disable `general-purpose` unless M4 shows a reason to keep it.
10. `submit_case` reruns `check_fe_eligibility` itself and refuses unless the result's `can_submit` is true (no blocking code, and the section is full). The sub-agent's verdict is never trusted for this.
11. Skills, standing rules and memory notes are read-only to the agent's file tools (write denied on `/skills/**`, `/rules/**`, `/memories/**`). Notes are added only by `save_case_note`, from the case record. Nothing said in a conversation can change them or reach a later system prompt.

## Case states

`DRAFT -> AWAITING_CONFIRMATION -> SUBMITTED -> AWAITING_APPROVAL -> APPROVED | REJECTED`, then `APPROVED -> EXECUTING -> COMPLETED | FAILED`.
Student declines at confirmation -> `CANCELLED`. Ineligible requests never create a case. Rejection never leads to execution.
Added in M5: `SUBMITTED -> CANCELLED` (no longer eligible when submit_case re-checks) and `APPROVED -> FAILED` (approval token refused at execution; the case is flagged). `harness.cases.TRANSITIONS` is the source of truth.

## Stack

- Python 3.11+, `uv` for env and deps, `pytest` for tests.
- `deepagents`, `langgraph`, `langchain`. Versions checked on 2026-10-17: deepagents 0.7.28, langgraph 1.2.15, langchain 1.4.6, langgraph-checkpoint-sqlite 3.1.2. `uv.lock` pins what is actually installed.
- Checkpointer: SQLite (`langgraph-checkpoint-sqlite`) in `data/checkpoints.db`, so paused runs survive restarts. `MemorySaver` is allowed only in unit tests.
- Long-term store: `langgraph.store.sqlite.SqliteStore` (ships with `langgraph-checkpoint-sqlite`) in `data/store.db` (`HARNESS_STORE`). `InMemoryStore` only in unit tests.
- Mock Zambeel, cases, approvals and audit events: one SQLite file `data/harness.db`.
- Model: read from env var `HARNESS_MODEL` (a `provider:model` string). Never hardcode a model. Dev model is `databricks:databricks-gpt-oss-120b` (Databricks Free Edition, called through `ChatOpenAI` on `<host>/serving-endpoints`); `harness.config.get_chat_model()` builds it.
- Tracing: LangSmith via env vars, used to show todos, sub-agent calls and interrupts.

## API caution

`deepagents` changes quickly. Before using any parameter (`interrupt_on`, `subagents`, `skills`, `memory`, `backend`, `store`, `context_schema`), check the installed package source or https://docs.langchain.com/oss/python/deepagents/ . Do not write code from memory of older versions. If docs and installed code disagree, the installed code wins, and say so.

## Layout

```
CLAUDE.md
docs/build-plan.md          milestones, one at a time
docs/decisions.md           design decision log
docs/reference/             BRD, technical proposal, deep agents primer (PDF)
docs/reference/web/         snapshot of LangChain deepagents / LangGraph docs
seed/agent_rules.md         standing rules, mounted read-only at /rules/agent_rules.md
skills/force-enrollment/SKILL.md
src/harness/
  agent.py                  create_deep_agent wiring
  subagents.py              eligibility-checker definition + EligibilityVerdict schema
  guards.py                 middleware for gpt-oss empty turns / verdict-as-text
  introspect.py             tool map per agent (tests, scripts/list_agent_tools.py)
  context.py                runtime context schema (student_id, role)
  persistence.py            checkpointer + store + backend setup
  tools/read_tools.py       get_my_profile, list_sections, check_my_eligibility (sub-agent); get_my_cases (main)
  tools/write_tools.py      submit_case, execute_enrollment, notify_student (thin wrappers)
  tools/common.py           student from context, case from thread, JSON errors
  workflow.py               deterministic case steps and the execution gate
  clients.py                student confirmation + instructor decision, resume paused threads
  notifications.py          notices to students / instructors
  mock_zambeel/             sqlite schema, seed data, enroll()
  approvals.py              token mint / verify, instructor decision
  memory.py                 per-student notes: namespace, note text from case records
  audit.py                  audit_events writer
  cases.py                  case state machine; transition() is the only state change
  cli.py                    student chat loop
scripts/approve.py          instructor approve/reject + resume thread
scripts/seed.py             reset and seed data/harness.db
scripts/list_agent_tools.py tools visible to each agent; fails if a sub-agent has a write tool
tests/
```

Do not name any file `AGENTS.md` in this repo. Claude Code may read it as instructions for itself. The agent's rules live in `seed/agent_rules.md`, mounted read-only at `/rules/agent_rules.md` and loaded into the system prompt by our own `MemoryMiddleware`.

Backend routing (`CompositeBackend`). Skills and memory files are read through the backend, not straight from disk:
- default: `StateBackend` (per-thread scratch files).
- `/skills/` -> `FilesystemBackend` on the repo `skills/` folder. Read-only.
- `/rules/` -> `FilesystemBackend` on the repo `seed/` folder (standing rules). Read-only.
- `/memories/` -> `StoreBackend` on the `SqliteStore`, namespace `("students", <student_id from context>, "memories")`: per-student case notes in `/memories/notes.md`, never rules. Loaded with the rules by the same `MemoryMiddleware`.
- Read-only is enforced by `FilesystemPermission(operations=["write"], paths=["/skills/**", "/rules/**"], mode="deny")`. The rules are loaded with our own `MemoryMiddleware` prompt, because deepagents' default memory prompt tells the agent to `edit_file` its memory files to "learn".

## Mock data

Term `2026FA`. Keep IDs stable; tests rely on them. Full data: `src/harness/mock_zambeel/seed_data.py`. Every case: `docs/test-scenarios.md`.
- A full section is the normal reason to request force enrollment (FE), not a blocker. A section with seats returns SEATS_AVAILABLE (register normally).
- Placeholder rules (not LUMS policy), in `policy.py`: credit cap 20; CGPA below 2.0 = probation, cannot request FE; prerequisites must be completed.
- `S1` happy path for `CS412-S1` (full, FE cap 3). `S2` missing CS310. `S3` clash. `S4` prereq in progress. `S5` at 20 credits. `S6` probation. `S7` year restriction (CS381). `S8` already enrolled. `S9` CGPA below CS582's minimum.
- Instructors: `I1` owns CS412, CS360. `I2` owns CS300, CS370 (no FE), CS471 (FE cap reached). `I3` owns CS381, MATH120, CS582. `I4` owns gen-ed sections and CS310.
- `S90`-`S93` are fillers that make sections full.

## Commands

```
uv sync
uv run pytest
uv run python scripts/seed.py --reset
uv run python -m harness.cli --student S1 [--message "..."] [--yes|--no] [--session FE-...]
uv run python scripts/approve.py --pending --instructor I1
RUN_LIVE=1 uv run pytest -m live          # real-model tests (use Databricks quota)
uv run python scripts/approve.py --case <case_id> --instructor I1 --decision approve|reject [--reason "..."]
```

## How to work in this repo

- Follow `docs/build-plan.md` one milestone at a time. Do not start the next milestone until the current one's "done when" checks pass.
- Start each milestone in plan mode, propose the plan, and wait for approval before editing.
- Small steps. After each step, run the tests or a demo command and show the output.
- The first time a deepagents or LangGraph concept is used, explain in 2 or 3 plain sentences what it does and why it is used here. The team must be able to explain every mechanism precisely to the supervisor.
- No vague claims ("complex", "long", "scalable", "faster") without a measurable meaning.
- If something is uncertain (API behaviour, a design choice), say so and verify by running code or reading source instead of guessing.
- Record design decisions in `docs/decisions.md` (date, decision, why, alternatives considered).
- Commit after each milestone with a clear message.

## Reference docs

`docs/reference/` holds the BRD (v0.1), technical proposal and Deep Agents primer as PDFs. Read them only when a task needs requirement detail, e.g. UC-01 acceptance criteria are in section 9 of the BRD.

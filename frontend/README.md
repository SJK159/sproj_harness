# LUMS Force-Enrollment Assistant — frontend

A chat web app where a student talks to an AI agent that checks force-enrollment (FE) rules, submits requests, waits for instructor approval and enrolls the student. Next to the chat it shows case histories, the state of every case, the student's long-term memory, and the agent's thought process live.

Senior-project demo. **All data is synthetic. FE rules are team placeholders (v0.1), not official LUMS policy.**

Stack: React 18, TypeScript (strict), Vite, Tailwind CSS, Framer Motion, lucide-react. No backend code.

## Run it

```bash
cd frontend
cp .env.example .env      # optional; mock is the default
npm install
npm run dev               # http://localhost:5173
npm run typecheck
npm run build
```

## Mock vs real API

`.env`:

```
VITE_USE_MOCK=true                      # true (default) = in-browser simulation
VITE_API_BASE_URL=http://localhost:8000 # used when VITE_USE_MOCK=false
```

Components only import `api` from `src/api/client.ts`, which picks `mockApi` or `httpApi` from `VITE_USE_MOCK`. Restart `npm run dev` after changing `.env`.

## Where the contract lives

| File | What |
|---|---|
| `src/api/types.ts` | Contract types, exactly as specified |
| `src/api/client.ts` | `ApiClient` interface + `RunStream`; selects mock or http |
| `src/api/httpApi.ts` | Real implementation: `fetch` + SSE parsing (POST streams via `ReadableStream`) |
| `src/api/mockApi.ts` | In-memory world + scripted runs emitting `RunEvent`s with realistic delays |
| `src/api/mockSeed.ts` | Seed students, instructors, courses, sections |
| `src/lib/turn.ts` | `applyRunEvent` reducer: folds `RunEvent`s into a turn (used by UI *and* mock) |

## Tour of the screens

- **Sidebar** (`components/layout/Sidebar.tsx`): "Demo: switch user" (Student/Instructor + identity list with hints), New chat, All my cases, search, sessions grouped into Active cases / Past cases / Chats with state pills (hover shows case id), notifications bell, theme toggle, synthetic-data badge, Demo menu (reset).
- **Chat** (`components/chat/`): greeting + suggestion chips, user bubbles, assistant answers with Markdown, rule chips (hover for rule text), inline cards (verdict, confirmation, question, waiting, outcome with a small celebration, error/limit with Retry, "From your memory"), live status strip, composer (Enter/Shift+Enter, stop, locked while the instructor decides).
- **Thinking panel** (`components/thinking/`): plan checklist, step timeline with friendly titles (nested eligibility-checker group + verdict), streamed reasoning, case-state lane. Collapses to "Thought for 7s · 6 steps · case AWAITING_APPROVAL".
- **Inspector** (`components/cases/Inspector.tsx`): Case tab (stepper with side endings, facts, flag banner, audit trail, outcome), Memory tab (read-only notes), Profile tab (year, CGPA/probation, credit bar, courses). 380px panel on desktop, bottom sheet on mobile.
- **All my cases** (`components/cases/CasesPage.tsx`): List and Board views.
- **Instructor** (`components/instructor/`): Waiting for you / Decided, open any case by id, review screen (eligibility at submission, audit trail, Approve / Reject with reason), live resumed run, inline refusal for non-owners.

## Demo script (mock)

1. As **S1**, click "Please submit a force-enrollment request for CS412 section S1" → Confirm.
2. Switch to **Instructor I1** → open the case under *Waiting for you* → Approve (or Reject with a reason).
3. Switch back to **S1** → bell shows the notice; open the chat to see the outcome and the new memory note.
4. To see a refusal: as **I2**, paste the case id into "Open case by id" and try to approve.

## Scenarios the mock covers

1. Eligibility question ("can I get force enrolled in CS412"): plan → rules → checker (list sections, check S1, check S2) → verdict → answer with rule chips.
2. Submit (S1, "submit … CS412 section S1"): checker → `submit_case` → `confirm_submission`. Confirm → SUBMITTED → AWAITING_APPROVAL (+ `APPROVAL_REQUESTED` notice to I1) → `execute_enrollment` paused → `waiting_for_instructor`. Decline → CANCELLED + memory note.
3. Instructor approves → APPROVED → EXECUTING → COMPLETED (FORCE), `COMPLETED` + `AGENT_MESSAGE` notices, memory note, celebration. Reject → REJECTED, notice contains "rejected by instructor I1. Reason: …", memory note. Wrong instructor → `403` "I2 does not own CS412-S1", recorded as `APPROVAL_REFUSED`; case keeps waiting.
4. Ineligible students (S2–S9) get the matching blocking codes; asking to submit never shows a confirmation. S6 → CS582 shows PROBATION + CGPA_BELOW_MIN.
5. Vague course ("the machine learning course") → `ask_student` "Which course code do you mean?" → answering "CS412" resumes into scenario 1.
6. Memory ("what happened with my last request") → answer from memory with the "From your memory" chip; no notes → "I don't have any record of a previous request."
7. Profile ("how many credits") → one `get_my_profile` step.
8. Repeat submit while a case is open → "You already have an open request for this course: case FE-… (AWAITING_APPROVAL)."
9. `/loop` → `run.finished limit_reached` → error card with Retry.

Also: "yes / please submit" after an eligibility answer submits the offered section; suggestion buttons on the verdict card ask about open sections; Stop aborts a run.

Seeded history: S1 has completed case `FE-0f2144b5` (CS412-S1, approved by I1, includes a refused attempt by I2) and a plain chat; S2 has rejected case `FE-7b3e90a2` (CS360-S1).

## Notes and gaps against the contract

- **Instructor "Decided" list**: no endpoint in the contract. `ApiClient.listDecided` is implemented by the mock; `httpApi` returns `[]` until an endpoint exists (suggested: `GET /api/instructors/{id}/decided`).
- **Instructor notifications**: the contract only has `GET /api/students/{id}/notifications`. The client calls the same path with an instructor id.
- **"Eligibility at submission"** on the instructor screen reads `detail.eligibility` of the `APPROVAL_REQUESTED` audit event. The real backend should put those facts there (or the screen shows "Not recorded yet").
- **Seeded past case date**: S1's completed `FE-0f2144b5` is dated Spring 2026 so it doesn't block the Fall 2026 happy path for CS412-S1.
- **Case creation timing**: following scenario 2, the case is created (DRAFT → AWAITING_CONFIRMATION) when the agent prepares the request, so Decline can end in CANCELLED. The inspector's empty state says so.
- **Reconnection**: if a stream drops, the turn ends with an error card and Retry; reopening the chat reloads messages from `GET /api/sessions/{id}/messages`. There is no automatic SSE resume (the contract has no run-resume endpoint).
- No tokens, secrets or approval tokens are read, shown or stored. Identity ids are sent with calls for the demo only.

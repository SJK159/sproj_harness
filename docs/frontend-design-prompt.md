# Prompt for Claude Design: LUMS Force-Enrollment Assistant (web frontend)

Copy everything below the line into Claude Design.

---

## What to build

Design and build a production-quality web frontend for **LUMS Force-Enrollment Assistant**: a chat app in the style of Claude, ChatGPT and Gemini, where a university student talks to an AI agent that checks course rules, submits force-enrollment requests, waits for instructor approval and enrolls the student. Alongside the chat, the app shows **case histories**, the **state of every case**, the student's **long-term memory**, and the agent's **thought process live while it works**.

It is a senior-project demo (LUMS, Pakistan), used by the team and shown to a supervisor. It must be **intuitive to someone who has never seen it**, calm and trustworthy (it handles enrollment approvals), and pleasant to use, with tasteful animations and transitions.

The backend already exists (Python, LangGraph "deep agent"). It does **not** have an HTTP API yet. So: build the frontend against a **typed API contract** (below), with a **mock API** that simulates the backend realistically (streaming, delays, pauses). Later we will write the real API to the same contract and switch one setting. Everything must run with the mock alone.

## Deliverable (important)

A zip whose root is a single folder named **`frontend/`**. We will drop it into our repository as `sproj-orchestrator/frontend/`.

- Stack: **React 18 + TypeScript (strict) + Vite**, **Tailwind CSS**, **Framer Motion** for animation, **lucide-react** icons. No other UI framework. No backend, no server code.
- `frontend/README.md`: what it is, `npm install`, `npm run dev`, how to switch mock vs real API, a short tour of the screens, and where each part of the contract lives.
- `frontend/.env.example`: `VITE_USE_MOCK=true` and `VITE_API_BASE_URL=http://localhost:8000`. No secrets anywhere.
- `src/api/types.ts` (the contract types, exactly as below), `src/api/client.ts` (interface), `src/api/mockApi.ts` (simulation), `src/api/httpApi.ts` (real implementation using `fetch` + Server-Sent Events, compiled but unused while mock is on). Components only talk to the `client.ts` interface.
- `npm run build` and `npm run typecheck` must pass.
- Organise components by feature (`chat/`, `cases/`, `memory/`, `instructor/`, `thinking/`, `layout/`, `ui/`).

## The domain in 60 seconds (so the UI is right)

- **Force enrollment (FE):** joining a course section that is already **full**, with the instructor's approval. If a section has open seats, the student should just register normally; no FE needed.
- **Eligibility rules** (placeholders written by the team, **not official LUMS policy**; always show the "placeholder" label): each rule has a label the agent cites, e.g. `FE-2 (placeholder v0.1)`.

| Label | Rule | Codes |
|---|---|---|
| FE-1 | FE is for full sections; open seats mean register normally | `SEATS_AVAILABLE`, `OTHER_SECTION_OPEN` (advisory, not failures) |
| FE-2 | Prerequisites must be completed (in progress does not count) | `PREREQ_MISSING`, `PREREQ_IN_PROGRESS` |
| FE-3 | No timetable clash | `CLASH` |
| FE-4 | Credit cap 20 | `CREDIT_LIMIT` |
| FE-5 | No FE on probation (CGPA below 2.0) | `PROBATION` |
| FE-6 | Section restrictions (year, CGPA) | `YEAR_RESTRICTION`, `CGPA_BELOW_MIN` |
| FE-7 | Instructor must accept FE, within a cap of FE slots | `FE_NOT_ACCEPTED`, `FE_CAP_REACHED` |
| FE-8 | One section per course; course offered this term | `ALREADY_ENROLLED`, `NOT_OFFERED` |

- **A case** is one force-enrollment request. **One chat session = one case at most**; the session id *is* the case id (format `FE-` + 8 hex chars, e.g. `FE-45c1d9b5`). A session with no case yet is just a chat.
- **Case states** (exact strings) and their flow:
  - Main path: `DRAFT → AWAITING_CONFIRMATION → SUBMITTED → AWAITING_APPROVAL → APPROVED → EXECUTING → COMPLETED`
  - Endings that never enroll: `CANCELLED` (student said no, or no longer eligible at submit), `REJECTED` (instructor said no), `FAILED` (approval could not be verified, FE slots ran out, or a rule failed at the last re-check; may carry a `flag` = needs human review).
- **Two human checkpoints**, both are pauses the agent waits on:
  1. **Student confirmation**: before submitting, the student confirms or declines. Only **Confirm** / **Decline**; never an "edit request" option.
  2. **Instructor approval**: the section's instructor approves or rejects (with a reason). Can take days; the student can leave. Only the section's owner may decide; others are refused.
- **Agents:** a **main agent** (talks to the student) and an **eligibility checker** sub-agent (runs the rule checks in its own context, returns a structured verdict; read-only; it may ask the student one clarifying question, e.g. "Which course code do you mean?").
- **Memory:** per-student notes about finished cases, one line per case, written **by the system from the case record** (never free text from the chat). Shown read-only. Example: `2026-10-17 FE-0f2144b5: force enrollment in CS412-S1 COMPLETED (approved by I1; force enrollment).`
- **Privacy:** a student only ever sees their **own** profile, cases, notices and memory.
- All data is **synthetic**. Show a small, unobtrusive "Synthetic demo data" badge.

## Screens and layout

### Overall shell (desktop first, works down to a 390 px phone)

Three regions, like Claude/ChatGPT with an inspector:

1. **Left sidebar** (collapsible, 272 px; slides over as a drawer on mobile)
   - App name and a small logo mark; **New chat** button (primary).
   - **Who am I** switcher at the top: role toggle **Student / Instructor** (clearly labelled "Demo: switch user"; there is no real login) and a dropdown of identities. Students S1-S9 with one-line hints (from the seed data table below), instructors I1-I4.
   - **Sessions**, grouped: **Active cases** (state not final), **Past cases**, **Chats** (no case). Each item: title (auto from the first message or the course, e.g. "CS412-S1 force enrollment"), relative time, and a coloured **state pill**. Hover reveals the case id.
   - Search box filtering sessions.
   - **Notifications** bell with an unread count; opens a popover list (kinds: `COMPLETED`, `REJECTED`, `FAILED`, `APPROVAL_REQUESTED`, `AGENT_MESSAGE`), mark-as-read on open.
   - Footer: theme toggle (light/dark/system), "Synthetic demo data" badge.

2. **Center: the chat** (max text width ~760 px, centered)
   - Empty state for a new chat: friendly greeting with the student's name and **suggestion chips**: "Can I get force enrolled in CS412?", "Please submit a force-enrollment request for CS412 section S1", "What happened with my last request?", "How many credits am I taking?", "Can I get into the machine learning course?".
   - User messages right-aligned in a soft bubble; assistant messages left, no bubble (like Claude), with a small avatar.
   - Each assistant turn has, **above** its answer, a **Thinking panel** (see "Thought process" below).
   - Markdown rendering (headings, lists, tables, bold, code). **Rule labels** like `FE-4 (placeholder v0.1)` (also when written with a non-breaking hyphen `FE‑4`) render as **rule chips**; hovering shows the rule text from the table above.
   - Structured content rendered as cards (see "Inline cards").
   - **Composer** pinned to the bottom: auto-growing textarea, send button (Enter to send, Shift+Enter for newline), stop button while running. Disabled with an explanation while the case waits for the instructor ("This request is with the instructor. Start a new chat for another course.").
   - **Live status strip** just above the composer while the agent runs: current step in plain words + the case state pill + elapsed seconds, e.g. "Checking the rules for CS412-S1 · AWAITING_APPROVAL · 4s".

3. **Right panel: Case inspector** (toggle button in the header; 380 px; becomes a bottom sheet on mobile). Tabs:
   - **Case**: the current session's case.
     - Big **state tracker**: the main path as a vertical stepper with the current step highlighted and animated, and side endings (`CANCELLED`, `REJECTED`, `FAILED`) branching off where they apply. No case yet: an explanation "No case yet. A case is created when you confirm a submission."
     - Facts: case id (copyable), section, instructor, created/updated, `next_action`, a red **flag** banner if set ("Flagged for review: approval could not be verified").
     - **Audit trail**: timeline of every event (actor, action, from → to, timestamp, detail on expand). Refusal rows (e.g. `APPROVAL_REFUSED`, `TOKEN_REFUSED`, `EXECUTE_REFUSED`) in a muted red style. Explain once in a tooltip: "Every change to a case is recorded and can't be edited."
     - Outcome card when final: enrollment (kind FORCE/REGULAR), or rejection reason and who decided, or failure reason.
   - **Memory**: "What the assistant remembers about you": the notes as a list of cards (date, case id link, section, outcome, detail), read-only with a lock icon and the sentence "Written by the system from your case records. You can't edit these, and neither can the assistant." Empty state for students with no history.
   - **Profile**: year, CGPA (probation badge if below 2.0), credits this term (with a 0-20 bar against the cap), completed courses, current enrollments.

### Cases page (sidebar link "All my cases")
A full-width view of the signed-in student's cases: toggle **List** (table: case id, section, state pill, updated, outcome) and **Board** (columns by state group: *In progress*, *Waiting for instructor*, *Completed*, *Not completed*). Clicking opens the session with the inspector open.

### Instructor view (when the role is Instructor)
- Sidebar shows **Waiting for you** (cases in `AWAITING_APPROVAL` for this instructor's sections) and **Decided**.
- Case review screen: student id, section, the eligibility facts at submission, the audit trail, and two buttons: **Approve** and **Reject** (reject requires a reason in a small dialog). No other actions.
- After deciding, show the resumed agent run **live** (same Thinking panel), ending in the new state. If the instructor does not own the section, show the refusal inline ("I2 does not own CS412-S1") and leave the case waiting.
- The student's session, when opened later, shows the outcome and a new notification.

## Thought process: the centrepiece

The user must be able to *see the agent work* without reading logs. For every assistant turn, a **Thinking panel** sits above the answer:

- **While running:** expanded, header "Thinking…" with a subtle shimmer and a live timer. Contents, in order of arrival:
  1. **Plan** (from `todos.updated`): a checklist; items tick with a spring animation as their status moves `pending → in_progress → completed` (in-progress item has a small spinner).
  2. **Steps timeline** (from `tool.*` and `subagent.*` events): one row per step with an icon, a **plain-language title** and, on expand, the raw tool name, arguments and a short result. Friendly titles:
     - `write_todos` → "Planning"
     - `read_file` on `/skills/force-enrollment/SKILL.md` → "Reading the force-enrollment rules"
     - `task` → "Asking the eligibility checker" (a **nested group** containing the sub-agent's own steps, indented, with the checker's verdict shown when it finishes)
     - `list_sections` → "Looking up sections of CS412"
     - `check_my_eligibility` → "Checking the rules for CS412-S1"
     - `get_my_profile` → "Reading your profile"
     - `get_my_cases` → "Looking up your cases"
     - `submit_case` → "Submitting your request"
     - `execute_enrollment` → "Waiting for the instructor" (paused) or "Enrolling you" (after approval)
     - `notify_student` → "Sending you a notice"
     - `save_case_note` → "Saving this to memory"
     - `ask_student` → "The checker has a question for you"
     - Unknown names: show the raw name.
  3. **Reasoning** (from `reasoning.delta`, may be absent): the model's reasoning text in a quieter, smaller style inside a collapsible "Reasoning" section, streamed.
  4. A thin **case-state lane** at the top of the panel: whenever `case.updated` arrives during the run, the pill morphs to the new state with a short label of what caused it ("You confirmed", "Sent to I1", "Approved by I1", "Enrolled").
- **When finished:** collapses to one line: "Thought for 7s · 6 steps · case AWAITING_APPROVAL", expandable again. Keep it collapsed for older turns in the history.
- The **right inspector** updates live during the run (state tracker advances, audit rows slide in), so state and reasoning are visible side by side.

## Inline cards in the chat

- **Eligibility verdict card** (from a `subagent.finished` verdict or tool result): one block per section.
  - Header: section id + an outcome badge: **Can request FE** (green), **No FE needed: seats open** (blue), **Not eligible** (red).
  - Blocking reasons as a list, each with its rule chip and reason text.
  - Advisory notes in a softer style.
  - Suggested open sections as small buttons ("Ask about CS412-S2"), which insert a message.
- **Confirmation card** (interrupt `confirm_submission`): "Submit a force-enrollment request for **CS412-S1**? The instructor will be asked to approve it." Buttons **Confirm** (primary) / **Decline**. After a choice, the card locks, showing the choice and the time.
- **Question card** (interrupt `ask_student`): shows "The eligibility checker asks: Which course code do you mean?", with an input + Send and optional quick answers (course codes mentioned in the conversation).
- **Waiting card** (interrupt `waiting_for_instructor`): calm, animated hourglass/pulse, "Your request FE-45c1d9b5 is with instructor I1. You can close this chat; you'll get a notice when they decide." Links to the case inspector.
- **Outcome card** on completion / rejection / failure, with the matching colour and icon (a small, tasteful celebration on `COMPLETED`: brief particle burst or a check that draws itself; nothing on other outcomes).
- **Memory badge** on answers that used memory: "From your memory" chip linking to the Memory tab.
- **Error / limit card**: if the run ends with `limit_reached` or `error`, a friendly card ("The assistant stopped to avoid a loop. Try rephrasing.") with a Retry button.

## Visual design

- Calm, neutral, editorial, close to Claude's feel: warm off-white light theme and a deep slate dark theme. Accent: teal `#2A7F8E`, deep navy `#1F3A5F` for headings, used sparingly. Generous whitespace, 8 px spacing grid, 12-16 px radii, soft 1 px borders rather than heavy shadows.
- Typography: Inter (or system UI); 15 px body in chat, 13 px for meta text; tabular numbers for times and ids; monospace for case ids and tool names.
- **State colours** (pill background tint + darker text; also use an icon, never colour alone):
  - `DRAFT`, `AWAITING_CONFIRMATION`: neutral grey
  - `SUBMITTED`, `AWAITING_APPROVAL`: amber
  - `APPROVED`, `EXECUTING`: teal
  - `COMPLETED`: green
  - `CANCELLED`: slate
  - `REJECTED`, `FAILED`: red
- Iconography: lucide; one icon per step type (planning: list-checks; rules: book-open; checker: user-search; submit: send; waiting: hourglass; enroll: graduation-cap; memory: brain or bookmark; notice: bell).

## Motion (make it delightful, never noisy)

- Durations 150-300 ms, ease-out; springs for checkmarks and pills (stiffness ~400, damping ~30).
- Streaming text with a soft blinking caret; "Thinking…" shimmer; steps slide in from 8 px below with fade; nested sub-agent group expands with height animation.
- Case state pill **morphs** (shared layout animation) between states; the stepper's progress line fills to the new step; audit rows stagger in.
- Cards enter with a slight scale (0.98 → 1) and fade. Sidebar collapse, inspector open/close and mobile drawers slide.
- Confirm/Decline and Approve/Reject buttons give a pressed state and a brief success morph.
- Respect `prefers-reduced-motion`: replace movement with simple fades and turn off the celebration.

## Accessibility and quality

- Full keyboard use; visible focus rings; `aria-live="polite"` on the live status strip and streaming answer; buttons with labels; WCAG AA contrast in both themes.
- Never block the UI on a stream: show partial content as it arrives; handle stream errors and reconnection gracefully.
- Loading skeletons for sidebar, inspector and profile.
- No secrets, tokens or approval tokens are ever shown or stored by the frontend.

## API contract (build exactly this; `src/api/types.ts`)

```ts
export type CaseState =
  | "DRAFT" | "AWAITING_CONFIRMATION" | "SUBMITTED" | "AWAITING_APPROVAL"
  | "APPROVED" | "EXECUTING" | "COMPLETED" | "REJECTED" | "FAILED" | "CANCELLED";

export interface StudentSummary { student_id: string; name: string; hint: string }   // hint: one line for the switcher
export interface InstructorSummary { instructor_id: string; name: string; sections: string[] }

export interface Profile {
  student_id: string; name: string; program: string; year: number; cgpa: number; on_probation: boolean;
  completed: string[]; enrollments: { offering_id: string; course_id: string }[]; credits: number;
}

export interface Case {
  case_id: string; student_id: string; offering_id: string; state: CaseState;
  next_action: string | null; flag: string | null; created_at: string; updated_at: string;
}
export interface AuditEvent {
  event_id: number; case_id: string; actor: string; action: string;
  from_state: CaseState | null; to_state: CaseState | null; timestamp: string; detail: Record<string, unknown> | null;
}
export interface CaseDetail {
  case: Case; audit: AuditEvent[];
  approval: { instructor_id: string; decision: "APPROVE" | "REJECT"; reason: string | null; created_at: string } | null;
  enrollment: { enrollment_id: number; kind: "FORCE" | "REGULAR" } | null;
  instructor_id: string;               // owner of the section
}

export type NotificationKind = "APPROVAL_REQUESTED" | "REJECTED" | "COMPLETED" | "FAILED" | "AGENT_MESSAGE";
export interface Notification {
  notification_id: number; recipient_id: string; case_id: string | null; kind: NotificationKind;
  message: string; created_at: string; read_at: string | null;
}

export interface MemoryNote { date: string; case_id: string; offering_id: string; outcome: CaseState; detail: string; raw: string }
export interface Memory { student_id: string; notes: MemoryNote[] }

export interface Reason { code: string; rule: string; reason: string }       // rule like "FE-2 (placeholder v0.1)"
export interface SectionVerdict {
  offering_id: string | null; can_submit: boolean; fe_needed: boolean;
  blocking: Reason[]; advisory: Reason[]; suggestions: string[];
}
export interface EligibilityVerdict { course_id: string; sections: SectionVerdict[]; error: string | null; summary: string }

export interface Todo { content: string; status: "pending" | "in_progress" | "completed" }

export type Interrupt =
  | { kind: "confirm_submission"; case_id: string; offering_id: string; description: string }
  | { kind: "ask_student"; question: string }
  | { kind: "waiting_for_instructor"; case_id: string; instructor_id: string; description: string };

export interface ChatMessage {
  message_id: string; role: "user" | "assistant"; text: string; created_at: string;
  thinking?: { todos: Todo[]; steps: Step[]; reasoning: string; duration_ms: number; case_states: CaseState[] };
  verdict?: EligibilityVerdict; interrupt?: Interrupt; used_memory?: boolean;
}
export interface Step {
  call_id: string; name: string; agent: "main" | "eligibility-checker";
  args: Record<string, unknown>; status: "running" | "done" | "error" | "paused";
  summary?: string; children?: Step[];     // children = steps inside a sub-agent call
}

export interface Session {
  session_id: string;                      // equals the case id, e.g. "FE-45c1d9b5"
  student_id: string; title: string; created_at: string; updated_at: string;
  case: Case | null; pending_interrupt: Interrupt | null;
}

// Server-Sent Events emitted by a run (one JSON object per `data:` line, `event:` = type)
export type RunEvent =
  | { type: "run.started"; run_id: string; session_id: string }
  | { type: "reasoning.delta"; text: string }
  | { type: "todos.updated"; todos: Todo[] }
  | { type: "tool.started"; call_id: string; name: string; args: Record<string, unknown>; agent: Step["agent"]; parent_call_id?: string }
  | { type: "tool.finished"; call_id: string; name: string; ok: boolean; summary: string; result?: unknown }
  | { type: "subagent.started"; call_id: string; name: string; description: string }
  | { type: "subagent.finished"; call_id: string; verdict: EligibilityVerdict | null }
  | { type: "case.updated"; case: Case; event: AuditEvent }
  | { type: "notification.created"; notification: Notification }
  | { type: "memory.updated"; student_id: string; note: MemoryNote }
  | { type: "interrupt"; interrupt: Interrupt }
  | { type: "message.delta"; text: string }
  | { type: "message.completed"; message: ChatMessage }
  | { type: "run.finished"; status: "answered" | "waiting_for_instructor" | "interrupted" | "limit_reached" | "error"; error?: string };
```

**Endpoints** (`httpApi.ts`; streaming ones return `text/event-stream` of `RunEvent`):

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/students` | | `StudentSummary[]` |
| GET | `/api/instructors` | | `InstructorSummary[]` |
| GET | `/api/students/{id}/profile` | | `Profile` |
| GET | `/api/students/{id}/sessions` | | `Session[]` |
| GET | `/api/students/{id}/cases` | | `Case[]` |
| GET | `/api/students/{id}/memory` | | `Memory` |
| GET | `/api/students/{id}/notifications` | | `Notification[]` |
| POST | `/api/notifications/read` | `{ ids: number[] }` | `204` |
| POST | `/api/sessions` | `{ student_id }` | `Session` (new id, no case) |
| GET | `/api/sessions/{id}/messages` | | `ChatMessage[]` |
| POST | `/api/sessions/{id}/messages` | `{ student_id, text }` | SSE stream |
| POST | `/api/sessions/{id}/resume` | `{ student_id, decision: "approve" \| "reject" }` or `{ student_id, answer: string }` | SSE stream |
| GET | `/api/cases/{id}` | | `CaseDetail` |
| GET | `/api/instructors/{id}/pending` | | `Case[]` |
| POST | `/api/cases/{id}/decision` | `{ instructor_id, decision: "approve" \| "reject", reason?: string }` | SSE stream of the resumed run, or `403 { error }` when not the owner |
| POST | `/api/sessions/{id}/stop` | | `204` |

The frontend sends the acting student or instructor id with each call (demo only; the real API takes identity from its own session).

## Mock API: simulate the real system

`mockApi.ts` keeps an in-memory world (reset button in a small "Demo" menu) seeded with the data below, and emits `RunEvent`s with realistic delays: 300-900 ms per step, text streamed at ~40 characters per tick, reasoning a little faster. It must implement these scripted behaviours by matching the user's message (case-insensitive keywords) and the signed-in student:

1. **Eligibility question** ("can I get force enrolled in CS412", any student): plan (3-4 todos) → read rules → eligibility checker (nested: look up CS412 sections, check S1, check S2) → verdict per the seed data → short answer citing rule chips. For S1: CS412-S1 can request FE, CS412-S2 has 5 open seats (advisory FE-1).
2. **Submit** ("please submit … CS412 section S1", S1): plan → checker → `submit_case` step → `interrupt confirm_submission`. On **Confirm**: `case.updated` DRAFT → AWAITING_CONFIRMATION → SUBMITTED → AWAITING_APPROVAL (an `APPROVAL_REQUESTED` notice goes to I1), then `execute_enrollment` pauses with `interrupt waiting_for_instructor`, `run.finished waiting_for_instructor`. On **Decline**: CANCELLED, a short answer, memory note saved.
3. **Instructor approves** (I1 on that case): resumed run → APPROVED → EXECUTING → COMPLETED, enrollment FORCE, notices `COMPLETED` + `AGENT_MESSAGE` to the student, `memory.updated`, celebration. **Rejects** with reason: REJECTED, the student's notice contains "rejected by instructor I1. Reason: …", memory note saved. **Wrong instructor** (I2): `403` with "I2 does not own CS412-S1"; the case stays waiting.
4. **Ineligible** (e.g. S2 → CS412-S1, S3, S5, S6 … per the table): verdict with the blocking codes; if the student still asks to submit, the confirmation card never appears and the answer explains why. S6 → CS582-S1 shows **two** codes (PROBATION, CGPA_BELOW_MIN).
5. **Vague course** ("the machine learning course"): the checker emits `interrupt ask_student` "Which course code do you mean?"; the answer "CS412" resumes the run into scenario 1.
6. **Memory** ("what happened with my last request"): no tools, answer from memory with the "From your memory" chip; for a student with no notes: "I don't have any record of a previous request."
7. **Profile** ("how many credits"): one `get_my_profile` step, answer from the profile.
8. **Repeat question while a case is open** (S1 asks to submit CS412 again in another chat): "You already have an open request for this course: case FE-… (AWAITING_APPROVAL)."
9. **Limit reached**: a hidden demo trigger (message "/loop") ends with `run.finished limit_reached` to show the error card.

Pre-seed S1 with one **completed past case** (`FE-0f2144b5`, CS412-S1, approved by I1) and its memory note, and S2 with one **rejected** past case, so histories and memory are not empty on first open.

## Seed data (synthetic; use these exact ids)

Term: Fall 2026. Students:

| Id | Name | Year | CGPA | Credits now | Hint for the switcher |
|---|---|---|---|---|---|
| S1 | Student One | 4 | 3.4 | 15 | Eligible for CS412-S1 (happy path) |
| S2 | Student Two | 3 | 3.0 | 3 | Missing prerequisite CS310 |
| S3 | Student Three | 3 | 3.1 | 3 | Timetable clash with CS412-S1 (MATH120) |
| S4 | Student Four | 3 | 3.2 | 3 | CS310 still in progress |
| S5 | Student Five | 4 | 3.3 | 20 | At the 20-credit cap |
| S6 | Student Six | 3 | 1.9 | 3 | On probation |
| S7 | Student Seven | 2 | 3.2 | 3 | Too junior for CS381 (year 4+) |
| S8 | Student Eight | 4 | 3.0 | 3 | Already enrolled in CS412 |
| S9 | Student Nine | 4 | 2.8 | 3 | Below CS582's CGPA 3.0 minimum |

Instructors: I1 (CS412, CS360), I2 (CS300, CS370, CS471), I3 (CS381, MATH120, CS582), I4 (gen-ed, CS310).

Sections:
- **CS412-S1:** full, accepts FE, 3 FE slots, MW 11:00-12:15.
- **CS412-S2:** 5 seats open, TR 14:00-15:15.
- **CS360-S1:** full, accepts FE, 1 FE slot.
- **CS370-S1:** full, instructor does not accept FE.
- **CS471-S1:** full, FE slots used up.
- **CS381-S1:** full, seniors only.
- **MATH120-S1:** full, MW 11:00-12:15.
- **CS582-S1:** full, minimum CGPA 3.0.
- **CS999:** in the catalogue, not offered.

## Things to avoid

- No login screen, no real authentication, no settings pages beyond theme.
- No "edit request" or free-form override on approvals: approve or reject only.
- Never let a student see another student's cases, notes or profile in the student view.
- Don't invent states, codes or tool names beyond the contract; show unknown ones raw.
- No stock-photo imagery, no heavy gradients, no glassmorphism; keep it calm and readable.

When you finish, list in the README which scenarios the mock covers and any part of the contract you could not implement.

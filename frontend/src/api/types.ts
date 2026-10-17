// API contract. Keep in sync with the backend. Do not add states, codes or tool names here.

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

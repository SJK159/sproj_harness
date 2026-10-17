import type {
  Case, CaseDetail, ChatMessage, InstructorSummary, Memory, Notification, Profile, RunEvent, Session, StudentSummary,
} from './types';
import { createMockApi } from './mockApi';
import { createHttpApi } from './httpApi';

/** A running agent turn. Iterate `events`; call `stop()` to abort the stream. */
export interface RunStream {
  events: AsyncIterable<RunEvent>;
  stop: () => void;
}

export type Decision = 'approve' | 'reject';
export type ResumeBody = { student_id: string; decision: Decision } | { student_id: string; answer: string };
export type DecisionResult = { ok: true; stream: RunStream } | { ok: false; status: number; error: string };

/** The only surface components talk to. Implemented by mockApi.ts and httpApi.ts. */
export interface ApiClient {
  readonly mode: 'mock' | 'http';
  listStudents(): Promise<StudentSummary[]>;
  listInstructors(): Promise<InstructorSummary[]>;
  getProfile(studentId: string): Promise<Profile>;
  listSessions(studentId: string): Promise<Session[]>;
  listCases(studentId: string): Promise<Case[]>;
  getMemory(studentId: string): Promise<Memory>;
  /** GET /api/students/{id}/notifications (also used with instructor ids, see README). */
  listNotifications(recipientId: string): Promise<Notification[]>;
  markNotificationsRead(ids: number[]): Promise<void>;
  createSession(studentId: string): Promise<Session>;
  getMessages(sessionId: string): Promise<ChatMessage[]>;
  sendMessage(sessionId: string, studentId: string, text: string): RunStream;
  resume(sessionId: string, body: ResumeBody): RunStream;
  getCase(caseId: string): Promise<CaseDetail>;
  listPending(instructorId: string): Promise<Case[]>;
  /** Not in the contract yet: cases this instructor already decided. httpApi returns []. */
  listDecided(instructorId: string): Promise<Case[]>;
  decide(caseId: string, instructorId: string, decision: Decision, reason?: string): Promise<DecisionResult>;
  stop(sessionId: string): Promise<void>;
  /** Mock only: restore the seeded world. */
  resetDemo?: () => void;
}

const useMock = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false';

export const api: ApiClient = useMock
  ? createMockApi()
  : createHttpApi(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000');

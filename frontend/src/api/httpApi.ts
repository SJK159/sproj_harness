import type { ApiClient, Decision, DecisionResult, ResumeBody, RunStream } from './client';
import { ApiError } from './errors';
import type {
  Case, CaseDetail, ChatMessage, InstructorSummary, Memory, Notification, Profile, RunEvent, Session, StudentSummary,
} from './types';

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: string; detail?: string };
    return body.error ?? body.detail ?? res.statusText;
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

/** Parse a text/event-stream body into RunEvents. Tolerates CRLF and comment/keep-alive lines. */
export async function* parseSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<RunEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      for (;;) {
        const m = /\r?\n\r?\n/.exec(buf);
        if (!m) break;
        const raw = buf.slice(0, m.index);
        buf = buf.slice(m.index + m[0].length);
        const data = raw
          .split(/\r?\n/)
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).replace(/^ /, ''))
          .join('\n');
        if (!data) continue;
        try {
          yield JSON.parse(data) as RunEvent;
        } catch {
          // ignore malformed frames
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function createHttpApi(baseUrl: string): ApiClient {
  const base = baseUrl.replace(/\/$/, '');

  async function json<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(base + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!res.ok) throw new ApiError(res.status, await readError(res));
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  function streamFromResponse(resPromise: Promise<Response>, ctrl: AbortController): RunStream {
    async function* gen(): AsyncGenerator<RunEvent> {
      const res = await resPromise;
      if (!res.ok || !res.body) throw new ApiError(res.status, await readError(res));
      yield* parseSSE(res.body);
    }
    return { events: gen(), stop: () => ctrl.abort() };
  }

  function post(path: string, body: unknown, ctrl: AbortController): Promise<Response> {
    return fetch(base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  }

  return {
    mode: 'http',
    listStudents: () => json<StudentSummary[]>('/api/students'),
    listInstructors: () => json<InstructorSummary[]>('/api/instructors'),
    getProfile: (id) => json<Profile>(`/api/students/${encodeURIComponent(id)}/profile`),
    listSessions: (id) => json<Session[]>(`/api/students/${encodeURIComponent(id)}/sessions`),
    listCases: (id) => json<Case[]>(`/api/students/${encodeURIComponent(id)}/cases`),
    getMemory: (id) => json<Memory>(`/api/students/${encodeURIComponent(id)}/memory`),
    listNotifications: (id) => json<Notification[]>(`/api/students/${encodeURIComponent(id)}/notifications`),
    markNotificationsRead: (ids) => json<void>('/api/notifications/read', { method: 'POST', body: JSON.stringify({ ids }) }),
    createSession: (student_id) => json<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ student_id }) }),
    getMessages: (id) => json<ChatMessage[]>(`/api/sessions/${encodeURIComponent(id)}/messages`),
    sendMessage(sessionId, student_id, text) {
      const ctrl = new AbortController();
      return streamFromResponse(post(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, { student_id, text }, ctrl), ctrl);
    },
    resume(sessionId, body: ResumeBody) {
      const ctrl = new AbortController();
      return streamFromResponse(post(`/api/sessions/${encodeURIComponent(sessionId)}/resume`, body, ctrl), ctrl);
    },
    getCase: (id) => json<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`),
    listPending: (id) => json<Case[]>(`/api/instructors/${encodeURIComponent(id)}/pending`),
    listDecided: async () => [],
    async decide(caseId, instructor_id, decision: Decision, reason?: string): Promise<DecisionResult> {
      const ctrl = new AbortController();
      const res = await post(`/api/cases/${encodeURIComponent(caseId)}/decision`, { instructor_id, decision, reason }, ctrl);
      if (!res.ok) return { ok: false, status: res.status, error: await readError(res) };
      return { ok: true, stream: streamFromResponse(Promise.resolve(res), ctrl) };
    },
    stop: (id) => json<void>(`/api/sessions/${encodeURIComponent(id)}/stop`, { method: 'POST' }),
  };
}

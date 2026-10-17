import type { AuditEvent, CaseState, ChatMessage, EligibilityVerdict, Interrupt, RunEvent, Step, Todo } from '../api/types';

export type RunStatus = 'running' | Extract<RunEvent, { type: 'run.finished' }>['status'];
export interface LaneEntry { state: CaseState; label: string }

/** Client-side view of one assistant turn, built by folding RunEvents. Shared by the UI and the mock. */
export interface LiveTurn {
  localId: string;
  runId: string | null;
  todos: Todo[];
  steps: Step[];
  reasoning: string;
  text: string;
  lane: LaneEntry[];
  verdict?: EligibilityVerdict;
  interrupt?: Interrupt;
  usedMemory?: boolean;
  startedAt: number;
  finishedAt: number | null;
  status: RunStatus;
  error?: string;
  message?: ChatMessage;
}

let counter = 0;
export function newTurn(): LiveTurn {
  counter += 1;
  return {
    localId: `turn-${Date.now()}-${counter}`, runId: null, todos: [], steps: [], reasoning: '', text: '',
    lane: [], startedAt: Date.now(), finishedAt: null, status: 'running',
  };
}

function mapSteps(steps: Step[], fn: (s: Step) => Step): Step[] {
  return steps.map((s) => {
    const m = fn(s);
    return m.children ? { ...m, children: mapSteps(m.children, fn) } : m;
  });
}

function hasStep(steps: Step[], id: string): boolean {
  return steps.some((s) => s.call_id === id || (s.children ? hasStep(s.children, id) : false));
}

function insertChild(steps: Step[], parentId: string, step: Step): Step[] | null {
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i];
    if (s.call_id === parentId) {
      const copy = [...steps];
      copy[i] = { ...s, children: [...(s.children ?? []), step] };
      return copy;
    }
    if (s.children) {
      const inner = insertChild(s.children, parentId, step);
      if (inner) {
        const copy = [...steps];
        copy[i] = { ...s, children: inner };
        return copy;
      }
    }
  }
  return null;
}

const updateStep = (steps: Step[], id: string, patch: Partial<Step>) =>
  mapSteps(steps, (s) => (s.call_id === id ? { ...s, ...patch } : s));

export function laneLabel(ev: AuditEvent): string {
  const d = ev.detail ?? {};
  switch (ev.action) {
    case 'CASE_CREATED': return 'Case created';
    case 'CONFIRMATION_REQUESTED': return 'Waiting for you to confirm';
    case 'STUDENT_CONFIRMED': return 'You confirmed';
    case 'STUDENT_DECLINED': return 'You declined';
    case 'APPROVAL_REQUESTED': return `Sent to ${typeof d.instructor_id === 'string' ? d.instructor_id : 'the instructor'}`;
    case 'APPROVED': return `Approved by ${ev.actor}`;
    case 'REJECTED': return `Rejected by ${ev.actor}`;
    case 'EXECUTION_STARTED': return 'Enrolling';
    case 'ENROLLED': return 'Enrolled';
    case 'NO_LONGER_ELIGIBLE': return 'No longer eligible';
    case 'FAILED': return 'Failed';
    default: return humanize(ev.action);
  }
}

export function humanize(code: string): string {
  const s = code.replace(/_/g, ' ').toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function applyRunEvent(t: LiveTurn, ev: RunEvent): LiveTurn {
  switch (ev.type) {
    case 'run.started':
      return { ...t, runId: ev.run_id };
    case 'reasoning.delta':
      return { ...t, reasoning: t.reasoning + ev.text };
    case 'todos.updated':
      return { ...t, todos: ev.todos };
    case 'tool.started': {
      if (hasStep(t.steps, ev.call_id)) return t;
      const step: Step = { call_id: ev.call_id, name: ev.name, agent: ev.agent, args: ev.args, status: 'running' };
      const nested = ev.parent_call_id ? insertChild(t.steps, ev.parent_call_id, step) : null;
      return { ...t, steps: nested ?? [...t.steps, step] };
    }
    case 'tool.finished':
      return { ...t, steps: updateStep(t.steps, ev.call_id, { status: ev.ok ? 'done' : 'error', summary: ev.summary }) };
    case 'subagent.started': {
      if (hasStep(t.steps, ev.call_id)) {
        return { ...t, steps: mapSteps(t.steps, (s) => (s.call_id === ev.call_id ? { ...s, children: s.children ?? [] } : s)) };
      }
      const step: Step = { call_id: ev.call_id, name: 'task', agent: 'main', args: { description: ev.description }, status: 'running', children: [] };
      return { ...t, steps: [...t.steps, step] };
    }
    case 'subagent.finished':
      return {
        ...t,
        verdict: ev.verdict ?? t.verdict,
        steps: ev.verdict ? updateStep(t.steps, ev.call_id, { summary: ev.verdict.summary }) : t.steps,
      };
    case 'case.updated':
      return { ...t, lane: [...t.lane, { state: ev.case.state, label: laneLabel(ev.event) }] };
    case 'interrupt':
      return {
        ...t,
        interrupt: ev.interrupt,
        steps: mapSteps(t.steps, (s) => (s.status === 'running' ? { ...s, status: 'paused' } : s)),
      };
    case 'message.delta':
      return { ...t, text: t.text + ev.text };
    case 'message.completed':
      return {
        ...t,
        message: ev.message,
        text: ev.message.text,
        usedMemory: ev.message.used_memory,
        verdict: ev.message.verdict ?? t.verdict,
        interrupt: ev.message.interrupt ?? t.interrupt,
      };
    case 'run.finished':
      return { ...t, status: ev.status, error: ev.error, finishedAt: Date.now() };
    default:
      return t;
  }
}

export function turnToThinking(t: LiveTurn): NonNullable<ChatMessage['thinking']> {
  return {
    todos: t.todos,
    steps: t.steps,
    reasoning: t.reasoning,
    duration_ms: (t.finishedAt ?? Date.now()) - t.startedAt,
    case_states: t.lane.map((l) => l.state),
  };
}

export function countSteps(steps: Step[]): number {
  return steps.reduce((n, s) => n + 1 + (s.children ? countSteps(s.children) : 0), 0);
}

export function deepestRunning(steps: Step[]): Step | null {
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    if (s.status === 'running' || s.status === 'paused') {
      const inner = s.children ? deepestRunning(s.children) : null;
      return inner ?? s;
    }
  }
  return null;
}

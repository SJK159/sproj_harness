// In-memory simulation of the backend. Emits RunEvents with realistic timing.
import type { ApiClient, Decision, DecisionResult, ResumeBody, RunStream } from './client';
import { ApiError } from './errors';
import type {
  AuditEvent, CaseDetail, CaseState, ChatMessage, EligibilityVerdict, Interrupt, MemoryNote, Notification,
  NotificationKind, Profile, Reason, RunEvent, SectionVerdict, Session, Step, Todo,
} from './types';
import { COURSES, INSTRUCTORS, SECTIONS, STUDENTS, TERM, seedProfiles, type SectionDef } from './mockSeed';
import { applyRunEvent, newTurn, turnToThinking } from '../lib/turn';

const SKILL_PATH = '/skills/force-enrollment/SKILL.md';
const rule = (n: number, nb = false) => `FE${nb ? '\u2011' : '-'}${n} (placeholder v0.1)`;
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const hex8 = () => Array.from({ length: 8 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
const nowIso = () => new Date().toISOString();
const today = () => new Date().toISOString().slice(0, 10);
const STOP = Symbol('stop');
const FINAL: CaseState[] = ['COMPLETED', 'REJECTED', 'FAILED', 'CANCELLED'];

type FinishStatus = Extract<RunEvent, { type: 'run.finished' }>['status'];
type Pending = { kind: 'confirm'; case_id: string } | { kind: 'ask'; submit: boolean } | { kind: 'approval'; case_id: string };

interface SessionRec {
  session: Session; messages: ChatMessage[]; pending: Pending | null; stop: (() => void) | null;
  lastCourse: string | null; offered: string | null;
}
interface World {
  profiles: Record<string, Profile>; sections: Record<string, SectionDef>; sessions: Record<string, SessionRec>;
  cases: Record<string, CaseDetail>; notifications: Notification[]; memory: Record<string, MemoryNote[]>;
  seq: { event: number; notif: number; enroll: number; msg: number };
}

// ---------- eligibility (mirrors the team's placeholder rules) ----------

const R = (code: string, n: number, reason: string, nb = false): Reason => ({ code, rule: rule(n, nb), reason });
const seatsLeft = (s: SectionDef) => Math.max(0, s.capacity - s.enrolled);
const sectionsOf = (w: World, course: string) => Object.values(w.sections).filter((s) => s.course_id === course);
const overlaps = (a: SectionDef, b: SectionDef) =>
  [...a.days].some((d) => b.days.includes(d)) && a.start < b.end && b.start < a.end;

function evaluate(w: World, studentId: string, courseId: string): EligibilityVerdict {
  const course = COURSES[courseId];
  const p = w.profiles[studentId];
  if (!course) return { course_id: courseId, sections: [], error: `${courseId} is not in the course catalogue.`, summary: `${courseId}: unknown course.` };
  if (!course.offered) {
    return {
      course_id: courseId, error: null, summary: `${courseId} is not offered in ${TERM}.`,
      sections: [{ offering_id: null, can_submit: false, fe_needed: false, blocking: [R('NOT_OFFERED', 8, `${courseId} is in the catalogue but not offered in ${TERM}.`)], advisory: [], suggestions: [] }],
    };
  }
  const secs = sectionsOf(w, courseId);
  const openSecs = secs.filter((s) => seatsLeft(s) > 0);
  const sections: SectionVerdict[] = secs.map((s) => {
    const blocking: Reason[] = [];
    const advisory: Reason[] = [];
    const already = p.enrollments.find((e) => e.course_id === courseId);
    if (already) blocking.push(R('ALREADY_ENROLLED', 8, `You're already enrolled in ${already.offering_id}; only one section per course is allowed.`));
    if (p.on_probation) blocking.push(R('PROBATION', 5, `Your CGPA is ${p.cgpa.toFixed(1)}, below 2.0, so you're on academic probation.`));
    for (const pre of course.prereqs) {
      if (p.completed.includes(pre)) continue;
      const inProgress = p.enrollments.some((e) => e.course_id === pre);
      blocking.push(inProgress
        ? R('PREREQ_IN_PROGRESS', 2, `Prerequisite ${pre} is in progress this term; it has to be completed first.`)
        : R('PREREQ_MISSING', 2, `Prerequisite ${pre} is not completed.`));
    }
    for (const e of p.enrollments) {
      const es = w.sections[e.offering_id];
      if (es && es.course_id !== courseId && overlaps(es, s)) {
        blocking.push(R('CLASH', 3, `Clashes with ${es.offering_id} (${es.days} ${es.start}-${es.end}).`));
      }
    }
    if (p.credits + course.credits > 20) blocking.push(R('CREDIT_LIMIT', 4, `You're at ${p.credits} credits; adding ${course.credits} would exceed the 20-credit cap.`));
    if (s.min_year && p.year < s.min_year) blocking.push(R('YEAR_RESTRICTION', 6, `This section is for year ${s.min_year} and above; you're in year ${p.year}.`));
    if (s.min_cgpa && p.cgpa < s.min_cgpa) blocking.push(R('CGPA_BELOW_MIN', 6, `This section needs a CGPA of ${s.min_cgpa.toFixed(1)}; yours is ${p.cgpa.toFixed(1)}.`));
    const full = seatsLeft(s) === 0;
    let suggestions: string[] = [];
    if (!full) {
      advisory.push(R('SEATS_AVAILABLE', 1, `${s.offering_id} has ${seatsLeft(s)} open seats. Register normally; no force enrollment needed.`));
    } else {
      if (!s.accepts_fe) blocking.push(R('FE_NOT_ACCEPTED', 7, `The instructor isn't accepting force enrollments for ${s.offering_id}.`));
      else if (s.fe_used >= s.fe_slots) blocking.push(R('FE_CAP_REACHED', 7, `All FE slots for ${s.offering_id} are used (${s.fe_used} of ${s.fe_slots}).`));
      const others = openSecs.filter((o) => o.offering_id !== s.offering_id);
      if (others.length) {
        advisory.push(R('OTHER_SECTION_OPEN', 1, `${others.map((o) => `${o.offering_id} (${seatsLeft(o)} seats)`).join(', ')} has open seats; you could register there normally instead.`));
        suggestions = others.map((o) => o.offering_id);
      }
    }
    return { offering_id: s.offering_id, can_submit: full && blocking.length === 0, fe_needed: full, blocking, advisory, suggestions };
  });
  return { course_id: courseId, sections, error: null, summary: sections.map(sectionSummary).join(' ') };
}

function sectionSummary(sv: SectionVerdict): string {
  const id = sv.offering_id ?? 'Course';
  if (sv.can_submit) return `${id}: can request FE.`;
  if (sv.blocking.length) return `${id}: not eligible (${sv.blocking.map((b) => b.code).join(', ')}).`;
  return `${id}: seats open, register normally.`;
}

// ---------- answer composition ----------

function eligibilityAnswer(w: World, studentId: string, v: EligibilityVerdict): { text: string; offered: string | null } {
  if (v.error) return { text: `I couldn't check that: ${v.error}`, offered: null };
  const p = w.profiles[studentId];
  const parts: string[] = [];
  let offered: string | null = null;
  for (const sv of v.sections) {
    if (!sv.offering_id) {
      parts.push(`**${v.course_id}** is in the catalogue but isn't offered in ${TERM}, so there's nothing to request (${rule(8)}).`);
      continue;
    }
    const sec = w.sections[sv.offering_id];
    const credits = COURSES[sec.course_id]?.credits ?? 3;
    if (sv.can_submit) {
      offered = offered ?? sv.offering_id;
      parts.push(`**${sv.offering_id}** is full, and you pass every rule the checker looked at, so **you can request force enrollment**. Prerequisites are done (${rule(2, true)}), there's no clash (${rule(3)}), and your credits would go from ${p.credits} to ${p.credits + credits}, within the cap (${rule(4)}).`);
    } else if (!sv.blocking.length) {
      parts.push(`**${sv.offering_id}** has ${seatsLeft(sec)} open seats, so you can just register there normally. No force enrollment needed (${rule(1)}).`);
    } else {
      parts.push(`**${sv.offering_id}** — not eligible:\n\n${sv.blocking.map((b) => `- ${b.reason} ${b.rule}`).join('\n')}`);
    }
  }
  if (offered) parts.push(`Want me to submit a force-enrollment request for **${offered}**?`);
  return { text: parts.join('\n\n'), offered };
}

function blockedAnswer(w: World, v: EligibilityVerdict, target: SectionVerdict | undefined, label: string): string {
  if (v.error) return `I couldn't submit a request: ${v.error}`;
  if (!target) return `I couldn't find a section called **${label}** this term, so nothing was submitted.`;
  if (!target.offering_id) return `I didn't submit anything: **${v.course_id}** isn't offered in ${TERM} (${rule(8)}).`;
  if (!target.fe_needed && !target.blocking.length) {
    const sec = w.sections[target.offering_id];
    return `**${target.offering_id}** has ${seatsLeft(sec)} open seats, so you don't need force enrollment. Register for it normally through the portal (${rule(1)}). I didn't create a request.`;
  }
  const alt = target.suggestions.length ? `\n\n${target.suggestions.join(', ')} has open seats if you'd like to register there instead.` : '';
  return `I didn't submit a request for **${target.offering_id}**, because:\n\n${target.blocking.map((b) => `- ${b.reason} ${b.rule}`).join('\n')}\n\nNo case was created.${alt}`;
}

// ---------- run machinery ----------

interface Ctx {
  w: World; rec: SessionRec; studentId: string; usedMemory: boolean;
  emit(ev: RunEvent): void;
  sleep(ms?: number): Promise<void>;
  plan(items: string[]): Promise<void>;
  todo(i: number): Promise<void>;
  doneAll(): Promise<void>;
  begin(name: string, args: Record<string, unknown>, agent?: Step['agent'], parent?: string): string;
  end(id: string, name: string, summary: string, ok?: boolean, result?: unknown): void;
  tool(name: string, args: Record<string, unknown>, summary: string, o?: { agent?: Step['agent']; parent?: string; result?: unknown; ms?: number }): Promise<string>;
  think(text: string): Promise<void>;
  say(text: string): Promise<void>;
  move(cd: CaseDetail, to: CaseState, actor: string, action: string, detail?: Record<string, unknown> | null): void;
  notify(recipient: string, kind: NotificationKind, message: string, caseId: string | null): void;
  remember(cd: CaseDetail, detail: string): void;
  interrupt(i: Interrupt): void;
}

function pushAudit(w: World, cd: CaseDetail, from: CaseState | null, to: CaseState | null, actor: string, action: string, detail: Record<string, unknown> | null, ts = nowIso()): AuditEvent {
  w.seq.event += 1;
  const ev: AuditEvent = { event_id: w.seq.event, case_id: cd.case.case_id, actor, action, from_state: from, to_state: to, timestamp: ts, detail };
  cd.audit.push(ev);
  if (to) { cd.case.state = to; cd.case.updated_at = ts; }
  return ev;
}

function addNotification(w: World, recipient: string, kind: NotificationKind, message: string, caseId: string | null, ts = nowIso(), read = false): Notification {
  w.seq.notif += 1;
  const n: Notification = { notification_id: w.seq.notif, recipient_id: recipient, case_id: caseId, kind, message, created_at: ts, read_at: read ? ts : null };
  w.notifications.push(n);
  return n;
}

function makeNote(cd: CaseDetail, detail: string, date = today()): MemoryNote {
  const c = cd.case;
  return { date, case_id: c.case_id, offering_id: c.offering_id, outcome: c.state, detail, raw: `${date} ${c.case_id}: force enrollment in ${c.offering_id} ${c.state} (${detail}).` };
}

function startRun(w: World, rec: SessionRec, studentId: string, body: (c: Ctx) => Promise<FinishStatus>): RunStream {
  let turn = newTurn();
  const queue: RunEvent[] = [];
  let wake: (() => void) | null = null;
  let finished = false;
  let stopped = false;
  let todos: Todo[] = [];
  let callSeq = 0;

  const push = (ev: RunEvent) => {
    turn = applyRunEvent(turn, ev);
    queue.push(ev);
    const f = wake; wake = null; f?.();
  };
  const emitTodos = () => c.emit({ type: 'todos.updated', todos: todos.map((t) => ({ ...t })) });

  const c: Ctx = {
    w, rec, studentId, usedMemory: false,
    emit(ev) { if (!stopped) push(ev); },
    async sleep(ms = rand(300, 900)) { await wait(ms); if (stopped) throw STOP; },
    async plan(items) {
      const id = c.begin('write_todos', { todos: items });
      await c.sleep(rand(250, 450));
      todos = items.map((content) => ({ content, status: 'pending' }));
      emitTodos();
      c.end(id, 'write_todos', `Planned ${items.length} steps`);
      await c.sleep(150);
    },
    async todo(i) {
      todos = todos.map((t, j) => (j < i ? { ...t, status: 'completed' } : j === i ? { ...t, status: 'in_progress' } : t));
      emitTodos();
      await c.sleep(120);
    },
    async doneAll() {
      todos = todos.map((t) => ({ ...t, status: 'completed' }));
      emitTodos();
      await c.sleep(100);
    },
    begin(name, args, agent = 'main', parent) {
      callSeq += 1;
      const id = `call_${hex8()}${callSeq}`;
      c.emit({ type: 'tool.started', call_id: id, name, args, agent, parent_call_id: parent });
      return id;
    },
    end(id, name, summary, ok = true, result) {
      c.emit({ type: 'tool.finished', call_id: id, name, ok, summary, result });
    },
    async tool(name, args, summary, o = {}) {
      const id = c.begin(name, args, o.agent ?? 'main', o.parent);
      await c.sleep(o.ms ?? rand(300, 900));
      c.end(id, name, summary, true, o.result);
      return id;
    },
    async think(text) {
      for (let i = 0; i < text.length; i += 60) { c.emit({ type: 'reasoning.delta', text: text.slice(i, i + 60) }); await c.sleep(35); }
    },
    async say(text) {
      for (let i = 0; i < text.length; i += 40) { c.emit({ type: 'message.delta', text: text.slice(i, i + 40) }); await c.sleep(55); }
    },
    move(cd, to, actor, action, detail = null) {
      const ev = pushAudit(w, cd, cd.case.state, to, actor, action, detail);
      const owner = w.sessions[cd.case.case_id];
      if (owner) { owner.session.case = clone(cd.case); owner.session.updated_at = cd.case.updated_at; }
      c.emit({ type: 'case.updated', case: clone(cd.case), event: clone(ev) });
    },
    notify(recipient, kind, message, caseId) {
      c.emit({ type: 'notification.created', notification: clone(addNotification(w, recipient, kind, message, caseId)) });
    },
    remember(cd, detail) {
      const note = makeNote(cd, detail);
      (w.memory[cd.case.student_id] ??= []).push(note);
      c.emit({ type: 'memory.updated', student_id: cd.case.student_id, note });
    },
    interrupt(i) {
      rec.session.pending_interrupt = i;
      c.emit({ type: 'interrupt', interrupt: i });
    },
  };

  const finalize = (status: FinishStatus, error?: string) => {
    if (status === 'limit_reached' || status === 'error') {
      push({ type: 'run.finished', status, error: error ?? (status === 'limit_reached' ? 'Recursion limit reached' : 'Unknown error') });
      return;
    }
    const msg: ChatMessage = {
      message_id: `msg_${++w.seq.msg}`, role: 'assistant',
      text: turn.text + (stopped ? `${turn.text ? '\n\n' : ''}_Stopped._` : ''),
      created_at: nowIso(), thinking: turnToThinking(turn),
      verdict: turn.verdict, interrupt: turn.interrupt, used_memory: c.usedMemory || undefined,
    };
    rec.messages.push(msg);
    rec.session.updated_at = msg.created_at;
    push({ type: 'message.completed', message: clone(msg) });
    push({ type: 'run.finished', status });
  };

  rec.stop = () => { stopped = true; };
  void (async () => {
    push({ type: 'run.started', run_id: `run_${hex8()}`, session_id: rec.session.session_id });
    try {
      finalize(await body(c));
    } catch (e) {
      if (e === STOP) finalize('interrupted');
      else finalize('error', e instanceof Error ? e.message : String(e));
    } finally {
      finished = true;
      rec.stop = null;
      // `wake` is assigned inside a closure, which TS narrowing cannot see; widen it explicitly.
      const f = wake as (() => void) | null; wake = null; f?.();
    }
  })();

  async function* events(): AsyncGenerator<RunEvent> {
    for (;;) {
      if (queue.length) { yield queue.shift() as RunEvent; continue; }
      if (finished) return;
      await new Promise<void>((r) => { wake = r; });
    }
  }
  return { events: events(), stop: () => { stopped = true; } };
}

function failedStream(error: string): RunStream {
  async function* gen(): AsyncGenerator<RunEvent> { yield { type: 'run.finished', status: 'error', error }; }
  return { events: gen(), stop: () => undefined };
}

// ---------- scenarios ----------

async function checker(c: Ctx, course: string): Promise<EligibilityVerdict> {
  const description = `Check force-enrollment eligibility for ${c.studentId} in ${course}`;
  const id = c.begin('task', { subagent_type: 'eligibility-checker', description });
  c.emit({ type: 'subagent.started', call_id: id, name: 'eligibility-checker', description });
  await c.sleep(300);
  const secs = sectionsOf(c.w, course);
  const listSummary = secs.length
    ? `${secs.length} section${secs.length > 1 ? 's' : ''}: ${secs.map((s) => `${s.offering_id} (${seatsLeft(s) ? `${seatsLeft(s)} seats open` : 'full'})`).join(', ')}`
    : `No sections of ${course} in ${TERM}`;
  await c.tool('list_sections', { course_id: course }, listSummary, { agent: 'eligibility-checker', parent: id });
  const v = evaluate(c.w, c.studentId, course);
  for (const sv of v.sections) {
    if (sv.offering_id) await c.tool('check_my_eligibility', { offering_id: sv.offering_id }, sectionSummary(sv), { agent: 'eligibility-checker', parent: id, result: sv });
  }
  await c.sleep(250);
  c.emit({ type: 'subagent.finished', call_id: id, verdict: clone(v) });
  c.end(id, 'task', v.summary);
  return v;
}

async function eligibilityFlow(c: Ctx, course: string, resumed = false): Promise<FinishStatus> {
  const items = resumed ? [`Check eligibility for ${course}`, 'Explain the result'] : ['Read the force-enrollment rules', `Check eligibility for ${course}`, 'Explain the result'];
  await c.plan(items);
  let i = 0;
  if (!resumed) {
    await c.todo(i++);
    await c.think(`The student is asking about ${course}. I'll read the force-enrollment skill, then hand the rule checks to the eligibility checker so the verdict is structured and cites rule labels.`);
    await c.tool('read_file', { path: SKILL_PATH }, 'Read rules FE-1 to FE-8 (placeholder v0.1)');
  }
  await c.todo(i++);
  const v = await checker(c, course);
  await c.todo(i);
  const { text, offered } = eligibilityAnswer(c.w, c.studentId, v);
  c.rec.lastCourse = course;
  c.rec.offered = offered;
  await c.say(text);
  await c.doneAll();
  return 'answered';
}

function createCase(c: Ctx, sec: SectionDef): CaseDetail {
  const id = c.rec.session.session_id;
  const ts = nowIso();
  const cd: CaseDetail = {
    case: { case_id: id, student_id: c.studentId, offering_id: sec.offering_id, state: 'DRAFT', next_action: null, flag: null, created_at: ts, updated_at: ts },
    audit: [], approval: null, enrollment: null, instructor_id: sec.instructor_id,
  };
  c.w.cases[id] = cd;
  const ev = pushAudit(c.w, cd, null, 'DRAFT', 'main-agent', 'CASE_CREATED', { offering_id: sec.offering_id }, ts);
  c.rec.session.case = clone(cd.case);
  c.rec.session.title = `${sec.offering_id} force enrollment`;
  c.emit({ type: 'case.updated', case: clone(cd.case), event: clone(ev) });
  return cd;
}

async function submitFlow(c: Ctx, course: string, section: string | null): Promise<FinishStatus> {
  const sid = c.rec.session.session_id;
  const open = Object.values(c.w.cases).find((cd) =>
    cd.case.student_id === c.studentId && !FINAL.includes(cd.case.state) && cd.case.offering_id.startsWith(`${course}-`) && cd.case.case_id !== sid);
  if (open) {
    await c.plan(['Look up your cases', 'Explain']);
    await c.todo(0);
    await c.tool('get_my_cases', {}, `Open case ${open.case.case_id} (${open.case.state})`);
    await c.todo(1);
    await c.say(`You already have an open request for this course: case ${open.case.case_id} (${open.case.state}). I can't open a second one while it's in progress. Open that chat from the sidebar to follow it.`);
    await c.doneAll();
    return 'answered';
  }
  if (c.rec.session.case) {
    await c.say(`This chat already holds case ${c.rec.session.case.case_id} (${c.rec.session.case.state}). One chat holds one request, so start a new chat for another course.`);
    return 'answered';
  }
  await c.plan(['Read the force-enrollment rules', `Check eligibility for ${section ?? course}`, 'Prepare the request for your confirmation']);
  await c.todo(0);
  await c.think(`The student wants to submit a request for ${section ?? course}. Rules first, then a fresh eligibility check. I must not submit anything until the student confirms.`);
  await c.tool('read_file', { path: SKILL_PATH }, 'Read rules FE-1 to FE-8 (placeholder v0.1)');
  await c.todo(1);
  const v = await checker(c, course);
  c.rec.lastCourse = course;
  const target = (section ? v.sections.find((s) => s.offering_id === section) : undefined)
    ?? (section ? undefined : v.sections.find((s) => s.can_submit) ?? v.sections.find((s) => s.fe_needed) ?? v.sections[0]);
  await c.todo(2);
  if (!target || !target.can_submit || !target.offering_id) {
    await c.say(blockedAnswer(c.w, v, target, section ?? course));
    await c.doneAll();
    return 'answered';
  }
  const sec = c.w.sections[target.offering_id];
  const stepId = c.begin('submit_case', { offering_id: sec.offering_id });
  await c.sleep(500);
  const cd = createCase(c, sec);
  await c.sleep(400);
  cd.case.next_action = 'Waiting for the student to confirm';
  c.move(cd, 'AWAITING_CONFIRMATION', 'main-agent', 'CONFIRMATION_REQUESTED', null);
  c.end(stepId, 'submit_case', `Prepared case ${cd.case.case_id}; waiting for your confirmation`);
  await c.doneAll();
  await c.say(`**${sec.offering_id}** is full and you pass the rules, so I've prepared a force-enrollment request. Nothing is sent until you confirm below; then instructor **${sec.instructor_id}** will be asked to approve it.`);
  c.interrupt({ kind: 'confirm_submission', case_id: cd.case.case_id, offering_id: sec.offering_id, description: `Submit a force-enrollment request for ${sec.offering_id}? The instructor will be asked to approve it.` });
  c.rec.pending = { kind: 'confirm', case_id: cd.case.case_id };
  c.rec.offered = null;
  return 'interrupted';
}

async function confirmFlow(c: Ctx, cd: CaseDetail, accept: boolean): Promise<FinishStatus> {
  c.rec.pending = null;
  c.rec.session.pending_interrupt = null;
  const sec = c.w.sections[cd.case.offering_id];
  const id = cd.case.case_id;
  if (!accept) {
    await c.plan(['Cancel the request', 'Save the outcome to memory']);
    await c.todo(0);
    cd.case.next_action = null;
    c.move(cd, 'CANCELLED', c.studentId, 'STUDENT_DECLINED', { reason: 'Student declined at confirmation' });
    await c.todo(1);
    const n = c.begin('save_case_note', { case_id: id });
    await c.sleep();
    c.remember(cd, 'declined by student; nothing submitted');
    c.end(n, 'save_case_note', 'Saved one line to memory');
    await c.say(`Okay, I didn't submit anything. Case ${id} is cancelled and nothing was sent to the instructor. If you change your mind, start a new chat and ask again.`);
    await c.doneAll();
    return 'answered';
  }
  await c.plan(['Re-check eligibility', 'Submit the request', 'Ask the instructor to approve', 'Enroll you once approved']);
  await c.todo(0);
  c.move(cd, 'SUBMITTED', c.studentId, 'STUDENT_CONFIRMED', { via: 'confirmation card' });
  const v = evaluate(c.w, c.studentId, sec.course_id);
  const sv = v.sections.find((s) => s.offering_id === sec.offering_id);
  await c.tool('check_my_eligibility', { offering_id: sec.offering_id }, sv?.can_submit ? 'Still eligible: no blocking rules' : `No longer eligible: ${sv?.blocking.map((b) => b.code).join(', ')}`, { result: sv });
  if (!sv?.can_submit) {
    cd.case.next_action = null;
    c.move(cd, 'CANCELLED', 'main-agent', 'NO_LONGER_ELIGIBLE', { codes: sv?.blocking.map((b) => b.code) ?? [] });
    c.remember(cd, 'no longer eligible at submit');
    await c.say(`I couldn't submit: something changed and you no longer pass the rules.\n\n${sv?.blocking.map((b) => `- ${b.reason} ${b.rule}`).join('\n') ?? ''}`);
    return 'answered';
  }
  await c.todo(1);
  await c.tool('submit_case', { case_id: id }, `Submitted to instructor ${sec.instructor_id}`);
  await c.todo(2);
  const p = c.w.profiles[c.studentId];
  const course = COURSES[sec.course_id];
  cd.case.next_action = `Waiting for ${sec.instructor_id} to approve or reject`;
  c.move(cd, 'AWAITING_APPROVAL', 'system', 'APPROVAL_REQUESTED', {
    instructor_id: sec.instructor_id,
    eligibility: {
      year: p.year, cgpa: p.cgpa, credits_now: p.credits, credits_after: p.credits + course.credits,
      prerequisites: course.prereqs.length ? `${course.prereqs.join(', ')} completed` : 'none',
      timetable: 'no clash', fe_slots: `${sec.fe_used} of ${sec.fe_slots} used`, rules: 'FE-1 to FE-8 passed (placeholder v0.1)',
    },
  });
  c.notify(sec.instructor_id, 'APPROVAL_REQUESTED', `${c.studentId} asks for force enrollment in ${sec.offering_id} (case ${id}).`, id);
  await c.todo(3);
  c.begin('execute_enrollment', { case_id: id });
  await c.sleep(700);
  c.interrupt({ kind: 'waiting_for_instructor', case_id: id, instructor_id: sec.instructor_id, description: `Your request ${id} is with instructor ${sec.instructor_id}.` });
  c.rec.pending = { kind: 'approval', case_id: id };
  await c.say(`Submitted. Your request ${id} for **${sec.offering_id}** is now with instructor **${sec.instructor_id}**. I'll enroll you as soon as they approve, and you'll get a notice either way.`);
  return 'waiting_for_instructor';
}

async function decisionFlow(c: Ctx, cd: CaseDetail, decision: Decision, reason: string | undefined): Promise<FinishStatus> {
  c.rec.pending = null;
  c.rec.session.pending_interrupt = null;
  const sec = c.w.sections[cd.case.offering_id];
  const instr = cd.instructor_id;
  const id = cd.case.case_id;
  const student = cd.case.student_id;
  cd.approval = { instructor_id: instr, decision: decision === 'approve' ? 'APPROVE' : 'REJECT', reason: reason ?? null, created_at: nowIso() };
  if (decision === 'reject') {
    const why = reason?.trim() || 'No reason given';
    await c.plan(['Record the decision', 'Send you a notice', 'Save the outcome to memory']);
    await c.todo(0);
    cd.case.next_action = null;
    c.move(cd, 'REJECTED', instr, 'REJECTED', { reason: why });
    await c.sleep(400);
    await c.todo(1);
    const n = c.begin('notify_student', { kind: 'REJECTED' });
    await c.sleep();
    c.notify(student, 'REJECTED', `Your request ${id} for ${sec.offering_id} was rejected by instructor ${instr}. Reason: ${why}`, id);
    c.end(n, 'notify_student', 'Notice sent');
    await c.todo(2);
    const m = c.begin('save_case_note', { case_id: id });
    await c.sleep();
    c.remember(cd, `rejected by ${instr}; reason: ${why}`);
    c.end(m, 'save_case_note', 'Saved one line to memory');
    await c.say(`Instructor **${instr}** rejected request ${id} for **${sec.offering_id}**.\n\n**Reason:** ${why}\n\nYou weren't enrolled. You can ask me about other sections in a new chat.`);
    await c.doneAll();
    return 'answered';
  }
  await c.plan(['Verify the approval', 'Enroll you', 'Send you a notice', 'Save the outcome to memory']);
  await c.todo(0);
  await c.think(`Instructor ${instr} approved case ${id}. Before enrolling, confirm the decision came from the section owner and that an FE slot is still free.`);
  c.move(cd, 'APPROVED', instr, 'APPROVED', { decision: 'APPROVE' });
  await c.todo(1);
  const ex = c.begin('execute_enrollment', { case_id: id });
  await c.sleep(500);
  c.move(cd, 'EXECUTING', 'main-agent', 'EXECUTION_STARTED', null);
  await c.sleep(800);
  const p = c.w.profiles[student];
  const before = p.credits;
  if (sec.fe_used >= sec.fe_slots) {
    cd.case.flag = 'FE slots ran out before enrollment';
    c.move(cd, 'FAILED', 'system', 'FAILED', { reason: 'FE slots ran out' });
    c.end(ex, 'execute_enrollment', 'Failed: no FE slots left', false);
    c.notify(student, 'FAILED', `Your request ${id} for ${sec.offering_id} failed: no FE slots were left.`, id);
    c.remember(cd, 'failed; FE slots ran out');
    await c.say(`I couldn't enroll you: the FE slots for **${sec.offering_id}** ran out before enrollment (${rule(7)}). The case is flagged for review.`);
    return 'answered';
  }
  const credits = COURSES[sec.course_id]?.credits ?? 3;
  p.enrollments.push({ offering_id: sec.offering_id, course_id: sec.course_id });
  p.credits += credits;
  sec.fe_used += 1;
  sec.enrolled += 1;
  c.w.seq.enroll += 1;
  cd.enrollment = { enrollment_id: c.w.seq.enroll, kind: 'FORCE' };
  cd.case.next_action = null;
  c.move(cd, 'COMPLETED', 'system', 'ENROLLED', { enrollment_id: c.w.seq.enroll, kind: 'FORCE' });
  c.end(ex, 'execute_enrollment', `Approval verified; enrolled in ${sec.offering_id} (FORCE)`);
  await c.todo(2);
  const n = c.begin('notify_student', { kind: 'COMPLETED' });
  await c.sleep();
  c.notify(student, 'COMPLETED', `You're enrolled in ${sec.offering_id}. Request ${id} was approved by instructor ${instr}.`, id);
  c.notify(student, 'AGENT_MESSAGE', `Your credits this term are now ${p.credits}.`, id);
  c.end(n, 'notify_student', '2 notices sent');
  await c.todo(3);
  const m = c.begin('save_case_note', { case_id: id });
  await c.sleep();
  c.remember(cd, `approved by ${instr}; force enrollment`);
  c.end(m, 'save_case_note', 'Saved one line to memory');
  await c.say(`**You're in.** Instructor **${instr}** approved request ${id}, and you're now enrolled in **${sec.offering_id}** (force enrollment). Your credits this term went from ${before} to ${p.credits}.`);
  await c.doneAll();
  return 'answered';
}

async function askFlow(c: Ctx, submit: boolean): Promise<FinishStatus> {
  await c.plan(['Read the force-enrollment rules', 'Work out which course you mean', 'Check eligibility', 'Explain the result']);
  await c.todo(0);
  await c.tool('read_file', { path: SKILL_PATH }, 'Read rules FE-1 to FE-8 (placeholder v0.1)');
  await c.todo(1);
  const description = 'Find the course the student means, then check eligibility';
  const id = c.begin('task', { subagent_type: 'eligibility-checker', description });
  c.emit({ type: 'subagent.started', call_id: id, name: 'eligibility-checker', description });
  await c.sleep(300);
  await c.tool('list_sections', { query: 'machine learning' }, 'Two matches: CS412 Machine Learning, CS582 Advanced Machine Learning', { agent: 'eligibility-checker', parent: id });
  const question = 'Which course code do you mean?';
  c.begin('ask_student', { question }, 'eligibility-checker', id);
  await c.sleep(400);
  c.interrupt({ kind: 'ask_student', question });
  c.rec.pending = { kind: 'ask', submit };
  return 'interrupted';
}

async function answerFlow(c: Ctx, answer: string, submit: boolean): Promise<FinishStatus> {
  const course = parseCourse(answer);
  if (!course) {
    await c.say('I still need a course code, for example **CS412** or **CS582**.');
    c.interrupt({ kind: 'ask_student', question: 'Which course code do you mean?' });
    return 'interrupted';
  }
  c.rec.pending = null;
  c.rec.session.pending_interrupt = null;
  if (!c.rec.session.case) c.rec.session.title = `${course} force enrollment`;
  return submit ? submitFlow(c, course, null) : eligibilityFlow(c, course, true);
}

async function memoryFlow(c: Ctx): Promise<FinishStatus> {
  const notes = c.w.memory[c.studentId] ?? [];
  await c.sleep(500);
  if (!notes.length) {
    await c.say("I don't have any record of a previous request. If you like, I can check a course for you, for example **CS412**.");
    return 'answered';
  }
  c.usedMemory = true;
  const n = notes[notes.length - 1];
  const more = notes.length > 1 ? `\n\nI have ${notes.length} requests on record in total; they're all in the Memory tab.` : '';
  await c.say(`Your last request was ${n.case_id} for **${n.offering_id}**. It ended **${n.outcome}** on ${n.date}: ${n.detail}.${more}`);
  return 'answered';
}

async function profileFlow(c: Ctx): Promise<FinishStatus> {
  const p = c.w.profiles[c.studentId];
  await c.tool('get_my_profile', {}, `Year ${p.year}, CGPA ${p.cgpa.toFixed(1)}, ${p.credits} credits`);
  const list = p.enrollments.map((e) => `- ${e.offering_id} ${COURSES[e.course_id]?.title ?? ''} (${COURSES[e.course_id]?.credits ?? 3} cr)`).join('\n');
  const room = 20 - p.credits;
  const tail = room > 0
    ? `That leaves room for **${room} more** before the 20-credit cap (${rule(4)}).`
    : `You're at the 20-credit cap (${rule(4)}), so you can't add another course, by force enrollment or otherwise.`;
  await c.say(`You're taking **${p.credits} credits** this term across ${p.enrollments.length} course${p.enrollments.length === 1 ? '' : 's'}:\n\n${list}\n\n${tail}`);
  return 'answered';
}

async function loopFlow(c: Ctx): Promise<FinishStatus> {
  await c.plan(['Find the answer']);
  await c.todo(0);
  for (let k = 0; k < 6; k++) {
    await c.tool(k % 2 ? 'list_sections' : 'read_file', k % 2 ? { course_id: 'CS412' } : { path: SKILL_PATH }, 'No new information', { ms: 260 });
  }
  return 'limit_reached';
}

async function genericFlow(c: Ctx): Promise<FinishStatus> {
  await c.sleep(400);
  await c.say("I can help with force enrollment: checking whether you can get into a full section, submitting a request, and following it up with the instructor. Try asking about a course code, like **CS412**.");
  return 'answered';
}

function parseCourse(text: string): string | null {
  const m = /\b(CS|MATH|GEN)\s?-?(\d{3})\b/i.exec(text);
  return m ? `${m[1].toUpperCase()}${m[2]}` : null;
}
function parseSection(text: string, course: string): string | null {
  const m = /\bsection\s*S?(\d)\b/i.exec(text) ?? /\b(?:CS|MATH|GEN)\s?\d{3}\s*-\s*S(\d)\b/i.exec(text);
  return m ? `${course}-S${m[1]}` : null;
}

// ---------- seed world ----------

function seedWorld(): World {
  const w: World = {
    profiles: seedProfiles(),
    sections: Object.fromEntries(SECTIONS.map((s) => [s.offering_id, { ...s }])),
    sessions: {}, cases: {}, notifications: [], memory: {},
    seq: { event: 0, notif: 0, enroll: 100, msg: 0 },
  };
  const st = (name: string, args: Record<string, unknown>, summary: string, extra: Partial<Step> = {}): Step =>
    ({ call_id: `call_${hex8()}`, name, agent: 'main', args, status: 'done', summary, ...extra });
  const sub = (name: string, args: Record<string, unknown>, summary: string): Step => st(name, args, summary, { agent: 'eligibility-checker' });
  const msg = (role: ChatMessage['role'], text: string, created_at: string, extra: Partial<ChatMessage> = {}): ChatMessage =>
    ({ message_id: `msg_${++w.seq.msg}`, role, text, created_at, ...extra });
  const done = (items: string[]): Todo[] => items.map((content) => ({ content, status: 'completed' }));

  function pastCase(o: { case_id: string; student_id: string; offering_id: string; day: string; nextDay: string; decision: 'APPROVE' | 'REJECT'; reason: string | null; refusal?: string }) {
    const sec = w.sections[o.offering_id];
    const t = (d: string, hm: string) => `${d}T${hm}:00.000Z`;
    const cd: CaseDetail = {
      case: { case_id: o.case_id, student_id: o.student_id, offering_id: o.offering_id, state: 'DRAFT', next_action: null, flag: null, created_at: t(o.day, '05:02'), updated_at: t(o.day, '05:02') },
      audit: [], approval: null, enrollment: null, instructor_id: sec.instructor_id,
    };
    pushAudit(w, cd, null, 'DRAFT', 'main-agent', 'CASE_CREATED', { offering_id: o.offering_id }, t(o.day, '05:02'));
    pushAudit(w, cd, 'DRAFT', 'AWAITING_CONFIRMATION', 'main-agent', 'CONFIRMATION_REQUESTED', null, t(o.day, '05:02'));
    pushAudit(w, cd, 'AWAITING_CONFIRMATION', 'SUBMITTED', o.student_id, 'STUDENT_CONFIRMED', { via: 'confirmation card' }, t(o.day, '05:04'));
    pushAudit(w, cd, 'SUBMITTED', 'AWAITING_APPROVAL', 'system', 'APPROVAL_REQUESTED', {
      instructor_id: sec.instructor_id,
      eligibility: { year: w.profiles[o.student_id].year, cgpa: w.profiles[o.student_id].cgpa, rules: 'FE-1 to FE-8 passed (placeholder v0.1)' },
    }, t(o.day, '05:04'));
    if (o.refusal) pushAudit(w, cd, null, null, o.refusal, 'APPROVAL_REFUSED', { reason: `${o.refusal} does not own ${o.offering_id}` }, t(o.day, '09:40'));
    cd.approval = { instructor_id: sec.instructor_id, decision: o.decision, reason: o.reason, created_at: t(o.nextDay, '06:15') };
    let detail: string;
    if (o.decision === 'APPROVE') {
      pushAudit(w, cd, 'AWAITING_APPROVAL', 'APPROVED', sec.instructor_id, 'APPROVED', { decision: 'APPROVE' }, t(o.nextDay, '06:15'));
      pushAudit(w, cd, 'APPROVED', 'EXECUTING', 'main-agent', 'EXECUTION_STARTED', null, t(o.nextDay, '06:15'));
      w.seq.enroll += 1;
      cd.enrollment = { enrollment_id: w.seq.enroll, kind: 'FORCE' };
      pushAudit(w, cd, 'EXECUTING', 'COMPLETED', 'system', 'ENROLLED', { enrollment_id: w.seq.enroll, kind: 'FORCE' }, t(o.nextDay, '06:16'));
      detail = `approved by ${sec.instructor_id}; force enrollment`;
      addNotification(w, o.student_id, 'COMPLETED', `You're enrolled in ${o.offering_id}. Request ${o.case_id} was approved by instructor ${sec.instructor_id}.`, o.case_id, t(o.nextDay, '06:16'), true);
    } else {
      pushAudit(w, cd, 'AWAITING_APPROVAL', 'REJECTED', sec.instructor_id, 'REJECTED', { reason: o.reason }, t(o.nextDay, '06:15'));
      detail = `rejected by ${sec.instructor_id}; reason: ${o.reason}`;
      addNotification(w, o.student_id, 'REJECTED', `Your request ${o.case_id} for ${o.offering_id} was rejected by instructor ${sec.instructor_id}. Reason: ${o.reason}`, o.case_id, t(o.nextDay, '06:15'));
    }
    w.cases[o.case_id] = cd;
    (w.memory[o.student_id] ??= []).push(makeNote(cd, detail, o.nextDay));
    const verdict: EligibilityVerdict = {
      course_id: sec.course_id, error: null, summary: `${o.offering_id}: can request FE.`,
      sections: [{ offering_id: o.offering_id, can_submit: true, fe_needed: true, blocking: [], advisory: [], suggestions: [] }],
    };
    const confirm: Interrupt = { kind: 'confirm_submission', case_id: o.case_id, offering_id: o.offering_id, description: `Submit a force-enrollment request for ${o.offering_id}? The instructor will be asked to approve it.` };
    const waiting: Interrupt = { kind: 'waiting_for_instructor', case_id: o.case_id, instructor_id: sec.instructor_id, description: `Your request ${o.case_id} is with instructor ${sec.instructor_id}.` };
    const final: CaseState[] = o.decision === 'APPROVE' ? ['APPROVED', 'EXECUTING', 'COMPLETED'] : ['REJECTED'];
    const messages: ChatMessage[] = [
      msg('user', `Please submit a force-enrollment request for ${sec.course_id} section ${o.offering_id.split('-')[1]}`, t(o.day, '05:01')),
      msg('assistant', `**${o.offering_id}** is full and you pass the rules, so I've prepared a force-enrollment request. Nothing is sent until you confirm below; then instructor **${sec.instructor_id}** will be asked to approve it.`, t(o.day, '05:02'), {
        verdict, interrupt: confirm,
        thinking: {
          todos: done(['Read the force-enrollment rules', `Check eligibility for ${o.offering_id}`, 'Prepare the request for your confirmation']),
          steps: [
            st('write_todos', { todos: 3 }, 'Planned 3 steps'),
            st('read_file', { path: SKILL_PATH }, 'Read rules FE-1 to FE-8 (placeholder v0.1)'),
            st('task', { subagent_type: 'eligibility-checker' }, verdict.summary, { children: [
              sub('list_sections', { course_id: sec.course_id }, 'Sections listed'),
              sub('check_my_eligibility', { offering_id: o.offering_id }, `${o.offering_id}: can request FE.`),
            ] }),
            st('submit_case', { offering_id: o.offering_id }, `Prepared case ${o.case_id}; waiting for your confirmation`),
          ],
          reasoning: '', duration_ms: 8200, case_states: ['DRAFT', 'AWAITING_CONFIRMATION'],
        },
      }),
      msg('assistant', `Submitted. Your request ${o.case_id} for **${o.offering_id}** is now with instructor **${sec.instructor_id}**. I'll enroll you as soon as they approve, and you'll get a notice either way.`, t(o.day, '05:04'), {
        interrupt: waiting,
        thinking: {
          todos: [...done(['Re-check eligibility', 'Submit the request', 'Ask the instructor to approve']), { content: 'Enroll you once approved', status: 'in_progress' }],
          steps: [
            st('write_todos', { todos: 4 }, 'Planned 4 steps'),
            st('check_my_eligibility', { offering_id: o.offering_id }, 'Still eligible: no blocking rules'),
            st('submit_case', { case_id: o.case_id }, `Submitted to instructor ${sec.instructor_id}`),
            st('execute_enrollment', { case_id: o.case_id }, '', { status: 'paused' }),
          ],
          reasoning: '', duration_ms: 5600, case_states: ['SUBMITTED', 'AWAITING_APPROVAL'],
        },
      }),
      msg('assistant', o.decision === 'APPROVE'
        ? `**You're in.** Instructor **${sec.instructor_id}** approved request ${o.case_id}, and you're now enrolled in **${o.offering_id}** (force enrollment).`
        : `Instructor **${sec.instructor_id}** rejected request ${o.case_id} for **${o.offering_id}**.\n\n**Reason:** ${o.reason}\n\nYou weren't enrolled. You can ask me about other sections in a new chat.`, t(o.nextDay, '06:16'), {
        thinking: {
          todos: done(o.decision === 'APPROVE' ? ['Verify the approval', 'Enroll you', 'Send you a notice', 'Save the outcome to memory'] : ['Record the decision', 'Send you a notice', 'Save the outcome to memory']),
          steps: o.decision === 'APPROVE'
            ? [st('write_todos', { todos: 4 }, 'Planned 4 steps'), st('execute_enrollment', { case_id: o.case_id }, `Approval verified; enrolled in ${o.offering_id} (FORCE)`), st('notify_student', { kind: 'COMPLETED' }, 'Notice sent'), st('save_case_note', { case_id: o.case_id }, 'Saved one line to memory')]
            : [st('write_todos', { todos: 3 }, 'Planned 3 steps'), st('notify_student', { kind: 'REJECTED' }, 'Notice sent'), st('save_case_note', { case_id: o.case_id }, 'Saved one line to memory')],
          reasoning: '', duration_ms: 6100, case_states: final,
        },
      }),
    ];
    w.sessions[o.case_id] = {
      session: { session_id: o.case_id, student_id: o.student_id, title: `${o.offering_id} force enrollment`, created_at: t(o.day, '05:01'), updated_at: t(o.nextDay, '06:16'), case: clone(cd.case), pending_interrupt: null },
      messages, pending: null, stop: null, lastCourse: sec.course_id, offered: null,
    };
  }

  // Spring 2026 so it doesn't block the Fall 2026 happy path for S1.
  pastCase({ case_id: 'FE-0f2144b5', student_id: 'S1', offering_id: 'CS412-S1', day: '2026-02-10', nextDay: '2026-02-11', decision: 'APPROVE', reason: null, refusal: 'I2' });
  pastCase({ case_id: 'FE-7b3e90a2', student_id: 'S2', offering_id: 'CS360-S1', day: '2026-09-02', nextDay: '2026-09-03', decision: 'REJECT', reason: 'The section is at room capacity this term.' });

  // A plain chat (no case) for S1.
  const chatId = 'FE-3c9a1e07';
  const p1 = w.profiles.S1;
  w.sessions[chatId] = {
    session: { session_id: chatId, student_id: 'S1', title: 'How many credits am I taking?', created_at: '2026-10-14T08:20:00.000Z', updated_at: '2026-10-14T08:20:06.000Z', case: null, pending_interrupt: null },
    messages: [
      msg('user', 'How many credits am I taking?', '2026-10-14T08:20:00.000Z'),
      msg('assistant', `You're taking **${p1.credits} credits** this term across ${p1.enrollments.length} courses. That leaves room for **${20 - p1.credits} more** before the 20-credit cap (${rule(4)}).`, '2026-10-14T08:20:06.000Z', {
        thinking: { todos: [], steps: [st('get_my_profile', {}, `Year 4, CGPA 3.4, ${p1.credits} credits`)], reasoning: '', duration_ms: 2100, case_states: [] },
      }),
    ],
    pending: null, stop: null, lastCourse: null, offered: null,
  };
  return w;
}

// ---------- client ----------

export function createMockApi(): ApiClient {
  let w = seedWorld();
  const lag = () => wait(rand(150, 380));
  const findRec = (id: string) => w.sessions[id];

  return {
    mode: 'mock',
    async listStudents() { await lag(); return clone(STUDENTS); },
    async listInstructors() { await lag(); return clone(INSTRUCTORS); },
    async getProfile(id) {
      await lag();
      const p = w.profiles[id];
      if (!p) throw new ApiError(404, `Student ${id} not found`);
      return clone(p);
    },
    async listSessions(id) {
      await lag();
      return clone(Object.values(w.sessions)
        .filter((r) => r.session.student_id === id && (r.messages.length > 0 || r.session.case))
        .map((r) => r.session)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    },
    async listCases(id) {
      await lag();
      return clone(Object.values(w.cases).filter((cd) => cd.case.student_id === id).map((cd) => cd.case)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    },
    async getMemory(id) { await lag(); return { student_id: id, notes: clone(w.memory[id] ?? []) }; },
    async listNotifications(id) {
      await wait(80);
      return clone(w.notifications.filter((n) => n.recipient_id === id).sort((a, b) => b.created_at.localeCompare(a.created_at)));
    },
    async markNotificationsRead(ids) {
      const ts = nowIso();
      for (const n of w.notifications) if (ids.includes(n.notification_id) && !n.read_at) n.read_at = ts;
    },
    async createSession(student_id) {
      await wait(60);
      let id = `FE-${hex8()}`;
      while (w.sessions[id]) id = `FE-${hex8()}`;
      const ts = nowIso();
      const session: Session = { session_id: id, student_id, title: 'New chat', created_at: ts, updated_at: ts, case: null, pending_interrupt: null };
      w.sessions[id] = { session, messages: [], pending: null, stop: null, lastCourse: null, offered: null };
      return clone(session);
    },
    async getMessages(id) {
      await lag();
      const rec = findRec(id);
      if (!rec) throw new ApiError(404, `Session ${id} not found`);
      return clone(rec.messages);
    },
    sendMessage(sessionId, studentId, text) {
      const rec = findRec(sessionId);
      if (!rec || rec.session.student_id !== studentId) return failedStream('This chat was not found for the signed-in student.');
      rec.messages.push({ message_id: `msg_${++w.seq.msg}`, role: 'user', text, created_at: nowIso() });
      rec.session.updated_at = nowIso();
      const course = parseCourse(text);
      const section = course ? parseSection(text, course) : null;
      if (rec.session.title === 'New chat') rec.session.title = course ? `${section ?? course} force enrollment` : text.length > 42 ? `${text.slice(0, 40).trim()}…` : text;
      const t = text.toLowerCase().trim();
      const run = (body: (c: Ctx) => Promise<FinishStatus>) => startRun(w, rec, studentId, body);
      const pending = rec.pending;
      if (pending?.kind === 'ask') return run((c) => answerFlow(c, text, pending.submit));
      if (pending?.kind === 'confirm') return run(async (c) => { await c.say('Please confirm or decline the request above first.'); return 'interrupted'; });
      if (pending?.kind === 'approval') return run(async (c) => { await c.say('This request is with the instructor. Start a new chat for another course.'); return 'waiting_for_instructor'; });
      if (t === '/loop') return run(loopFlow);
      if (/what happened|last request|previous request|my (last|previous)|history/.test(t)) return run(memoryFlow);
      const wantsSubmit = /\bsubmit\b|\bgo ahead\b|\bfile (a|the|my) request\b|^(yes|yeah|yep|sure|ok|okay|please do)\b/.test(t);
      if (!course && /credit|my profile|cgpa|my courses|am i enrolled/.test(t)) return run(profileFlow);
      if (course) {
        rec.lastCourse = course;
        return run((c) => (wantsSubmit ? submitFlow(c, course, section) : eligibilityFlow(c, course)));
      }
      if (wantsSubmit && (rec.offered || rec.lastCourse)) {
        const off = rec.offered;
        const crs = off ? off.split('-')[0] : (rec.lastCourse as string);
        return run((c) => submitFlow(c, crs, off));
      }
      if (/machine learning|\bml\b|course|class|enrol|force/.test(t)) return run((c) => askFlow(c, wantsSubmit));
      return run(genericFlow);
    },
    resume(sessionId, body: ResumeBody) {
      const rec = findRec(sessionId);
      if (!rec || rec.session.student_id !== body.student_id) return failedStream('This chat was not found for the signed-in student.');
      const pending = rec.pending;
      if ('answer' in body) {
        if (pending?.kind !== 'ask') return failedStream('Nothing is waiting for an answer in this chat.');
        rec.messages.push({ message_id: `msg_${++w.seq.msg}`, role: 'user', text: body.answer, created_at: nowIso() });
        return startRun(w, rec, body.student_id, (c) => answerFlow(c, body.answer, pending.submit));
      }
      if (pending?.kind !== 'confirm') return failedStream('Nothing is waiting for a confirmation in this chat.');
      const cd = w.cases[pending.case_id];
      return startRun(w, rec, body.student_id, (c) => confirmFlow(c, cd, body.decision === 'approve'));
    },
    async getCase(id) {
      await wait(rand(90, 200));
      const cd = w.cases[id];
      if (!cd) throw new ApiError(404, `Case ${id} not found`);
      return clone(cd);
    },
    async listPending(id) {
      await lag();
      return clone(Object.values(w.cases).filter((cd) => cd.instructor_id === id && cd.case.state === 'AWAITING_APPROVAL').map((cd) => cd.case));
    },
    async listDecided(id) {
      await lag();
      return clone(Object.values(w.cases).filter((cd) => cd.approval?.instructor_id === id).map((cd) => cd.case)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    },
    async decide(caseId, instructorId, decision, reason): Promise<DecisionResult> {
      await wait(rand(200, 400));
      const cd = w.cases[caseId];
      if (!cd) return { ok: false, status: 404, error: `Case ${caseId} not found` };
      if (cd.case.state !== 'AWAITING_APPROVAL') return { ok: false, status: 409, error: `Case ${caseId} is not waiting for approval (${cd.case.state}).` };
      if (cd.instructor_id !== instructorId) {
        const error = `${instructorId} does not own ${cd.case.offering_id}`;
        pushAudit(w, cd, null, null, instructorId, 'APPROVAL_REFUSED', { reason: error, attempted: decision.toUpperCase() });
        return { ok: false, status: 403, error };
      }
      const rec = w.sessions[caseId];
      return { ok: true, stream: startRun(w, rec, cd.case.student_id, (c) => decisionFlow(c, cd, decision, reason)) };
    },
    async stop(id) { findRec(id)?.stop?.(); },
    resetDemo() { w = seedWorld(); },
  };
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { api, type RunStream } from '../../api/client';
import type { CaseDetail, CaseState, ChatMessage, RunEvent, Session, Step } from '../../api/types';
import { isFinal } from '../../lib/states';
import type { LiveTurn } from '../../lib/turn';
import { useApp } from '../../state/AppContext';
import { useCaseDetail } from '../../state/useCaseDetail';
import { useRun } from '../../state/useRun';
import { laneFromStates, ThinkingPanel, type ThinkingData } from '../thinking/ThinkingPanel';
import { Button } from '../ui/Button';
import { Skeleton } from '../ui/Misc';
import { LogoMark } from '../layout/LogoMark';
import { Composer } from './Composer';
import { EmptyState } from './EmptyState';
import { Markdown } from './Markdown';
import { StatusStrip } from './StatusStrip';
import {
  ConfirmCard, ErrorCard, MemoryChip, OutcomeCard, QuestionCard, VerdictCard, WaitingCard, type Resolved,
} from './cards';

type Item =
  | { kind: 'msg'; key: string; m: ChatMessage }
  | { kind: 'failed'; key: string; turn: LiveTurn; retryText: string | null };

const SEEN_KEY = 'fe-celebrated';
const seen = (): string[] => { try { return JSON.parse(localStorage.getItem(SEEN_KEY) ?? '[]') as string[]; } catch { return []; } };
const markSeen = (id: string) => { localStorage.setItem(SEEN_KEY, JSON.stringify([...seen().slice(-50), id])); };

const codesIn = (text: string) => Array.from(text.matchAll(/\b(?:CS|MATH|GEN)\d{3}\b/g), (m) => m[0]);
const stepTexts = (steps: Step[]): string[] => steps.flatMap((s) => [s.summary ?? '', ...(s.children ? stepTexts(s.children) : [])]);

function resolvedConfirm(detail: CaseDetail | null): Resolved | null {
  const ev = detail?.audit.find((e) => e.action === 'STUDENT_CONFIRMED' || e.action === 'STUDENT_DECLINED');
  if (!ev) return null;
  return { choice: ev.action === 'STUDENT_CONFIRMED' ? 'Confirmed' : 'Declined', at: ev.timestamp };
}

export function ChatView() {
  const app = useApp();
  const { studentId, activeSessionId, sessions, students } = app;
  const [localSession, setLocalSession] = useState<Session | null>(null);
  const session = sessions?.find((s) => s.session_id === activeSessionId)
    ?? (localSession?.session_id === activeSessionId ? localSession : null);
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [celebrateId, setCelebrateId] = useState<string | null>(null);
  const skipLoad = useRef<string | null>(null);
  const { turn, start, stop, running } = useRun();
  const { detail } = useCaseDetail(session?.case?.case_id ?? null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      const msgs = await api.getMessages(id);
      setItems(msgs.map((m) => ({ kind: 'msg', key: m.message_id, m })));
      const last = msgs[msgs.length - 1];
      const lastState = last?.thinking?.case_states.at(-1);
      if (last && lastState === 'COMPLETED' && !seen().includes(last.message_id)) { setCelebrateId(last.message_id); markSeen(last.message_id); }
      stick.current = true;
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not load this chat.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!activeSessionId) { setItems([]); return; }
    if (skipLoad.current === activeSessionId) { skipLoad.current = null; return; }
    void load(activeSessionId);
  }, [activeSessionId, load]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [items, turn]);

  const onEvent = useCallback((sid: string) => (ev: RunEvent, t: LiveTurn) => {
    switch (ev.type) {
      case 'run.started': void app.refreshSessions(); break;
      case 'case.updated': app.patchSession(sid, { case: ev.case }); app.bumpCase(); break;
      case 'interrupt': app.patchSession(sid, { pending_interrupt: ev.interrupt }); break;
      case 'notification.created': app.pushNotification(ev.notification); break;
      case 'memory.updated': app.bumpMemory(); break;
      case 'message.completed':
        setItems((prev) => [...prev, { kind: 'msg', key: t.localId, m: ev.message }]);
        if (ev.message.thinking?.case_states.at(-1) === 'COMPLETED') { setCelebrateId(ev.message.message_id); markSeen(ev.message.message_id); }
        break;
      default: break;
    }
  }, [app]);

  const runStream = useCallback(async (sid: string, stream: RunStream, retryText: string | null) => {
    stick.current = true;
    const t = await start(stream, onEvent(sid));
    if ((t.status === 'limit_reached' || t.status === 'error') && !t.message) {
      setItems((prev) => [...prev, { kind: 'failed', key: t.localId, turn: t, retryText }]);
    }
    void app.refreshSessions();
    void app.refreshNotifications();
    app.bumpCase();
  }, [start, onEvent, app]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || running) return;
    let sid = activeSessionId;
    let sess = session;
    if (!sid) {
      try {
        const s = await api.createSession(studentId);
        sid = s.session_id;
        sess = s;
        skipLoad.current = sid;
        setLocalSession(s);
        app.setActiveSessionId(sid);
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : 'Could not start a chat.');
        return;
      }
    }
    const askPending = sess?.pending_interrupt?.kind === 'ask_student';
    const now = new Date().toISOString();
    setItems((prev) => [...prev, { kind: 'msg', key: `u-${now}`, m: { message_id: `local-${now}`, role: 'user', text: trimmed, created_at: now } }]);
    if (askPending) app.patchSession(sid, { pending_interrupt: null });
    const stream = askPending ? api.resume(sid, { student_id: studentId, answer: trimmed }) : api.sendMessage(sid, studentId, trimmed);
    await runStream(sid, stream, trimmed);
  }, [running, activeSessionId, session, studentId, app, runStream]);

  const answer = useCallback(async (text: string) => {
    if (!activeSessionId || running) return;
    const now = new Date().toISOString();
    setItems((prev) => [...prev, { kind: 'msg', key: `u-${now}`, m: { message_id: `local-${now}`, role: 'user', text, created_at: now } }]);
    app.patchSession(activeSessionId, { pending_interrupt: null });
    await runStream(activeSessionId, api.resume(activeSessionId, { student_id: studentId, answer: text }), null);
  }, [activeSessionId, running, studentId, app, runStream]);

  const confirm = useCallback(async (accept: boolean) => {
    if (!activeSessionId || running) return;
    app.patchSession(activeSessionId, { pending_interrupt: null });
    await runStream(activeSessionId, api.resume(activeSessionId, { student_id: studentId, decision: accept ? 'approve' : 'reject' }), null);
  }, [activeSessionId, running, studentId, app, runStream]);

  const onStop = useCallback(() => {
    if (activeSessionId) void api.stop(activeSessionId);
    stop();
  }, [activeSessionId, stop]);

  const pending = session?.pending_interrupt ?? null;
  const caseState = (detail?.case.state ?? session?.case?.state ?? null) as CaseState | null;
  const waiting = caseState === 'AWAITING_APPROVAL' || pending?.kind === 'waiting_for_instructor';
  const disabledReason = running ? null
    : waiting ? 'This request is with the instructor. Start a new chat for another course.'
      : pending?.kind === 'confirm_submission' ? 'Confirm or decline the request above to continue.'
        : null;

  const allCodes = useMemo(() => {
    const out = new Set<string>();
    for (const it of items) {
      if (it.kind !== 'msg') continue;
      codesIn(it.m.text).forEach((c) => out.add(c));
      stepTexts(it.m.thinking?.steps ?? []).forEach((t) => codesIn(t).forEach((c) => out.add(c)));
    }
    if (turn) stepTexts(turn.steps).forEach((t) => codesIn(t).forEach((c) => out.add(c)));
    return Array.from(out).slice(0, 4);
  }, [items, turn]);

  const lastAssistantIdx = items.reduce((acc, it, i) => (it.kind === 'msg' && it.m.role === 'assistant' ? i : acc), -1);
  const showLive = !!turn && turn.status === 'running' && !turn.message;
  const studentName = students?.find((s) => s.student_id === studentId)?.name ?? studentId;
  const openCase = () => { app.setInspectorTab('case'); app.setInspectorOpen(true); };
  const openMemory = () => { app.setInspectorTab('memory'); app.setInspectorOpen(true); };

  function renderAssistant(key: string, opts: {
    thinking: ThinkingData; text: string; streaming: boolean; m?: ChatMessage; idx: number; live: boolean;
    verdict?: ChatMessage['verdict']; interrupt?: ChatMessage['interrupt']; usedMemory?: boolean;
  }) {
    const finalState = [...opts.thinking.lane].reverse().find((l) => isFinal(l.state))?.state ?? null;
    const isLast = opts.idx === lastAssistantIdx;
    const nextUser = items.slice(opts.idx + 1).find((it) => it.kind === 'msg' && it.m.role === 'user');
    const i = opts.interrupt;
    return (
      <motion.div key={key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }} className="flex gap-3">
        <div className="pt-0.5"><LogoMark size={26} /></div>
        <div className="min-w-0 flex-1" aria-live={opts.live ? 'polite' : undefined}>
          <ThinkingPanel data={opts.thinking} defaultOpen={opts.live} />
          {(opts.text || opts.streaming) && <Markdown text={opts.text} streaming={opts.streaming} />}
          {opts.usedMemory && <MemoryChip onClick={openMemory} />}
          {opts.verdict && <VerdictCard verdict={opts.verdict} onAsk={(t) => void send(t)} disabled={running || !!disabledReason} />}
          {i?.kind === 'confirm_submission' && (
            <ConfirmCard
              interrupt={i}
              active={!opts.live && isLast && pending?.kind === 'confirm_submission' && !running}
              resolved={resolvedConfirm(detail)}
              onChoose={(a) => void confirm(a)}
            />
          )}
          {i?.kind === 'ask_student' && (
            <QuestionCard
              question={i.question}
              active={!opts.live && isLast && pending?.kind === 'ask_student' && !running}
              answered={nextUser && nextUser.kind === 'msg' ? nextUser.m.text : null}
              suggestions={allCodes}
              onAnswer={(t) => void answer(t)}
            />
          )}
          {i?.kind === 'waiting_for_instructor' && (
            <WaitingCard interrupt={i} stillWaiting={caseState === 'AWAITING_APPROVAL'} onOpenCase={openCase} />
          )}
          {finalState && !opts.streaming && (
            <OutcomeCard state={finalState} detail={detail} celebrate={!!opts.m && opts.m.message_id === celebrateId} />
          )}
        </div>
      </motion.div>
    );
  }

  const isEmpty = !activeSessionId || (!loading && items.length === 0 && !showLive);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}
        className="scroll-thin flex min-h-0 flex-1 flex-col overflow-y-auto"
      >
        {loadError ? (
          <div className="mx-auto mt-16 flex max-w-sm flex-col items-center gap-3 px-4 text-center text-sm text-muted">
            <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden />
            {loadError}
            {activeSessionId && <Button size="sm" onClick={() => void load(activeSessionId)}><RotateCcw className="h-3.5 w-3.5" aria-hidden /> Try again</Button>}
          </div>
        ) : loading && items.length === 0 ? (
          <div className="mx-auto w-full max-w-[760px] space-y-6 px-4 py-8" aria-busy="true">
            <Skeleton className="ml-auto h-10 w-2/3 rounded-2xl" />
            <div className="space-y-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /></div>
          </div>
        ) : isEmpty ? (
          <EmptyState name={studentName} onPick={(t) => void send(t)} />
        ) : (
          <div className="mx-auto w-full max-w-[760px] space-y-7 px-4 pb-6 pt-6 sm:pt-8">
            <AnimatePresence initial={false}>
              {items.map((it, idx) => {
                if (it.kind === 'failed') {
                  return (
                    <motion.div key={it.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                      <div className="pt-0.5"><LogoMark size={26} /></div>
                      <div className="min-w-0 flex-1">
                        <ThinkingPanel data={{ todos: it.turn.todos, steps: it.turn.steps, reasoning: it.turn.reasoning, lane: it.turn.lane, running: false, durationMs: (it.turn.finishedAt ?? Date.now()) - it.turn.startedAt }} defaultOpen={false} />
                        <ErrorCard status={it.turn.status} error={it.turn.error} onRetry={it.retryText ? () => void send(it.retryText as string) : null} />
                      </div>
                    </motion.div>
                  );
                }
                const m = it.m;
                if (m.role === 'user') {
                  return (
                    <motion.div key={it.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="flex justify-end">
                      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent-soft px-4 py-2.5 text-[15px] leading-relaxed text-ink">{m.text}</div>
                    </motion.div>
                  );
                }
                const th = m.thinking;
                return renderAssistant(it.key, {
                  idx, live: false, m, text: m.text, streaming: false, verdict: m.verdict, interrupt: m.interrupt, usedMemory: m.used_memory,
                  thinking: { todos: th?.todos ?? [], steps: th?.steps ?? [], reasoning: th?.reasoning ?? '', lane: laneFromStates(th?.case_states ?? []), running: false, durationMs: th?.duration_ms },
                });
              })}
              {showLive && turn && renderAssistant(turn.localId, {
                idx: items.length, live: true, text: turn.text, streaming: !!turn.text,
                verdict: turn.verdict, interrupt: turn.interrupt, usedMemory: turn.usedMemory,
                thinking: { todos: turn.todos, steps: turn.steps, reasoning: turn.reasoning, lane: turn.lane, running: true, startedAt: turn.startedAt },
              })}
            </AnimatePresence>
          </div>
        )}
      </div>
      <div className="mx-auto w-full max-w-[760px] px-4 pb-3 sm:pb-4">
        <StatusStrip turn={turn} caseState={caseState} />
        <Composer
          onSend={(t) => void send(t)}
          onStop={onStop}
          running={running}
          disabledReason={disabledReason}
          placeholder={pending?.kind === 'ask_student' ? "Answer the checker's question…" : undefined}
        />
      </div>
    </div>
  );
}

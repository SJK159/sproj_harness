import { useMemo, useState, type ReactNode } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  AlertTriangle, ArrowRight, Ban, Brain, Check, CheckCircle2, DoorOpen, Hourglass, Info, PanelRight, RotateCcw, Send, X, XCircle,
} from 'lucide-react';
import type { CaseDetail, CaseState, EligibilityVerdict, Interrupt, SectionVerdict } from '../../api/types';
import { cn, fmtTime } from '../../lib/format';
import { Button } from '../ui/Button';
import { CaseId } from '../ui/Misc';
import { renderInline } from './Markdown';
import { RuleChip } from './RuleChip';

const cardMotion = { initial: { opacity: 0, scale: 0.98, y: 4 }, animate: { opacity: 1, scale: 1, y: 0 }, transition: { duration: 0.22, ease: 'easeOut' } } as const;
const card = 'mt-3 rounded-2xl border border-line bg-surface p-4';

// ---------- verdict ----------

function badgeFor(sv: SectionVerdict) {
  if (sv.blocking.length) return { label: 'Not eligible', cls: 'bg-red-100 text-red-800 dark:bg-red-400/15 dark:text-red-200', Icon: XCircle };
  if (sv.can_submit) return { label: 'Can request FE', cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200', Icon: CheckCircle2 };
  return { label: 'No FE needed: seats open', cls: 'bg-sky-100 text-sky-800 dark:bg-sky-400/15 dark:text-sky-200', Icon: DoorOpen };
}

export function VerdictCard({ verdict, onAsk, disabled }: { verdict: EligibilityVerdict; onAsk: (text: string) => void; disabled?: boolean }) {
  return (
    <motion.div {...cardMotion} className={card}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="text-[13px] font-semibold text-navy">Eligibility check · {verdict.course_id}</div>
        <span className="text-[11px] text-faint">by the eligibility checker</span>
      </div>
      {verdict.error && <p className="text-sm text-red-700 dark:text-red-300">{verdict.error}</p>}
      <div className="space-y-3">
        {verdict.sections.map((sv, i) => {
          const b = badgeFor(sv);
          return (
            <div key={sv.offering_id ?? i} className={cn(i > 0 && 'border-t border-line pt-3')}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[13px] font-medium">{sv.offering_id ?? verdict.course_id}</span>
                <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', b.cls)}>
                  <b.Icon aria-hidden className="h-3 w-3" /> {b.label}
                </span>
              </div>
              {sv.blocking.length > 0 && (
                <ul className="mt-2 space-y-1.5">
                  {sv.blocking.map((r, j) => (
                    <li key={j} className="flex items-start gap-2 text-[13.5px] leading-snug">
                      <X aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600 dark:text-red-300" />
                      <span><RuleChip label={r.rule} /> {r.reason} <span className="font-mono text-[11px] text-faint">{r.code}</span></span>
                    </li>
                  ))}
                </ul>
              )}
              {sv.advisory.length > 0 && (
                <ul className="mt-2 space-y-1.5">
                  {sv.advisory.map((r, j) => (
                    <li key={j} className="flex items-start gap-2 text-[13px] leading-snug text-muted">
                      <Info aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-faint" />
                      <span><RuleChip label={r.rule} /> {r.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
              {sv.suggestions.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {sv.suggestions.map((s) => {
                    const [course, sec] = s.split('-');
                    return (
                      <Button key={s} size="sm" disabled={disabled} onClick={() => onAsk(`Can I get into ${course} section ${sec}?`)}>
                        Ask about {s} <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                      </Button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

// ---------- confirm ----------

export interface Resolved { choice: string; at: string }

export function ConfirmCard({ interrupt, active, resolved, onChoose }: {
  interrupt: Extract<Interrupt, { kind: 'confirm_submission' }>; active: boolean; resolved: Resolved | null;
  onChoose: (accept: boolean) => void;
}) {
  const [picked, setPicked] = useState<{ accept: boolean; at: string } | null>(null);
  const locked = !!picked || !!resolved || !active;
  const choice = picked ? (picked.accept ? 'Confirmed' : 'Declined') : resolved?.choice;
  const at = picked?.at ?? resolved?.at;
  const pick = (accept: boolean) => {
    if (locked) return;
    setPicked({ accept, at: new Date().toISOString() });
    onChoose(accept);
  };
  return (
    <motion.div {...cardMotion} className={cn(card, active && !locked && 'border-accent/40 ring-4 ring-accent/10')}>
      <div className="flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><Send aria-hidden className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] leading-snug">
            Submit a force-enrollment request for <strong className="font-semibold">{interrupt.offering_id}</strong>? The instructor will be asked to approve it.
          </p>
          <div className="mt-1 text-[12px] text-faint">Case <CaseId id={interrupt.case_id} /></div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <AnimatePresence mode="popLayout" initial={false}>
              {!locked ? (
                <motion.div key="btns" className="flex gap-2" exit={{ opacity: 0, scale: 0.98 }}>
                  <Button variant="primary" onClick={() => pick(true)}><Check aria-hidden className="h-4 w-4" />Confirm</Button>
                  <Button onClick={() => pick(false)}>Decline</Button>
                </motion.div>
              ) : choice ? (
                <motion.div key="done" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  className={cn('inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-medium',
                    choice === 'Confirmed' ? 'bg-accent-soft text-accent' : 'bg-sunk text-muted')}>
                  {choice === 'Confirmed' ? <Check aria-hidden className="h-4 w-4" /> : <X aria-hidden className="h-4 w-4" />}
                  {choice === 'Confirmed' ? 'You confirmed' : 'You declined'}{at && <span className="font-normal opacity-80">· {fmtTime(at)}</span>}
                </motion.div>
              ) : (
                <motion.span key="closed" className="text-[13px] text-faint">This confirmation is closed.</motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ---------- question ----------

export function QuestionCard({ question, active, answered, suggestions, onAnswer }: {
  question: string; active: boolean; answered: string | null; suggestions: string[]; onAnswer: (text: string) => void;
}) {
  const [value, setValue] = useState('');
  const [sent, setSent] = useState<string | null>(null);
  const done = sent ?? answered;
  const submit = (text: string) => {
    const t = text.trim();
    if (!t || done || !active) return;
    setSent(t);
    onAnswer(t);
  };
  return (
    <motion.div {...cardMotion} className={cn(card, active && !done && 'border-accent/40 ring-4 ring-accent/10')}>
      <div className="text-[12px] font-medium text-faint">The eligibility checker asks:</div>
      <p className="mt-0.5 text-[15px] font-medium">{question}</p>
      {done ? (
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-sunk px-2.5 py-1 text-[13px] text-muted">
          <Check aria-hidden className="h-3.5 w-3.5" /> Answered: <span className="font-medium text-ink">{done}</span>
        </div>
      ) : active ? (
        <>
          {suggestions.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {suggestions.map((s) => <Button key={s} size="sm" onClick={() => submit(s)}><span className="font-mono">{s}</span></Button>)}
            </div>
          )}
          <form className="mt-2.5 flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(value); }}>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Type a course code"
              aria-label="Your answer"
              className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-canvas px-3 text-sm outline-none placeholder:text-faint focus:border-accent"
            />
            <Button type="submit" variant="primary" disabled={!value.trim()}>Send</Button>
          </form>
        </>
      ) : (
        <div className="mt-2 text-[13px] text-faint">No longer waiting for an answer.</div>
      )}
    </motion.div>
  );
}

// ---------- waiting ----------

export function WaitingCard({ interrupt, stillWaiting, onOpenCase }: {
  interrupt: Extract<Interrupt, { kind: 'waiting_for_instructor' }>; stillWaiting: boolean; onOpenCase: () => void;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div {...cardMotion} className={cn(card, 'bg-amber-50/60 dark:bg-amber-400/[0.06]', !stillWaiting && 'opacity-80')}>
      <div className="flex items-start gap-3">
        <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-200">
          {stillWaiting && !reduce && <motion.span aria-hidden className="absolute inset-0 rounded-xl bg-amber-300/40" animate={{ scale: [1, 1.35], opacity: [0.6, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut' }} />}
          <motion.span animate={stillWaiting && !reduce ? { rotate: [0, 0, 180, 180] } : undefined} transition={{ duration: 3, repeat: Infinity, times: [0, 0.45, 0.55, 1] }}>
            <Hourglass aria-hidden className="h-4 w-4" />
          </motion.span>
        </span>
        <div className="min-w-0 flex-1 text-[14.5px] leading-snug">
          {stillWaiting ? (
            <p>Your request <CaseId id={interrupt.case_id} /> is with instructor <strong className="font-semibold">{interrupt.instructor_id}</strong>. You can close this chat; you'll get a notice when they decide.</p>
          ) : (
            <p className="text-muted">Request <CaseId id={interrupt.case_id} /> was with instructor {interrupt.instructor_id}. They've decided; see below.</p>
          )}
          <button type="button" onClick={onOpenCase} className="mt-2 inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">
            <PanelRight aria-hidden className="h-3.5 w-3.5" /> View case
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// ---------- outcome ----------

function Burst() {
  const dots = useMemo(() => Array.from({ length: 10 }, (_, i) => ({ a: (i / 10) * Math.PI * 2, d: 26 + (i % 3) * 8 })), []);
  return (
    <span aria-hidden className="pointer-events-none absolute inset-0">
      {dots.map((p, i) => (
        <motion.span
          key={i}
          className={cn('absolute left-1/2 top-1/2 -ml-[3px] -mt-[3px] h-1.5 w-1.5 rounded-full', i % 2 ? 'bg-emerald-500' : 'bg-accent')}
          initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
          animate={{ x: Math.cos(p.a) * p.d, y: Math.sin(p.a) * p.d, opacity: 0, scale: 0.4 }}
          transition={{ duration: 0.9, ease: 'easeOut', delay: 0.25 }}
        />
      ))}
    </span>
  );
}

function DrawnCheck({ animate }: { animate: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <motion.path d="M5 12.5l4.5 4.5L19 7.5" initial={animate ? { pathLength: 0 } : false} animate={{ pathLength: 1 }} transition={{ duration: 0.45, ease: 'easeOut', delay: 0.1 }} />
    </svg>
  );
}

export function OutcomeCard({ state, detail, celebrate }: { state: CaseState; detail: CaseDetail | null; celebrate: boolean }) {
  const reduce = useReducedMotion();
  const party = celebrate && !reduce;
  const c = detail?.case;
  const off = c?.offering_id ?? 'the section';
  let tone = 'border-line';
  let icon = <Ban aria-hidden className="h-5 w-5" />;
  let iconCls = 'bg-slate-100 text-slate-600 dark:bg-slate-400/15 dark:text-slate-200';
  let title = '';
  let body: ReactNode = null;
  if (state === 'COMPLETED') {
    tone = 'border-emerald-200 dark:border-emerald-400/25';
    iconCls = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-200';
    icon = <DrawnCheck animate={party} />;
    title = `You're enrolled in ${off}`;
    body = <>{detail?.enrollment?.kind === 'FORCE' ? 'Force enrollment' : detail?.enrollment?.kind === 'REGULAR' ? 'Regular enrollment' : 'Enrollment'}{detail?.approval ? ` · approved by ${detail.approval.instructor_id}` : ''}</>;
  } else if (state === 'REJECTED') {
    tone = 'border-red-200 dark:border-red-400/25';
    iconCls = 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-200';
    icon = <XCircle aria-hidden className="h-5 w-5" />;
    title = 'Request rejected';
    body = <>Instructor {detail?.approval?.instructor_id ?? detail?.instructor_id}{detail?.approval?.reason ? <>: “{detail.approval.reason}”</> : ''}</>;
  } else if (state === 'FAILED') {
    tone = 'border-red-200 dark:border-red-400/25';
    iconCls = 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-200';
    icon = <AlertTriangle aria-hidden className="h-5 w-5" />;
    title = 'Request failed';
    const ev = detail?.audit.slice().reverse().find((e) => e.to_state === 'FAILED');
    const reason = ev?.detail && typeof ev.detail.reason === 'string' ? ev.detail.reason : c?.flag;
    body = <>{reason ?? 'The enrollment could not be completed.'}{c?.flag && <span className="mt-1 block font-medium text-red-700 dark:text-red-300">Flagged for review: {c.flag}</span>}</>;
  } else {
    title = 'Request cancelled';
    body = 'Nothing was submitted to the instructor.';
  }
  return (
    <motion.div {...cardMotion} className={cn(card, tone)}>
      <div className="flex items-center gap-3">
        <span className={cn('relative grid h-10 w-10 shrink-0 place-items-center rounded-xl', iconCls)}>
          {icon}
          {party && state === 'COMPLETED' && <Burst />}
        </span>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold">{title}</div>
          <div className="text-[13px] text-muted">{body}</div>
        </div>
      </div>
    </motion.div>
  );
}

// ---------- error / memory ----------

export function ErrorCard({ status, error, onRetry }: { status: string; error?: string; onRetry: (() => void) | null }) {
  const limit = status === 'limit_reached';
  return (
    <motion.div {...cardMotion} className={cn(card, 'border-red-200 dark:border-red-400/25')}>
      <div className="flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-200"><AlertTriangle aria-hidden className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[14.5px]">{limit ? 'The assistant stopped to avoid a loop. Try rephrasing.' : 'Something went wrong while the assistant was working.'}</p>
          {error && <p className="mt-0.5 text-[12.5px] text-faint">{renderInline(error)}</p>}
          {onRetry && <Button size="sm" className="mt-2.5" onClick={onRetry}><RotateCcw aria-hidden className="h-3.5 w-3.5" /> Retry</Button>}
        </div>
      </div>
    </motion.div>
  );
}

export function MemoryChip({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[12px] font-medium text-muted hover:border-accent/40 hover:text-accent">
      <Brain aria-hidden className="h-3.5 w-3.5" /> From your memory
    </button>
  );
}

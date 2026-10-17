import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, ChevronRight, Info } from 'lucide-react';
import type { AuditEvent, CaseDetail, CaseState } from '../../api/types';
import { cn, fmtDateTime } from '../../lib/format';
import { MAIN_PATH, stateMeta, TONE_DOT } from '../../lib/states';
import { humanize } from '../../lib/turn';
import { StatePill } from '../ui/StatePill';
import { Tooltip } from '../ui/Tooltip';

const ENDING_HINT: Partial<Record<CaseState, CaseState>> = { AWAITING_CONFIRMATION: 'CANCELLED', AWAITING_APPROVAL: 'REJECTED', EXECUTING: 'FAILED' };
const SIDE: CaseState[] = ['CANCELLED', 'REJECTED', 'FAILED'];

/** Vertical stepper of the main path with side endings branching off where they happened. */
export function StateTracker({ detail }: { detail: CaseDetail }) {
  const state = detail.case.state;
  const ending = SIDE.includes(state);
  const branchFrom = ending
    ? ([...detail.audit].reverse().find((e) => e.to_state === state)?.from_state ?? 'AWAITING_APPROVAL')
    : null;
  const reached = ending ? MAIN_PATH.indexOf(branchFrom as CaseState) : MAIN_PATH.indexOf(state);
  const completed = state === 'COMPLETED';

  return (
    <ol className="relative">
      {MAIN_PATH.map((s, i) => {
        const done = i < reached || (i === reached && (ending || completed));
        const current = i === reached && !ending && !completed;
        const future = i > reached;
        const m = stateMeta(s);
        const Icon = m.icon;
        const hint = ENDING_HINT[s];
        const isLast = i === MAIN_PATH.length - 1;
        return (
          <li key={s}>
            <div className="relative flex gap-3 pb-1">
              <div className="relative flex w-7 flex-col items-center">
                <motion.span
                  layout
                  className={cn(
                    'relative z-10 grid h-7 w-7 place-items-center rounded-full border text-[11px] transition-colors duration-300',
                    done ? 'border-accent bg-accent text-accent-ink'
                      : current ? 'border-accent bg-accent-soft text-accent'
                        : 'border-line bg-surface text-faint',
                  )}
                >
                  {done ? <Check aria-hidden className="h-3.5 w-3.5" /> : <Icon aria-hidden className="h-3.5 w-3.5" />}
                  {current && (
                    <motion.span aria-hidden className="absolute inset-0 rounded-full border-2 border-accent"
                      animate={{ scale: [1, 1.45], opacity: [0.55, 0] }} transition={{ duration: 1.6, repeat: Infinity, ease: 'easeOut' }} />
                  )}
                </motion.span>
                {!isLast && (
                  <span className="relative w-[2px] flex-1 overflow-hidden rounded bg-line" style={{ minHeight: 18 }}>
                    <motion.span
                      className="absolute inset-0 origin-top bg-accent"
                      initial={false}
                      animate={{ scaleY: i < reached ? 1 : 0 }}
                      transition={{ duration: 0.35, ease: 'easeOut', delay: i < reached ? i * 0.05 : 0 }}
                    />
                  </span>
                )}
              </div>
              <div className={cn('min-w-0 flex-1 pb-3 pt-1', future && 'opacity-55')}>
                <div className="flex items-center gap-2">
                  <span className={cn('text-[13.5px]', current ? 'font-semibold text-ink' : done ? 'text-ink' : 'text-muted')}>{m.label}</span>
                  {current && <span className="rounded-full bg-accent-soft px-1.5 py-[1px] text-[10.5px] font-semibold uppercase tracking-wide text-accent">Now</span>}
                </div>
                <div className="font-mono text-[10.5px] text-faint">{s}</div>
                {hint && !ending && !completed && i >= reached && (
                  <div className="mt-0.5 text-[11.5px] text-faint">or ends as {stateMeta(hint).label.toLowerCase()}</div>
                )}
                {ending && i === reached && (
                  <motion.div initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className="mt-2 flex items-center gap-2">
                    <span className="h-px w-4 bg-line" aria-hidden />
                    <StatePill state={state} size="md" />
                  </motion.div>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const isRefusal = (a: string) => a.endsWith('_REFUSED');

export function AuditTrail({ events }: { events: AuditEvent[] }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5">
        <h3 className="text-[12px] font-semibold uppercase tracking-[0.06em] text-faint">Audit trail</h3>
        <Tooltip content="Every change to a case is recorded and can't be edited." align="start" side="bottom">
          <span tabIndex={0} aria-label="About the audit trail" className="text-faint"><Info className="h-3.5 w-3.5" /></span>
        </Tooltip>
      </div>
      <ol className="space-y-1.5">
        <AnimatePresence initial={false}>
          {events.map((e, i) => <AuditRow key={e.event_id} e={e} delay={Math.min(i, 8) * 0.03} />)}
        </AnimatePresence>
      </ol>
    </div>
  );
}

function AuditRow({ e, delay }: { e: AuditEvent; delay: number }) {
  const [open, setOpen] = useState(false);
  const refusal = isRefusal(e.action);
  const tone = e.to_state ? stateMeta(e.to_state).tone : 'neutral';
  const entries = Object.entries(e.detail ?? {});
  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay }}
      className={cn('rounded-xl border px-2.5 py-2', refusal ? 'border-red-200 bg-red-50/70 dark:border-red-400/25 dark:bg-red-400/[0.06]' : 'border-line bg-surface')}
    >
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} disabled={!entries.length} className="flex w-full items-start gap-2 text-left">
        <span className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full', refusal ? 'bg-red-500' : TONE_DOT[tone])} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-1.5">
            <span className={cn('text-[13px] font-medium', refusal ? 'text-red-800 dark:text-red-200' : 'text-ink')}>{humanize(e.action)}</span>
            <span className="text-[12px] text-faint">by <span className="font-mono">{e.actor}</span></span>
          </span>
          {(e.from_state || e.to_state) && (
            <span className="mt-1 flex flex-wrap items-center gap-1 font-mono text-[10.5px] text-faint">
              {e.from_state ?? '∅'} <span aria-hidden>→</span> <span className="text-muted">{e.to_state ?? '∅'}</span>
            </span>
          )}
          <span className="mt-0.5 block text-[11.5px] tabular-nums text-faint">{fmtDateTime(e.timestamp)}</span>
        </span>
        {entries.length > 0 && <ChevronRight aria-hidden className={cn('mt-0.5 h-3.5 w-3.5 shrink-0 text-faint transition-transform', open && 'rotate-90')} />}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <dl className="ml-4 mt-1.5 space-y-0.5 border-t border-line pt-1.5 font-mono text-[11px]">
              {entries.map(([k, v]) => (
                <div key={k} className="flex gap-1.5 break-all"><dt className="shrink-0 text-faint">{k}:</dt><dd className="text-muted">{typeof v === 'string' ? v : JSON.stringify(v)}</dd></div>
              ))}
            </dl>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

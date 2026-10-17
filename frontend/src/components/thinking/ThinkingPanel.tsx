import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Circle, Hourglass, Loader2, Sparkles } from 'lucide-react';
import type { CaseState, Step, Todo } from '../../api/types';
import { cn, seconds } from '../../lib/format';
import { useNow } from '../../lib/hooks';
import { countSteps, type LaneEntry } from '../../lib/turn';
import { StatePill } from '../ui/StatePill';
import { stepIcon, stepTitle } from './stepMeta';

export interface ThinkingData {
  todos: Todo[]; steps: Step[]; reasoning: string;
  lane: Array<{ state: CaseState; label?: string }>;
  running: boolean; startedAt?: number; durationMs?: number;
}

const spring = { type: 'spring', stiffness: 400, damping: 30 } as const;
const slideIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.22, ease: 'easeOut' } } as const;

export function ThinkingPanel({ data, defaultOpen }: { data: ThinkingData; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const now = useNow(data.running, 500);
  useEffect(() => { if (!data.running) setOpen(false); }, [data.running]);
  useEffect(() => { if (data.running) setOpen(true); }, [data.running]);

  const elapsed = data.running ? now - (data.startedAt ?? now) : data.durationMs ?? 0;
  const n = countSteps(data.steps);
  const last = data.lane.length ? data.lane[data.lane.length - 1].state : null;
  const empty = !data.todos.length && !data.steps.length && !data.reasoning && !data.lane.length;
  if (empty && !data.running) return null;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group -ml-1.5 inline-flex max-w-full items-center gap-1.5 rounded-lg px-1.5 py-1 text-[13px] text-faint hover:bg-sunk hover:text-muted"
      >
        {data.running ? (
          <>
            <Sparkles aria-hidden className="h-3.5 w-3.5 text-accent" />
            <span className="shimmer-text font-medium">Thinking…</span>
            <span className="tabular-nums">{seconds(elapsed)}</span>
          </>
        ) : (
          <span className="truncate">
            Thought for {seconds(elapsed)} · {n} step{n === 1 ? '' : 's'}
            {last && <> · case <span className="font-mono text-[12px]">{last}</span></>}
          </span>
        )}
        <ChevronDown aria-hidden className={cn('h-3.5 w-3.5 shrink-0 transition-transform', open ? 'rotate-0' : '-rotate-90')} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="mt-1.5 space-y-3 rounded-2xl border border-line bg-surface/70 p-3.5">
              {data.lane.length > 0 && <CaseLane lane={data.lane} />}
              {data.todos.length > 0 && <PlanList todos={data.todos} />}
              {data.steps.length > 0 && <StepList steps={data.steps} />}
              {data.reasoning && <Reasoning text={data.reasoning} running={data.running} />}
              {empty && <div className="text-[13px] text-faint">Starting…</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CaseLane({ lane }: { lane: Array<{ state: CaseState; label?: string }> }) {
  const cur = lane[lane.length - 1];
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line pb-3 text-[13px]">
      <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-faint">Case</span>
      <StatePill state={cur.state} />
      <AnimatePresence mode="wait" initial={false}>
        {cur.label && (
          <motion.span key={`${cur.state}-${cur.label}`} {...slideIn} exit={{ opacity: 0 }} className="text-muted">
            {cur.label}
          </motion.span>
        )}
      </AnimatePresence>
      {lane.length > 1 && (
        <span className="ml-auto hidden font-mono text-[11px] text-faint sm:inline">
          {lane.map((l) => l.state).join(' → ')}
        </span>
      )}
    </div>
  );
}

function PlanList({ todos }: { todos: Todo[] }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-faint">Plan</div>
      <ul className="space-y-1">
        {todos.map((t, i) => (
          <motion.li key={`${i}-${t.content}`} {...slideIn} className="flex items-start gap-2 text-[13.5px]">
            <span className="mt-[3px] grid h-4 w-4 shrink-0 place-items-center">
              <AnimatePresence mode="wait" initial={false}>
                <motion.span key={t.status} initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.4, opacity: 0 }} transition={spring}>
                  {t.status === 'completed' ? <CheckCircle2 className="h-4 w-4 text-accent" aria-label="Done" />
                    : t.status === 'in_progress' ? <Loader2 className="h-4 w-4 animate-spin text-accent" aria-label="In progress" />
                      : <Circle className="h-4 w-4 text-line" aria-label="Pending" />}
                </motion.span>
              </AnimatePresence>
            </span>
            <span className={cn(t.status === 'completed' ? 'text-faint' : t.status === 'in_progress' ? 'text-ink' : 'text-muted')}>{t.content}</span>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

function StepList({ steps, nested = false }: { steps: Step[]; nested?: boolean }) {
  return (
    <div>
      {!nested && <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-faint">Steps</div>}
      <ul className="space-y-0.5">
        {steps.map((s) => <StepRow key={s.call_id} step={s} />)}
      </ul>
    </div>
  );
}

function StatusIcon({ status }: { status: Step['status'] }) {
  if (status === 'running') return <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" aria-label="Running" />;
  if (status === 'paused') return <Hourglass className="h-3.5 w-3.5 text-amber-600 dark:text-amber-300" aria-label="Paused" />;
  if (status === 'error') return <AlertCircle className="h-3.5 w-3.5 text-red-600 dark:text-red-300" aria-label="Error" />;
  return (
    <motion.span initial={{ scale: 0.5 }} animate={{ scale: 1 }} transition={spring}>
      <CheckCircle2 className="h-3.5 w-3.5 text-faint" aria-label="Done" />
    </motion.span>
  );
}

function StepRow({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const Icon = stepIcon(step);
  const isGroup = step.children !== undefined;
  const args = Object.entries(step.args ?? {});
  return (
    <motion.li {...slideIn}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-[13.5px] hover:bg-sunk"
      >
        <span className={cn('grid h-6 w-6 shrink-0 place-items-center rounded-md', step.status === 'running' ? 'bg-accent-soft text-accent' : 'bg-sunk text-muted')}>
          <Icon aria-hidden className="h-3.5 w-3.5" />
        </span>
        <span className={cn('min-w-0 flex-1 truncate', step.status === 'running' ? 'text-ink' : 'text-muted')}>{stepTitle(step)}</span>
        <StatusIcon status={step.status} />
        <ChevronRight aria-hidden className={cn('h-3.5 w-3.5 shrink-0 text-faint transition-transform', open && 'rotate-90')} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mb-1.5 ml-9 mt-0.5 space-y-1 rounded-lg bg-sunk px-2.5 py-2 text-[12px] text-muted">
              <div><span className="text-faint">tool</span> <span className="font-mono">{step.name}</span>{step.agent !== 'main' && <span className="text-faint"> · {step.agent}</span>}</div>
              {args.length > 0 && (
                <div className="font-mono text-[11.5px] leading-relaxed">
                  {args.map(([k, v]) => (
                    <div key={k} className="break-all"><span className="text-faint">{k}:</span> {typeof v === 'string' ? v : JSON.stringify(v)}</div>
                  ))}
                </div>
              )}
              {step.summary && <div><span className="text-faint">result</span> {step.summary}</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {isGroup && (
        <AnimatePresence initial={false}>
          {(step.children?.length ?? 0) > 0 && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} className="overflow-hidden">
              <div className="ml-[18px] border-l border-line pl-3">
                <div className="pb-0.5 pt-1 text-[11px] text-faint">Eligibility checker</div>
                <StepList steps={step.children ?? []} nested />
                {step.status === 'done' && step.summary && (
                  <motion.div {...slideIn} className="my-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12.5px] text-muted">
                    <span className="font-medium text-ink">Verdict: </span>{step.summary}
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      )}
    </motion.li>
  );
}

function Reasoning({ text, running }: { text: string; running: boolean }) {
  const [open, setOpen] = useState(running);
  return (
    <div className="border-t border-line pt-2.5">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-faint hover:text-muted">
        Reasoning <ChevronRight aria-hidden className={cn('h-3 w-3 transition-transform', open && 'rotate-90')} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.p initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden whitespace-pre-wrap pt-1 text-[12.5px] italic leading-relaxed text-faint">
            {text}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

export function laneFromStates(states: CaseState[]): LaneEntry[] {
  return states.map((state) => ({ state, label: '' }));
}

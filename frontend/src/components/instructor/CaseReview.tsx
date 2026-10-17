import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, ArrowLeft, Check, ShieldX, X } from 'lucide-react';
import { api, type Decision } from '../../api/client';
import type { RunEvent } from '../../api/types';
import { isFinal } from '../../lib/states';
import { useApp } from '../../state/AppContext';
import { useCaseDetail } from '../../state/useCaseDetail';
import { useRun } from '../../state/useRun';
import { AuditTrail, StateTracker } from '../cases/CaseParts';
import { Markdown } from '../chat/Markdown';
import { OutcomeCard } from '../chat/cards';
import { StatusStrip } from '../chat/StatusStrip';
import { LogoMark } from '../layout/LogoMark';
import { ThinkingPanel } from '../thinking/ThinkingPanel';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { CaseId, Skeleton } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';

export function CaseReview({ caseId }: { caseId: string }) {
  const app = useApp();
  const { detail, error } = useCaseDetail(caseId);
  const { turn, start, running } = useRun();
  const [busy, setBusy] = useState<Decision | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');

  const decide = async (decision: Decision, why?: string) => {
    setBusy(decision);
    setRefusal(null);
    try {
      const res = await api.decide(caseId, app.instructorId, decision, why);
      if (!res.ok) { setRefusal(res.error); app.bumpCase(); return; }
      await start(res.stream, (ev: RunEvent) => {
        if (ev.type === 'case.updated') app.bumpCase();
        if (ev.type === 'notification.created') app.pushNotification(ev.notification);
      });
      app.bumpCase();
    } catch (e) {
      setRefusal(e instanceof Error ? e.message : 'The decision could not be sent.');
    } finally {
      setBusy(null);
    }
  };

  if (error && !detail) {
    return (
      <div className="mx-auto mt-16 max-w-sm px-4 text-center text-[14px] text-muted">
        <AlertTriangle className="mx-auto mb-2 h-5 w-5 text-red-600" aria-hidden />{error}
        <div className="mt-3"><Button size="sm" onClick={() => app.setReviewCaseId(null)}><ArrowLeft className="h-3.5 w-3.5" aria-hidden />Back</Button></div>
      </div>
    );
  }
  if (!detail) {
    return <div className="mx-auto w-full max-w-[760px] space-y-3 px-4 py-8"><Skeleton className="h-7 w-1/2" /><Skeleton className="h-28 w-full rounded-2xl" /><Skeleton className="h-48 w-full rounded-2xl" /></div>;
  }

  const c = detail.case;
  const waiting = c.state === 'AWAITING_APPROVAL';
  const elig = detail.audit.find((e) => e.action === 'APPROVAL_REQUESTED')?.detail?.eligibility;
  const facts = elig && typeof elig === 'object' ? Object.entries(elig as Record<string, unknown>) : [];
  const owner = detail.instructor_id === app.instructorId;

  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[1100px] px-4 py-6 sm:px-6">
        <button type="button" onClick={() => app.setReviewCaseId(null)} className="mb-4 inline-flex items-center gap-1 text-[13px] text-faint hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Waiting for you
        </button>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="font-mono text-[22px] font-semibold tracking-tight text-navy">{c.offering_id}</h1>
              <StatePill state={c.state} size="md" />
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 text-[13px] text-muted">
              <span>Student <span className="font-mono text-ink">{c.student_id}</span></span>
              <span>Case <CaseId id={c.case_id} copy /></span>
              <span>Section owner <span className="font-mono text-ink">{detail.instructor_id}</span>{!owner && <span className="text-faint"> (not you)</span>}</span>
            </div>
          </div>
          {waiting && !turn && (
            <div className="flex gap-2">
              <Button variant="danger" disabled={!!busy} onClick={() => { setReason(''); setRejectOpen(true); }}><X className="h-4 w-4" aria-hidden />Reject</Button>
              <Button variant="primary" disabled={!!busy} onClick={() => void decide('approve')}>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span key={busy === 'approve' ? 'b' : 'i'} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} className="inline-flex"><Check className="h-4 w-4" aria-hidden /></motion.span>
                </AnimatePresence>
                {busy === 'approve' ? 'Approving…' : 'Approve'}
              </Button>
            </div>
          )}
        </div>

        <AnimatePresence>
          {refusal && (
            <motion.div role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="mt-4 flex items-start gap-2.5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[14px] text-red-800 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-200">
              <ShieldX className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <div><span className="font-medium">Refused: {refusal}.</span> The case is still waiting for its section owner, and the attempt was recorded in the audit trail.</div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-6">
            <section className="rounded-2xl border border-line bg-surface p-4">
              <h2 className="text-[13px] font-semibold text-navy">Eligibility at submission</h2>
              {facts.length ? (
                <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-1.5 text-[13.5px]">
                  {facts.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-faint">{k.replace(/_/g, ' ')}</dt>
                      <dd className="tabular-nums">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
              ) : <p className="mt-2 text-[13px] text-faint">Not recorded yet.</p>}
              <p className="mt-3 text-[12px] text-faint">Rules are placeholders (v0.1) written by the team, not official LUMS policy.</p>
            </section>

            {turn && (
              <section>
                <h2 className="mb-3 text-[13px] font-semibold text-navy">Resumed agent run <span className="font-normal text-faint">· as the student will see it</span></h2>
                <div className="flex gap-3">
                  <div className="pt-0.5"><LogoMark size={26} /></div>
                  <div className="min-w-0 flex-1" aria-live="polite">
                    <ThinkingPanel
                      data={{ todos: turn.todos, steps: turn.steps, reasoning: turn.reasoning, lane: turn.lane, running, startedAt: turn.startedAt, durationMs: (turn.finishedAt ?? Date.now()) - turn.startedAt }}
                      defaultOpen
                    />
                    {turn.text && <Markdown text={turn.text} streaming={running} />}
                    {!running && isFinal(c.state) && <OutcomeCard state={c.state} detail={detail} celebrate={c.state === 'COMPLETED'} />}
                  </div>
                </div>
                <div className="mt-3"><StatusStrip turn={turn} caseState={c.state} /></div>
              </section>
            )}

            {!turn && isFinal(c.state) && <OutcomeCard state={c.state} detail={detail} celebrate={false} />}
            <AuditTrail events={detail.audit} />
          </div>
          <aside className="h-fit rounded-2xl border border-line bg-surface p-4">
            <h2 className="mb-3 text-[13px] font-semibold text-navy">Case progress</h2>
            <StateTracker detail={detail} />
          </aside>
        </div>
      </div>

      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} title={`Reject ${c.offering_id} for ${c.student_id}?`}>
        <form onSubmit={(e) => { e.preventDefault(); if (!reason.trim()) return; setRejectOpen(false); void decide('reject', reason.trim()); }}>
          <label className="block text-[13px] text-muted" htmlFor="reject-reason">Reason (the student will see this)</label>
          <textarea id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} required
            className="mt-1.5 w-full resize-none rounded-xl border border-line bg-canvas px-3 py-2 text-[14px] outline-none focus:border-accent/60"
            placeholder="e.g. The section is at room capacity this term." />
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={() => setRejectOpen(false)}>Cancel</Button>
            <Button type="submit" variant="danger" disabled={!reason.trim()}>Reject request</Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

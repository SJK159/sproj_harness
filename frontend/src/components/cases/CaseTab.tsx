import type { ReactNode } from 'react';
import { AlertTriangle, FolderOpen } from 'lucide-react';
import { fmtDateTime } from '../../lib/format';
import { isFinal } from '../../lib/states';
import { useApp } from '../../state/AppContext';
import { useCaseDetail } from '../../state/useCaseDetail';
import { OutcomeCard } from '../chat/cards';
import { CaseId, Skeleton } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';
import { AuditTrail, StateTracker } from './CaseParts';

export function CaseTab() {
  const { sessions, activeSessionId } = useApp();
  const session = sessions?.find((s) => s.session_id === activeSessionId);
  const caseId = session?.case?.case_id ?? null;
  const { detail, error } = useCaseDetail(caseId);

  if (!caseId) {
    return (
      <div className="flex flex-col items-center px-6 py-14 text-center">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-sunk text-faint"><FolderOpen className="h-5 w-5" aria-hidden /></span>
        <p className="mt-3 text-[14px] font-medium">No case yet</p>
        <p className="mt-1 max-w-[260px] text-[13px] leading-relaxed text-muted">A case is created when you ask the assistant to submit a request; nothing is sent until you confirm.</p>
      </div>
    );
  }
  if (error && !detail) return <div className="p-4 text-[13px] text-red-700 dark:text-red-300">{error}</div>;
  if (!detail) {
    return (
      <div className="space-y-3 p-4" aria-busy="true">
        <Skeleton className="h-5 w-1/2" />
        {Array.from({ length: 6 }, (_, i) => <div key={i} className="flex items-center gap-3"><Skeleton className="h-7 w-7 rounded-full" /><Skeleton className="h-3.5 w-1/3" /></div>)}
      </div>
    );
  }
  const c = detail.case;
  const facts: Array<[string, ReactNode]> = [
    ['Case id', <CaseId key="id" id={c.case_id} copy />],
    ['Section', <span key="s" className="font-mono text-[12.5px]">{c.offering_id}</span>],
    ['Instructor', <span key="i" className="font-mono text-[12.5px]">{detail.instructor_id}</span>],
    ['Created', fmtDateTime(c.created_at)],
    ['Updated', fmtDateTime(c.updated_at)],
    ['Next action', c.next_action ?? '—'],
  ];
  return (
    <div className="space-y-5 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-navy">Case progress</h2>
        <StatePill state={c.state} size="md" />
      </div>
      {c.flag && (
        <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-800 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-200">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" /> Flagged for review: {c.flag}
        </div>
      )}
      <StateTracker detail={detail} />
      {isFinal(c.state) && <div className="-mt-3"><OutcomeCard state={c.state} detail={detail} celebrate={false} /></div>}
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 rounded-2xl border border-line bg-surface p-3.5 text-[13px]">
        {facts.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-faint">{k}</dt>
            <dd className="min-w-0 break-words text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      <AuditTrail events={detail.audit} />
    </div>
  );
}

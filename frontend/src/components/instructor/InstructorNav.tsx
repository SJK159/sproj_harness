import { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { api } from '../../api/client';
import type { Case } from '../../api/types';
import { cn, relTime } from '../../lib/format';
import { useApp } from '../../state/AppContext';
import { SectionLabel, SkeletonList } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';

export function useInstructorCases() {
  const { instructorId, caseVersion } = useApp();
  const [pending, setPending] = useState<Case[] | null>(null);
  const [decided, setDecided] = useState<Case[] | null>(null);
  useEffect(() => {
    let alive = true;
    void api.listPending(instructorId).then((p) => alive && setPending(p)).catch(() => alive && setPending([]));
    void api.listDecided(instructorId).then((d) => alive && setDecided(d)).catch(() => alive && setDecided([]));
    return () => { alive = false; };
  }, [instructorId, caseVersion]);
  return { pending, decided };
}

export function CaseRow({ c, active, onClick }: { c: Case; active?: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-current={active ? 'page' : undefined}
      className={cn('w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface', active && 'bg-surface ring-1 ring-line')}>
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] font-medium">{c.offering_id}</span>
        <StatePill state={c.state} size="xs" />
      </div>
      <div className="mt-0.5 text-[11.5px] tabular-nums text-faint">{c.student_id} · {relTime(c.updated_at)}</div>
    </button>
  );
}

export function InstructorNav() {
  const { reviewCaseId, setReviewCaseId } = useApp();
  const { pending, decided } = useInstructorCases();
  const [q, setQ] = useState('');
  return (
    <>
      <form
        className="flex gap-1.5 px-3 pb-2"
        onSubmit={(e) => { e.preventDefault(); const id = q.trim(); if (id) { setReviewCaseId(id); setQ(''); } }}
      >
        <label className="min-w-0 flex-1">
          <span className="sr-only">Open a case by id</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Open case by id, e.g. FE-…"
            className="h-8 w-full rounded-lg border border-line bg-surface px-2.5 font-mono text-[12.5px] outline-none placeholder:font-sans placeholder:text-faint focus:border-accent/60" />
        </label>
        <button type="submit" aria-label="Open case" className="grid h-8 w-8 place-items-center rounded-lg border border-line bg-surface text-muted hover:bg-sunk"><ArrowRight className="h-3.5 w-3.5" /></button>
      </form>
      <nav className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-label="Cases">
        <SectionLabel>Waiting for you</SectionLabel>
        {pending === null ? <SkeletonList rows={2} /> : pending.length === 0
          ? <div className="px-2.5 py-2 text-[12.5px] text-faint">Nothing waiting.</div>
          : <ul className="space-y-0.5">{pending.map((c) => <li key={c.case_id}><CaseRow c={c} active={c.case_id === reviewCaseId} onClick={() => setReviewCaseId(c.case_id)} /></li>)}</ul>}
        <SectionLabel>Decided</SectionLabel>
        {decided === null ? <SkeletonList rows={2} /> : decided.length === 0
          ? <div className="px-2.5 py-2 text-[12.5px] text-faint">No decisions yet.</div>
          : <ul className="space-y-0.5">{decided.map((c) => <li key={c.case_id}><CaseRow c={c} active={c.case_id === reviewCaseId} onClick={() => setReviewCaseId(c.case_id)} /></li>)}</ul>}
      </nav>
    </>
  );
}

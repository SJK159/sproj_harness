import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Brain, Lock } from 'lucide-react';
import { api } from '../../api/client';
import type { Memory } from '../../api/types';
import { fmtDate } from '../../lib/format';
import { useApp } from '../../state/AppContext';
import { SkeletonList } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';

export function MemoryTab() {
  const { studentId, memoryVersion, openSession } = useApp();
  const [mem, setMem] = useState<Memory | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api.getMemory(studentId).then((m) => alive && setMem(m)).catch((e: unknown) => alive && setErr(e instanceof Error ? e.message : 'Could not load memory'));
    return () => { alive = false; };
  }, [studentId, memoryVersion]);

  return (
    <div className="space-y-4 p-4">
      <div>
        <h2 className="text-[15px] font-semibold text-navy">What the assistant remembers about you</h2>
        <p className="mt-1.5 flex items-start gap-2 rounded-xl bg-sunk px-3 py-2 text-[12.5px] leading-relaxed text-muted">
          <Lock aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Written by the system from your case records. You can't edit these, and neither can the assistant.
        </p>
      </div>
      {err && !mem ? <div className="text-[13px] text-red-700 dark:text-red-300">{err}</div>
        : !mem || mem.student_id !== studentId ? <SkeletonList rows={3} />
          : mem.notes.length === 0 ? (
            <div className="flex flex-col items-center px-4 py-10 text-center">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-sunk text-faint"><Brain className="h-5 w-5" aria-hidden /></span>
              <p className="mt-3 text-[14px] font-medium">Nothing remembered yet</p>
              <p className="mt-1 max-w-[240px] text-[13px] text-muted">When a request finishes, one line about it is saved here.</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {[...mem.notes].reverse().map((n, i) => (
                <motion.li key={`${n.case_id}-${n.date}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                  className="rounded-2xl border border-line bg-surface p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] tabular-nums text-faint">{fmtDate(n.date)}</span>
                    <StatePill state={n.outcome} size="xs" />
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[13.5px]">
                    <button type="button" onClick={() => openSession(n.case_id, { inspector: 'case' })} className="font-mono text-[12.5px] text-accent hover:underline">{n.case_id}</button>
                    <span className="font-mono text-[12.5px] text-muted">{n.offering_id}</span>
                  </div>
                  <p className="mt-1 text-[13px] text-muted">{n.detail}</p>
                  <p className="mt-2 border-t border-line pt-2 font-mono text-[10.5px] leading-relaxed text-faint" title="Raw note">{n.raw}</p>
                </motion.li>
              ))}
            </ul>
          )}
    </div>
  );
}

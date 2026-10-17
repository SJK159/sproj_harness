import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { FolderOpen, LayoutGrid, List } from 'lucide-react';
import { api } from '../../api/client';
import type { Case, MemoryNote } from '../../api/types';
import { relTime } from '../../lib/format';
import { BOARD_GROUPS, boardGroup, isFinal } from '../../lib/states';
import { useApp } from '../../state/AppContext';
import { Segmented } from '../ui/Segmented';
import { Skeleton } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';

export function CasesPage() {
  const { studentId, openSession, caseVersion } = useApp();
  const [mode, setMode] = useState<'list' | 'board'>('list');
  const [cases, setCases] = useState<Case[] | null>(null);
  const [notes, setNotes] = useState<MemoryNote[]>([]);
  useEffect(() => {
    let alive = true;
    void Promise.all([api.listCases(studentId), api.getMemory(studentId)])
      .then(([c, m]) => { if (alive) { setCases(c); setNotes(m.notes); } })
      .catch(() => alive && setCases([]));
    return () => { alive = false; };
  }, [studentId, caseVersion]);

  const outcome = (c: Case) => (isFinal(c.state) ? notes.find((n) => n.case_id === c.case_id)?.detail ?? '—' : '—');
  const open = (c: Case) => openSession(c.case_id, { inspector: 'case' });

  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[1100px] px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight text-navy">All my cases</h1>
            <p className="mt-0.5 text-[13.5px] text-muted">Every force-enrollment request you've made. Open one to see its full history.</p>
          </div>
          <Segmented
            id="cases-mode"
            label="View"
            value={mode}
            onChange={setMode}
            className="w-[200px]"
            options={[
              { value: 'list', label: <><List className="h-3.5 w-3.5" aria-hidden />List</> },
              { value: 'board', label: <><LayoutGrid className="h-3.5 w-3.5" aria-hidden />Board</> },
            ]}
          />
        </div>

        {cases === null ? (
          <div className="mt-6 space-y-2" aria-busy="true">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-12 w-full rounded-xl" />)}</div>
        ) : cases.length === 0 ? (
          <div className="mt-16 flex flex-col items-center text-center">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-sunk text-faint"><FolderOpen className="h-5 w-5" aria-hidden /></span>
            <p className="mt-3 text-[15px] font-medium">No cases yet</p>
            <p className="mt-1 text-[13.5px] text-muted">Ask the assistant about a full course to get started.</p>
          </div>
        ) : (
          <AnimatePresence mode="wait" initial={false}>
            {mode === 'list' ? (
              <motion.div key="list" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-6 overflow-x-auto rounded-2xl border border-line bg-surface">
                <table className="w-full min-w-[640px] text-left text-[13.5px]">
                  <thead className="border-b border-line text-[12px] text-faint">
                    <tr><th className="px-4 py-2.5 font-medium">Case</th><th className="px-4 py-2.5 font-medium">Section</th><th className="px-4 py-2.5 font-medium">State</th><th className="px-4 py-2.5 font-medium">Updated</th><th className="px-4 py-2.5 font-medium">Outcome</th></tr>
                  </thead>
                  <tbody>
                    {cases.map((c) => (
                      <tr key={c.case_id} onClick={() => open(c)} className="cursor-pointer border-t border-line first:border-t-0 hover:bg-sunk/60">
                        <td className="px-4 py-3"><button type="button" onClick={(e) => { e.stopPropagation(); open(c); }} className="font-mono text-[12.5px] text-accent hover:underline">{c.case_id}</button></td>
                        <td className="px-4 py-3 font-mono text-[12.5px]">{c.offering_id}</td>
                        <td className="px-4 py-3"><StatePill state={c.state} size="xs" /></td>
                        <td className="px-4 py-3 tabular-nums text-muted">{relTime(c.updated_at)}</td>
                        <td className="px-4 py-3 text-muted">{outcome(c)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </motion.div>
            ) : (
              <motion.div key="board" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {BOARD_GROUPS.map((g) => {
                  const list = cases.filter((c) => boardGroup(c.state) === g);
                  return (
                    <section key={g} className="flex min-h-[160px] flex-col rounded-2xl bg-sunk/70 p-2.5" aria-label={g}>
                      <div className="flex items-center justify-between px-1.5 pb-2 pt-0.5">
                        <h2 className="text-[12.5px] font-semibold text-muted">{g}</h2>
                        <span className="text-[12px] tabular-nums text-faint">{list.length}</span>
                      </div>
                      <div className="space-y-2">
                        {list.map((c) => (
                          <motion.button key={c.case_id} layout type="button" onClick={() => open(c)} whileTap={{ scale: 0.98 }}
                            className="w-full rounded-xl border border-line bg-surface p-3 text-left transition-shadow hover:shadow-sm">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-mono text-[12.5px] font-medium">{c.offering_id}</span>
                              <StatePill state={c.state} size="xs" />
                            </div>
                            <div className="mt-1.5 font-mono text-[11.5px] text-faint">{c.case_id}</div>
                            <div className="mt-1 text-[12px] text-muted">{isFinal(c.state) ? outcome(c) : c.next_action ?? relTime(c.updated_at)}</div>
                          </motion.button>
                        ))}
                        {list.length === 0 && <div className="px-1.5 py-4 text-center text-[12px] text-faint">None</div>}
                      </div>
                    </section>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}

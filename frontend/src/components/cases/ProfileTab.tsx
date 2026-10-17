import { useEffect, useState, type ReactNode } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { api } from '../../api/client';
import type { Profile } from '../../api/types';
import { cn } from '../../lib/format';
import { useApp } from '../../state/AppContext';
import { Skeleton } from '../ui/Misc';

export function ProfileTab() {
  const { studentId, caseVersion } = useApp();
  const [p, setP] = useState<Profile | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api.getProfile(studentId).then((x) => alive && setP(x)).catch((e: unknown) => alive && setErr(e instanceof Error ? e.message : 'Could not load profile'));
    return () => { alive = false; };
  }, [studentId, caseVersion]);

  if (err && !p) return <div className="p-4 text-[13px] text-red-700 dark:text-red-300">{err}</div>;
  if (!p || p.student_id !== studentId) {
    return (
      <div className="space-y-4 p-4" aria-busy="true">
        <Skeleton className="h-5 w-1/2" />
        <div className="grid grid-cols-2 gap-2"><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
        <Skeleton className="h-14" />
        <Skeleton className="h-20" />
      </div>
    );
  }
  const pct = Math.min(100, (p.credits / 20) * 100);
  const atCap = p.credits >= 20;
  return (
    <div className="space-y-4 p-4">
      <div>
        <h2 className="text-[15px] font-semibold text-navy">{p.name}</h2>
        <div className="text-[12.5px] text-faint"><span className="font-mono">{p.student_id}</span> · {p.program}</div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Year" value={String(p.year)} />
        <Stat label="CGPA" value={p.cgpa.toFixed(2)} badge={p.on_probation ? 'Probation' : undefined} />
      </div>
      <div className="rounded-2xl border border-line bg-surface p-3.5">
        <div className="flex items-baseline justify-between text-[13px]">
          <span className="text-faint">Credits this term</span>
          <span className="tabular-nums"><span className="text-[17px] font-semibold text-ink">{p.credits}</span><span className="text-faint"> / 20 cap</span></span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-sunk" role="progressbar" aria-valuemin={0} aria-valuemax={20} aria-valuenow={p.credits} aria-label="Credits against the 20-credit cap">
          <motion.div className={cn('h-full rounded-full', atCap ? 'bg-amber-500' : 'bg-accent')} initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5, ease: 'easeOut' }} />
        </div>
        {atCap && <div className="mt-1.5 text-[12px] text-amber-700 dark:text-amber-300">At the cap: no more courses this term.</div>}
      </div>
      <Group title="Current enrollments">
        {p.enrollments.length ? p.enrollments.map((e) => <Chip key={e.offering_id}>{e.offering_id}</Chip>) : <span className="text-[13px] text-faint">None</span>}
      </Group>
      <Group title="Completed courses">
        {p.completed.length ? p.completed.map((c) => <Chip key={c} soft>{c}</Chip>) : <span className="text-[13px] text-faint">None</span>}
      </Group>
    </div>
  );
}

function Stat({ label, value, badge }: { label: string; value: string; badge?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-3">
      <div className="text-[12px] text-faint">{label}</div>
      <div className="mt-0.5 flex items-center gap-2">
        <span className="text-[19px] font-semibold tabular-nums">{value}</span>
        {badge && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-1.5 py-[1px] text-[11px] font-medium text-red-800 dark:bg-red-400/15 dark:text-red-200">
            <AlertTriangle aria-hidden className="h-3 w-3" />{badge}
          </span>
        )}
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-1.5 text-[12px] font-semibold uppercase tracking-[0.06em] text-faint">{title}</h3>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Chip({ children, soft }: { children: ReactNode; soft?: boolean }) {
  return <span className={cn('rounded-lg px-2 py-0.5 font-mono text-[12px]', soft ? 'bg-sunk text-muted' : 'border border-line bg-surface text-ink')}>{children}</span>;
}

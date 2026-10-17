import { useState, type ReactNode } from 'react';
import { Check, Copy, Database } from 'lucide-react';
import { cn } from '../../lib/format';

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded-md bg-line/60', className)} />;
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="space-y-1.5">
          <Skeleton className="h-3.5 w-4/5" />
          <Skeleton className="h-2.5 w-1/3" />
        </div>
      ))}
    </div>
  );
}

export function SyntheticBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] text-faint" title="All people, courses and cases are synthetic">
      <Database aria-hidden className="h-3 w-3" /> Synthetic demo data
    </span>
  );
}

export function CaseId({ id, copy = false, className }: { id: string; copy?: boolean; className?: string }) {
  const [done, setDone] = useState(false);
  const text = <span className={cn('font-mono text-[12.5px] tabular-nums tracking-tight', className)}>{id}</span>;
  if (!copy) return text;
  return (
    <button
      type="button"
      onClick={() => { void navigator.clipboard?.writeText(id); setDone(true); window.setTimeout(() => setDone(false), 1200); }}
      className="inline-flex items-center gap-1.5 rounded-md px-1 -mx-1 hover:bg-sunk"
      aria-label={`Copy case id ${id}`}
    >
      {text}
      {done ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5 text-faint" />}
    </button>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="px-2 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-faint">{children}</div>;
}

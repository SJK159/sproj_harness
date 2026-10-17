import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/format';

interface Props<T extends string> {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; aria?: string }[];
  id: string; className?: string; label: string;
}

/** Segmented control / tabs with a sliding highlight. */
export function Segmented<T extends string>({ value, onChange, options, id, className, label }: Props<T>) {
  return (
    <div role="tablist" aria-label={label} className={cn('relative flex gap-0.5 rounded-lg bg-sunk p-0.5', className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={o.aria}
            onClick={() => onChange(o.value)}
            className={cn('relative flex-1 rounded-md px-2.5 py-1 text-[13px] font-medium transition-colors', active ? 'text-ink' : 'text-faint hover:text-muted')}
          >
            {active && (
              <motion.span layoutId={`seg-${id}`} className="absolute inset-0 rounded-md bg-surface shadow-sm ring-1 ring-line" transition={{ type: 'spring', stiffness: 400, damping: 32 }} />
            )}
            <span className="relative z-10 inline-flex items-center justify-center gap-1.5">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

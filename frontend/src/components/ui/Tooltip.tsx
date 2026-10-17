import { useId, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '../../lib/format';

interface Props {
  content: ReactNode; children: ReactNode;
  side?: 'top' | 'bottom'; align?: 'start' | 'center' | 'end'; className?: string;
}

export function Tooltip({ content, children, side = 'top', align = 'center', className }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className={cn('relative inline-flex', className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      aria-describedby={open ? id : undefined}
    >
      {children}
      <AnimatePresence>
        {open && (
          <motion.span
            role="tooltip"
            id={id}
            initial={{ opacity: 0, y: side === 'top' ? 4 : -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            style={align === 'center' ? { x: '-50%' } : undefined}
            className={cn(
              'pointer-events-none absolute z-50 w-max max-w-[280px] whitespace-normal rounded-lg bg-ink px-2.5 py-1.5 text-left text-xs font-normal leading-snug text-canvas shadow-lg',
              side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5',
              align === 'center' ? 'left-1/2' : align === 'start' ? 'left-0' : 'right-0',
            )}
          >
            {content}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

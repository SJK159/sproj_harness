import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '../../lib/format';
import { stateMeta, TONE_CLASSES } from '../../lib/states';

interface Props { state: string; size?: 'xs' | 'sm' | 'md'; raw?: boolean; className?: string }

/** Coloured state pill with an icon (never colour alone). Morphs width and label when `state` changes. */
export function StatePill({ state, size = 'sm', raw = false, className }: Props) {
  const m = stateMeta(state);
  const Icon = m.icon;
  return (
    <motion.span
      layout
      title={state}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className={cn(
        'inline-flex items-center gap-1 overflow-hidden whitespace-nowrap rounded-full font-medium transition-colors duration-300',
        TONE_CLASSES[m.tone],
        size === 'xs' ? 'px-1.5 py-[1px] text-[11px]' : size === 'md' ? 'px-2.5 py-1 text-[13px]' : 'px-2 py-0.5 text-xs',
        className,
      )}
    >
      <Icon aria-hidden className={size === 'md' ? 'h-3.5 w-3.5' : 'h-3 w-3'} />
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={state}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.18 }}
          className={raw ? 'font-mono tracking-tight' : undefined}
        >
          {raw ? state : m.label}
        </motion.span>
      </AnimatePresence>
    </motion.span>
  );
}

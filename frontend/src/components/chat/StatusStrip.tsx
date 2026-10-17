import { AnimatePresence, motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { seconds } from '../../lib/format';
import { useNow } from '../../lib/hooks';
import type { LiveTurn } from '../../lib/turn';
import { currentActivity } from '../thinking/stepMeta';
import { StatePill } from '../ui/StatePill';

/** Live strip above the composer while a run is active: step · state · elapsed. */
export function StatusStrip({ turn, caseState }: { turn: LiveTurn | null; caseState: string | null }) {
  const running = turn?.status === 'running';
  const now = useNow(running, 500);
  const laneState = turn?.lane.length ? turn.lane[turn.lane.length - 1].state : null;
  const state = laneState ?? caseState;
  return (
    <div aria-live="polite" className="min-h-[28px]">
      <AnimatePresence>
        {running && turn && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="mb-2 flex items-center gap-2 text-[13px] text-muted"
          >
            <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin text-accent" />
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={currentActivity(turn)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }} className="truncate">
                {currentActivity(turn)}
              </motion.span>
            </AnimatePresence>
            {state && <><span className="text-faint">·</span><StatePill state={state} size="xs" raw /></>}
            <span className="text-faint">·</span>
            <span className="tabular-nums text-faint">{seconds(now - turn.startedAt)}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

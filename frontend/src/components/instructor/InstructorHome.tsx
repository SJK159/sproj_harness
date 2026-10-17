import { motion } from 'framer-motion';
import { Inbox } from 'lucide-react';
import { useApp } from '../../state/AppContext';
import { Skeleton } from '../ui/Misc';
import { StatePill } from '../ui/StatePill';
import { useInstructorCases } from './InstructorNav';
import { relTime } from '../../lib/format';

export function InstructorHome() {
  const { instructors, instructorId, setReviewCaseId } = useApp();
  const { pending } = useInstructorCases();
  const me = instructors?.find((i) => i.instructor_id === instructorId);
  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[760px] px-4 py-8">
        <h1 className="text-[24px] font-semibold tracking-tight text-navy">Waiting for you</h1>
        <p className="mt-1 text-[14px] text-muted">
          {me ? <>Force-enrollment requests for your sections: <span className="font-mono text-[13px]">{me.sections.join(', ')}</span>.</> : 'Force-enrollment requests for your sections.'}
          {' '}You can approve or reject; nothing else.
        </p>
        <div className="mt-6 space-y-2">
          {pending === null ? Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-[72px] w-full rounded-2xl" />)
            : pending.length === 0 ? (
              <div className="flex flex-col items-center rounded-2xl border border-dashed border-line px-6 py-12 text-center">
                <Inbox className="h-6 w-6 text-faint" aria-hidden />
                <p className="mt-3 text-[14.5px] font-medium">Nothing waiting</p>
                <p className="mt-1 max-w-[340px] text-[13px] text-muted">When a student confirms a request for one of your sections, it appears here. To see a refusal, open another instructor's case by id from the sidebar.</p>
              </div>
            ) : pending.map((c, i) => (
              <motion.button key={c.case_id} type="button" onClick={() => setReviewCaseId(c.case_id)}
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} whileTap={{ scale: 0.99 }}
                className="flex w-full items-center gap-4 rounded-2xl border border-line bg-surface p-4 text-left hover:border-accent/40">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[14px] font-semibold">{c.offering_id}</span>
                    <StatePill state={c.state} size="xs" />
                  </div>
                  <div className="mt-1 text-[13px] text-muted">Student <span className="font-mono">{c.student_id}</span> · case <span className="font-mono">{c.case_id}</span> · {relTime(c.updated_at)}</div>
                </div>
                <span className="text-[13px] font-medium text-accent">Review</span>
              </motion.button>
            ))}
        </div>
      </div>
    </div>
  );
}

import { motion } from 'framer-motion';
import { greeting } from '../../lib/format';
import { LogoMark } from '../layout/LogoMark';

const SUGGESTIONS = [
  'Can I get force enrolled in CS412?',
  'Please submit a force-enrollment request for CS412 section S1',
  'What happened with my last request?',
  'How many credits am I taking?',
  'Can I get into the machine learning course?',
];

export function EmptyState({ name, onPick }: { name: string; onPick: (text: string) => void }) {
  const first = name.split(' ')[0] === 'Student' ? name : name.split(' ')[0];
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col justify-center px-4 py-10">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
        <LogoMark size={40} />
        <h1 className="mt-5 text-[28px] font-semibold leading-tight tracking-tight text-navy">{greeting()}, {first}</h1>
        <p className="mt-2 max-w-[520px] text-[15px] leading-relaxed text-muted">
          I can check the force-enrollment rules for a course, submit a request to the instructor once you confirm, and follow it up until you're enrolled.
        </p>
      </motion.div>
      <div className="mt-7 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s, i) => (
          <motion.button
            key={s}
            type="button"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 + i * 0.04, duration: 0.22 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onPick(s)}
            className="rounded-xl border border-line bg-surface px-3.5 py-2 text-left text-[14px] text-ink transition-colors hover:border-accent/40 hover:bg-accent-soft/50"
          >
            {s}
          </motion.button>
        ))}
      </div>
    </div>
  );
}

import { AnimatePresence, motion } from 'framer-motion';
import { Brain, FolderKanban, User, X } from 'lucide-react';
import { useMediaQuery } from '../../lib/hooks';
import { useApp, type InspectorTab } from '../../state/AppContext';
import { Segmented } from '../ui/Segmented';
import { MemoryTab } from '../memory/MemoryTab';
import { CaseTab } from './CaseTab';
import { ProfileTab } from './ProfileTab';

function Body() {
  const { inspectorTab, setInspectorTab, setInspectorOpen } = useApp();
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <Segmented<InspectorTab>
          id="inspector-tabs"
          label="Inspector"
          className="flex-1"
          value={inspectorTab}
          onChange={setInspectorTab}
          options={[
            { value: 'case', label: <><FolderKanban className="h-3.5 w-3.5" aria-hidden />Case</> },
            { value: 'memory', label: <><Brain className="h-3.5 w-3.5" aria-hidden />Memory</> },
            { value: 'profile', label: <><User className="h-3.5 w-3.5" aria-hidden />Profile</> },
          ]}
        />
        <button type="button" onClick={() => setInspectorOpen(false)} aria-label="Close inspector" className="rounded-lg p-1.5 text-faint hover:bg-sunk hover:text-ink">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={inspectorTab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.16 }}>
            {inspectorTab === 'case' ? <CaseTab /> : inspectorTab === 'memory' ? <MemoryTab /> : <ProfileTab />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

/** Right-hand case inspector: a 380px panel on desktop, a bottom sheet on small screens. */
export function Inspector() {
  const { inspectorOpen, setInspectorOpen } = useApp();
  const isLg = useMediaQuery('(min-width: 1024px)');
  if (isLg) {
    return (
      <AnimatePresence initial={false}>
        {inspectorOpen && (
          <motion.aside
            key="inspector"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 380, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: 'easeOut' }}
            className="shrink-0 overflow-hidden border-l border-line bg-surface/60"
            aria-label="Case inspector"
          >
            <div className="h-full w-[380px]"><Body /></div>
          </motion.aside>
        )}
      </AnimatePresence>
    );
  }
  return (
    <AnimatePresence>
      {inspectorOpen && (
        <motion.div key="sheet" className="fixed inset-0 z-40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/30" onClick={() => setInspectorOpen(false)} aria-hidden />
          <motion.aside
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', stiffness: 380, damping: 40 }}
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.4 }}
            onDragEnd={(_, info) => { if (info.offset.y > 120) setInspectorOpen(false); }}
            className="absolute inset-x-0 bottom-0 h-[82dvh] overflow-hidden rounded-t-2xl border-t border-line bg-canvas shadow-2xl"
            aria-label="Case inspector"
          >
            <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line" aria-hidden />
            <div className="h-[calc(100%-12px)]"><Body /></div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

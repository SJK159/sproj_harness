import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp, Lock, Square } from 'lucide-react';
import { cn } from '../../lib/format';

interface Props {
  onSend: (text: string) => void; onStop: () => void; running: boolean;
  disabledReason: string | null; placeholder?: string;
}

export function Composer({ onSend, onStop, running, disabledReason, placeholder }: Props) {
  const [text, setText] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);
  const disabled = !!disabledReason;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  useEffect(() => { if (!disabled && !running) ref.current?.focus({ preventScroll: true }); }, [disabled, running]);

  const send = () => {
    const t = text.trim();
    if (!t || running || disabled) return;
    onSend(t);
    setText('');
  };

  return (
    <div className="relative">
      <AnimatePresence initial={false}>
        {disabled && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="mb-2 flex items-center gap-2 rounded-xl bg-sunk px-3 py-2 text-[13px] text-muted"
            role="status"
          >
            <Lock aria-hidden className="h-3.5 w-3.5 shrink-0" /> {disabledReason}
          </motion.div>
        )}
      </AnimatePresence>
      <div className={cn('flex items-end gap-2 rounded-2xl border bg-surface p-2 pl-4 shadow-sm transition-colors', disabled ? 'border-line opacity-60' : 'border-line focus-within:border-accent/60')}>
        <textarea
          ref={ref}
          rows={1}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
          }}
          placeholder={placeholder ?? 'Ask about a course or a request…'}
          aria-label="Message"
          className="scroll-thin max-h-[200px] min-h-[24px] flex-1 resize-none bg-transparent py-2 text-[15px] leading-6 outline-none placeholder:text-faint disabled:cursor-not-allowed"
        />
        {running ? (
          <motion.button type="button" whileTap={{ scale: 0.92 }} onClick={onStop} aria-label="Stop" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink text-canvas hover:opacity-90">
            <Square aria-hidden className="h-3.5 w-3.5 fill-current" />
          </motion.button>
        ) : (
          <motion.button
            type="button"
            whileTap={{ scale: 0.92 }}
            onClick={send}
            disabled={disabled || !text.trim()}
            aria-label="Send"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent text-accent-ink transition-opacity hover:bg-accent/90 disabled:opacity-35"
          >
            <ArrowUp aria-hidden className="h-4 w-4" />
          </motion.button>
        )}
      </div>
      <div className="mt-1.5 hidden text-center text-[11px] text-faint sm:block">Enter to send · Shift+Enter for a new line · Rules shown are placeholders, not official LUMS policy</div>
    </div>
  );
}

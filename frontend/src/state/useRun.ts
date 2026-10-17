import { useCallback, useEffect, useRef, useState } from 'react';
import type { RunStream } from '../api/client';
import type { RunEvent } from '../api/types';
import { applyRunEvent, newTurn, type LiveTurn } from '../lib/turn';

/** Consumes a RunStream into a LiveTurn. Never blocks: state updates per event. */
export function useRun() {
  const [turn, setTurn] = useState<LiveTurn | null>(null);
  const streamRef = useRef<RunStream | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; streamRef.current?.stop(); }, []);

  const start = useCallback(async (stream: RunStream, onEvent?: (ev: RunEvent, t: LiveTurn) => void): Promise<LiveTurn> => {
    streamRef.current = stream;
    let t = newTurn();
    setTurn(t);
    try {
      for await (const ev of stream.events) {
        t = applyRunEvent(t, ev);
        if (!alive.current) break;
        setTurn(t);
        onEvent?.(ev, t);
      }
      if (t.status === 'running') {
        t = { ...t, status: 'error', error: 'The connection closed before the run finished.', finishedAt: Date.now() };
      }
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === 'AbortError';
      t = { ...t, status: aborted ? 'interrupted' : 'error', error: aborted ? undefined : e instanceof Error ? e.message : String(e), finishedAt: Date.now() };
    } finally {
      if (streamRef.current === stream) streamRef.current = null;
    }
    if (alive.current) setTurn(t);
    return t;
  }, []);

  const stop = useCallback(() => streamRef.current?.stop(), []);
  return { turn, setTurn, start, stop, running: turn?.status === 'running' };
}

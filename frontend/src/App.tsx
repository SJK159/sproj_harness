import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MotionConfig } from 'framer-motion';
import { AppProvider } from './state/AppContext';
import { Shell } from './components/layout/Shell';
import { api } from './api/client';
import { acceptAuthStatus, apiBase, authStatus, type AuthStatus, type SessionIdentity } from './api/auth';

export default function App() {
  const [epoch, setEpoch] = useState(0);
  const onReset = useCallback(() => setEpoch((e) => e + 1), []);
  const [auth, setAuth] = useState<AuthStatus | null>(api.mode === 'mock' ? { mode: 'demo', authenticated: false } : null);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const refresh = useCallback(() => {
    const sequence = ++generation.current;
    setError('');
    void authStatus().then((value) => {
      if (sequence !== generation.current) return;
      acceptAuthStatus(value); setAuth(value);
    }).catch((e: unknown) => {
      if (sequence !== generation.current) return;
      setAuth(null); setError(e instanceof Error ? e.message : 'Sign-in unavailable');
    });
  }, []);
  useEffect(() => {
    if (api.mode === 'mock') return;
    refresh();
    const lost = () => { ++generation.current; setAuth({ mode: 'bff', authenticated: false }); setEpoch((e) => e + 1); };
    window.addEventListener('harness:authentication-lost', lost);
    window.addEventListener('focus', refresh);
    return () => { ++generation.current; window.removeEventListener('harness:authentication-lost', lost); window.removeEventListener('focus', refresh); };
  }, [refresh]);
  const actor = auth?.mode === 'bff' ? auth.actor_id : undefined;
  const role = auth?.mode === 'bff' ? auth.role : undefined;
  const identity = useMemo<SessionIdentity | undefined>(() => actor && role ? { actor_id: actor, role } : undefined, [actor, role]);
  if (!auth || (auth.mode === 'bff' && !auth.authenticated)) return (
    <main className="grid min-h-screen place-items-center bg-canvas p-6">
      <section className="max-w-md rounded-xl border border-line bg-surface p-8">
        <h1 className="text-xl font-semibold">LUMS Force-Enrollment Assistant</h1>
        {error ? <><p role="alert" className="my-4">{error}</p><button type="button" onClick={refresh}>Retry</button></> :
          auth ? <><p className="my-4">Sign in with your project Microsoft account.</p><a className="underline" href={`${apiBase}/auth/login`}>Sign in with Microsoft</a></> : <p className="my-4" role="status">Checking sign-in…</p>}
      </section>
    </main>
  );
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.2, ease: 'easeOut' }}>
      <AppProvider key={`${epoch}-${identity?.actor_id ?? 'demo'}`} onReset={onReset} identity={identity}>
        <Shell />
      </AppProvider>
    </MotionConfig>
  );
}

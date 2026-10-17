import { useCallback, useState } from 'react';
import { MotionConfig } from 'framer-motion';
import { AppProvider } from './state/AppContext';
import { Shell } from './components/layout/Shell';

export default function App() {
  const [epoch, setEpoch] = useState(0);
  const onReset = useCallback(() => setEpoch((e) => e + 1), []);
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.2, ease: 'easeOut' }}>
      <AppProvider key={epoch} onReset={onReset}>
        <Shell />
      </AppProvider>
    </MotionConfig>
  );
}

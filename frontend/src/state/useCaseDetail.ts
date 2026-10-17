import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { CaseDetail } from '../api/types';
import { useApp } from './AppContext';

/** Fetches a case and refetches whenever any run reports a case change. */
export function useCaseDetail(caseId: string | null | undefined) {
  const { caseVersion } = useApp();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!caseId) { setDetail(null); setError(null); return; }
    let alive = true;
    api.getCase(caseId)
      .then((d) => { if (alive) { setDetail(d); setError(null); } })
      .catch((e: unknown) => { if (alive) setError(e instanceof Error ? e.message : 'Could not load the case'); });
    return () => { alive = false; };
  }, [caseId, caseVersion]);
  return { detail: detail && detail.case.case_id === caseId ? detail : null, error };
}

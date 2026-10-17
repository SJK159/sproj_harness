import {
  AlertTriangle, Ban, CheckCircle2, FileText, HelpCircle, Hourglass, Send, Settings2, ThumbsUp, XCircle, type LucideIcon,
} from 'lucide-react';
import type { CaseState } from '../api/types';

export type Tone = 'neutral' | 'amber' | 'teal' | 'green' | 'slate' | 'red';

export const STATE_META: Record<CaseState, { label: string; tone: Tone; icon: LucideIcon }> = {
  DRAFT: { label: 'Draft', tone: 'neutral', icon: FileText },
  AWAITING_CONFIRMATION: { label: 'Awaiting confirmation', tone: 'neutral', icon: HelpCircle },
  SUBMITTED: { label: 'Submitted', tone: 'amber', icon: Send },
  AWAITING_APPROVAL: { label: 'Awaiting approval', tone: 'amber', icon: Hourglass },
  APPROVED: { label: 'Approved', tone: 'teal', icon: ThumbsUp },
  EXECUTING: { label: 'Enrolling', tone: 'teal', icon: Settings2 },
  COMPLETED: { label: 'Completed', tone: 'green', icon: CheckCircle2 },
  CANCELLED: { label: 'Cancelled', tone: 'slate', icon: Ban },
  REJECTED: { label: 'Rejected', tone: 'red', icon: XCircle },
  FAILED: { label: 'Failed', tone: 'red', icon: AlertTriangle },
};

export const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-stone-200/70 text-stone-700 dark:bg-white/10 dark:text-stone-200',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200',
  teal: 'bg-teal-100 text-teal-800 dark:bg-teal-400/15 dark:text-teal-200',
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200',
  slate: 'bg-slate-200 text-slate-700 dark:bg-slate-400/15 dark:text-slate-200',
  red: 'bg-red-100 text-red-800 dark:bg-red-400/15 dark:text-red-200',
};

export const TONE_DOT: Record<Tone, string> = {
  neutral: 'bg-stone-400', amber: 'bg-amber-500', teal: 'bg-teal-600', green: 'bg-emerald-600', slate: 'bg-slate-400', red: 'bg-red-600',
};

export const MAIN_PATH: CaseState[] = ['DRAFT', 'AWAITING_CONFIRMATION', 'SUBMITTED', 'AWAITING_APPROVAL', 'APPROVED', 'EXECUTING', 'COMPLETED'];
export const FINAL_STATES: CaseState[] = ['COMPLETED', 'REJECTED', 'FAILED', 'CANCELLED'];
export const isFinal = (s: string | null | undefined): boolean => !!s && (FINAL_STATES as string[]).includes(s);

export function stateMeta(s: string): { label: string; tone: Tone; icon: LucideIcon } {
  return STATE_META[s as CaseState] ?? { label: s, tone: 'neutral', icon: HelpCircle };
}

export type BoardGroup = 'In progress' | 'Waiting for instructor' | 'Completed' | 'Not completed';
export const BOARD_GROUPS: BoardGroup[] = ['In progress', 'Waiting for instructor', 'Completed', 'Not completed'];
export function boardGroup(s: CaseState): BoardGroup {
  if (s === 'COMPLETED') return 'Completed';
  if (s === 'REJECTED' || s === 'FAILED' || s === 'CANCELLED') return 'Not completed';
  if (s === 'SUBMITTED' || s === 'AWAITING_APPROVAL') return 'Waiting for instructor';
  return 'In progress';
}

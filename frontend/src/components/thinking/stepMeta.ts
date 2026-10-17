import {
  Bell, BookOpen, Brain, FolderOpen, GraduationCap, HelpCircle, Hourglass, LayoutList, ListChecks, Scale, Send, User, UserSearch, Wrench,
  type LucideIcon,
} from 'lucide-react';
import type { Step } from '../../api/types';
import { deepestRunning, type LiveTurn } from '../../lib/turn';

const SKILL = '/skills/force-enrollment/SKILL.md';
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);

/** Plain-language title for a tool step. Unknown tools show their raw name. */
export function stepTitle(s: Step): string {
  const a = s.args ?? {};
  switch (s.name) {
    case 'write_todos': return 'Planning';
    case 'read_file': return str(a.path) === SKILL ? 'Reading the force-enrollment rules' : `Reading ${str(a.path) ?? 'a file'}`;
    case 'task': return 'Asking the eligibility checker';
    case 'list_sections': return str(a.course_id) ? `Looking up sections of ${str(a.course_id)}` : str(a.query) ? `Searching courses for “${str(a.query)}”` : 'Looking up sections';
    case 'check_my_eligibility': return `Checking the rules for ${str(a.offering_id) ?? str(a.course_id) ?? 'the section'}`;
    case 'get_my_profile': return 'Reading your profile';
    case 'get_my_cases': return 'Looking up your cases';
    case 'submit_case': return 'Submitting your request';
    case 'execute_enrollment': return s.status === 'paused' ? 'Waiting for the instructor' : 'Enrolling you';
    case 'notify_student': return 'Sending you a notice';
    case 'save_case_note': return 'Saving this to memory';
    case 'ask_student': return 'The checker has a question for you';
    default: return s.name;
  }
}

export function stepIcon(s: Step): LucideIcon {
  switch (s.name) {
    case 'write_todos': return ListChecks;
    case 'read_file': return BookOpen;
    case 'task': return UserSearch;
    case 'list_sections': return LayoutList;
    case 'check_my_eligibility': return Scale;
    case 'get_my_profile': return User;
    case 'get_my_cases': return FolderOpen;
    case 'submit_case': return Send;
    case 'execute_enrollment': return s.status === 'paused' ? Hourglass : GraduationCap;
    case 'notify_student': return Bell;
    case 'save_case_note': return Brain;
    case 'ask_student': return HelpCircle;
    default: return Wrench;
  }
}

/** One short phrase describing what the agent is doing right now. */
export function currentActivity(t: LiveTurn): string {
  if (t.status !== 'running') return 'Done';
  if (t.interrupt?.kind === 'ask_student') return 'Waiting for your answer';
  if (t.interrupt?.kind === 'confirm_submission') return 'Waiting for your confirmation';
  if (t.interrupt?.kind === 'waiting_for_instructor') return 'Waiting for the instructor';
  const s = deepestRunning(t.steps);
  if (s) return stepTitle(s);
  if (t.text) return 'Writing the answer';
  return 'Thinking';
}

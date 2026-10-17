export const RULE_VERSION = 'placeholder v0.1';

export const RULES: Record<string, { title: string; text: string; codes: string[] }> = {
  'FE-1': { title: 'Full sections only', text: 'Force enrollment is for full sections. If a section has open seats, register normally.', codes: ['SEATS_AVAILABLE', 'OTHER_SECTION_OPEN'] },
  'FE-2': { title: 'Prerequisites', text: 'Prerequisites must be completed. A prerequisite in progress this term does not count.', codes: ['PREREQ_MISSING', 'PREREQ_IN_PROGRESS'] },
  'FE-3': { title: 'No timetable clash', text: 'The section must not clash with your current timetable.', codes: ['CLASH'] },
  'FE-4': { title: 'Credit cap', text: 'Your credits this term, including the new course, must not exceed 20.', codes: ['CREDIT_LIMIT'] },
  'FE-5': { title: 'Not on probation', text: 'No force enrollment while on probation (CGPA below 2.0).', codes: ['PROBATION'] },
  'FE-6': { title: 'Section restrictions', text: 'You must meet the section’s year and CGPA restrictions.', codes: ['YEAR_RESTRICTION', 'CGPA_BELOW_MIN'] },
  'FE-7': { title: 'Instructor accepts FE', text: 'The instructor must accept force enrollment, within a cap of FE slots.', codes: ['FE_NOT_ACCEPTED', 'FE_CAP_REACHED'] },
  'FE-8': { title: 'One section, offered course', text: 'One section per course, and the course must be offered this term.', codes: ['ALREADY_ENROLLED', 'NOT_OFFERED'] },
};

/** Matches FE-4, FE‑4 (non-breaking hyphen) and an optional "(placeholder v0.1)" suffix; never a case id. */
export const RULE_PATTERN = 'FE[-\\u2011]\\d(?![0-9a-fA-F])(?:\\s*\\(placeholder v[\\d.]+\\))?';

export function ruleKey(label: string): string | null {
  const m = /FE[-\u2011](\d)/.exec(label);
  return m ? `FE-${m[1]}` : null;
}
